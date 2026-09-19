"""Generación asistida de recetas correctivas mediante IA.

La IA propone tres alternativas, pero nunca modifica archivos por sí sola.
La propuesta elegida se convierte al mismo modelo Correccion usado por el
motor determinista y queda sometida a preview, backup, verificación y rollback.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

from .config import ConfigObjetivo, Correccion


DEFAULT_PROVIDER_ID = "llmlab"
DEFAULT_MODEL_ID = "lab-coder"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


@dataclass
class AIProviderConfig:
    provider_id: str
    provider_name: str
    model_id: str
    model_name: str
    base_url: str
    api_key: str
    config_path: str

    def public_dict(self) -> dict:
        """Metadatos seguros; nunca incluye la API key."""
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "base_url": self.base_url,
            "config_path": self.config_path,
        }


def _opencode_config_path() -> Path:
    override = os.getenv("OPENCODE_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".config" / "opencode" / "opencode.json").resolve()


_ENV_REF = re.compile(r"^\{env:([A-Za-z_][A-Za-z0-9_]*)\}$")


def _resolver_api_key(valor: str | None) -> str:
    if not valor:
        raise RuntimeError(
            "El proveedor llmlab no tiene apiKey en la configuración de OpenCode."
        )

    match = _ENV_REF.match(valor.strip())
    if match:
        variable = match.group(1)
        key = os.getenv(variable)
        if not key:
            raise RuntimeError(
                f"OpenCode usa la variable {variable}, pero no está definida "
                "en esta sesión."
            )
        return key

    return valor.strip()


def cargar_configuracion_opencode(
    *,
    provider_id: str = DEFAULT_PROVIDER_ID,
) -> AIProviderConfig:
    """Carga llmlab/lab-coder desde ~/.config/opencode/opencode.json."""
    path = _opencode_config_path()
    if not path.exists():
        raise RuntimeError(
            "No se encontró la configuración de OpenCode en "
            f"{path}. Configura OpenCode antes de usar el Asistente IA."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"No fue posible leer la configuración de OpenCode: {path}"
        ) from exc

    providers = data.get("provider") or {}
    provider = providers.get(provider_id)
    if not isinstance(provider, dict):
        raise RuntimeError(
            f"No existe el proveedor '{provider_id}' en {path}."
        )

    options = provider.get("options") or {}
    base_url = str(options.get("baseURL") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError(
            f"El proveedor '{provider_id}' no declara options.baseURL."
        )

    api_key = _resolver_api_key(options.get("apiKey"))

    configured_model = str(
        os.getenv("AUDITOR_AI_MODEL")
        or data.get("model")
        or f"{provider_id}/{DEFAULT_MODEL_ID}"
    ).strip()

    if "/" in configured_model:
        selected_provider, model_id = configured_model.split("/", 1)
        if selected_provider != provider_id:
            model_id = DEFAULT_MODEL_ID
    else:
        model_id = configured_model

    models = provider.get("models") or {}
    model_data = models.get(model_id) or {}
    model_name = str(model_data.get("name") or model_id)

    return AIProviderConfig(
        provider_id=provider_id,
        provider_name=str(provider.get("name") or provider_id),
        model_id=model_id,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        config_path=str(path),
    )


@dataclass
class AIRecipeProposal:
    id: str
    titulo: str
    enfoque: str
    explicacion: str
    riesgo: str
    estrategia: str
    buscar: str
    reemplazar: str
    requiere_reinicio: bool
    consideraciones: str

    def as_dict(self) -> dict:
        return asdict(self)


_SENSITIVE_NAME = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b"
)
_BEARER = re.compile(
    r'(?i)(Authorization\s*[:=,\(]\s*["\']?Bearer\s+)([^\s"\']+)'
)
_API_KEY_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
    r"-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_QUOTED_ASSIGNMENT = re.compile(
    r'([:=]\s*)(["\'])(.*?)(\2)'
)
_UNQUOTED_ASSIGNMENT = re.compile(
    r"([:=]\s*)([^;,\s]+)"
)


def _redactar_linea_sensible(linea: str) -> str:
    if not _SENSITIVE_NAME.search(linea):
        return linea

    if _QUOTED_ASSIGNMENT.search(linea):
        return _QUOTED_ASSIGNMENT.sub(
            lambda m: f"{m.group(1)}{m.group(2)}<REDACTED>{m.group(4)}",
            linea,
            count=1,
        )

    return _UNQUOTED_ASSIGNMENT.sub(
        lambda m: f"{m.group(1)}<REDACTED>",
        linea,
        count=1,
    )


def redactar_secretos(texto: str) -> str:
    """Reduce el riesgo de enviar credenciales accidentales al proveedor IA."""
    resultado = _PRIVATE_KEY.sub("<REDACTED_PRIVATE_KEY>", texto)
    resultado = _BEARER.sub(
        lambda m: f"{m.group(1)}<REDACTED>",
        resultado,
    )
    resultado = _API_KEY_VALUE.sub("<REDACTED_API_KEY>", resultado)

    lineas = resultado.splitlines(keepends=True)
    return "".join(_redactar_linea_sensible(linea) for linea in lineas)


def _pistas_utiles(*textos: str) -> list[str]:
    palabras: list[str] = []
    for texto in textos:
        for token in re.findall(r"[A-Za-z0-9_./-]{4,}", texto or ""):
            limpio = token.strip("./-").lower()
            if len(limpio) >= 4 and limpio not in palabras:
                palabras.append(limpio)
    return palabras[:30]


def recortar_codigo(
    codigo: str,
    pistas: Iterable[str],
    *,
    max_chars: int = 30000,
) -> str:
    """Conserva zonas cercanas a pistas del hallazgo en archivos grandes."""
    if len(codigo) <= max_chars:
        return codigo

    lines = codigo.splitlines()
    pistas_l = [p.lower() for p in pistas if len(p) >= 4]
    indices: list[int] = []

    for i, line in enumerate(lines):
        lower = line.lower()
        if any(p in lower for p in pistas_l):
            indices.append(i)

    if not indices:
        mitad = max_chars // 2
        return codigo[:mitad] + "\n\n/* ... RECORTADO ... */\n\n" + codigo[-mitad:]

    seleccion: set[int] = set()
    for idx in indices[:12]:
        inicio = max(0, idx - 45)
        fin = min(len(lines), idx + 46)
        seleccion.update(range(inicio, fin))

    piezas: list[str] = []
    ultimo = None
    total = 0
    for idx in sorted(seleccion):
        if ultimo is not None and idx > ultimo + 1:
            pieza = "\n/* ... RECORTADO ... */\n"
            if total + len(pieza) > max_chars:
                break
            piezas.append(pieza)
            total += len(pieza)

        line = lines[idx] + "\n"
        if total + len(line) > max_chars:
            break
        piezas.append(line)
        total += len(line)
        ultimo = idx

    return "".join(piezas)


def _json_schema() -> dict:
    propuesta = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "titulo": {"type": "string"},
            "enfoque": {
                "type": "string",
                "enum": ["MINIMA", "ESTRUCTURAL", "ALTERNATIVA"],
            },
            "explicacion": {"type": "string"},
            "riesgo": {
                "type": "string",
                "enum": ["BAJO", "MEDIO", "ALTO"],
            },
            "estrategia": {
                "type": "string",
                "enum": ["replace_exact", "regex_replace"],
            },
            "buscar": {"type": "string"},
            "reemplazar": {"type": "string"},
            "requiere_reinicio": {"type": "boolean"},
            "consideraciones": {"type": "string"},
        },
        "required": [
            "id",
            "titulo",
            "enfoque",
            "explicacion",
            "riesgo",
            "estrategia",
            "buscar",
            "reemplazar",
            "requiere_reinicio",
            "consideraciones",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "propuestas": {
                "type": "array",
                "items": propuesta,
            }
        },
        "required": ["propuestas"],
        "additionalProperties": False,
    }


def _extraer_contenido_chat(response_json: dict) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            "El Laboratorio UTB no devolvió choices en chat/completions."
        )

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        textos: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if text:
                    textos.append(str(text))
        if textos:
            return "".join(textos).strip()

    raise RuntimeError(
        "La respuesta de Gemma no contiene texto utilizable."
    )


def _extraer_json(texto: str) -> dict:
    limpio = texto.strip()

    if limpio.startswith("```"):
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio, flags=re.I)
        limpio = re.sub(r"\s*```$", "", limpio)

    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass

    inicio = limpio.find("{")
    fin = limpio.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            return json.loads(limpio[inicio : fin + 1])
        except json.JSONDecodeError:
            pass

    raise RuntimeError(
        "Gemma no devolvió un JSON válido con las tres recetas."
    )


def _validar_propuestas(data: dict) -> list[AIRecipeProposal]:
    items = data.get("propuestas")
    if not isinstance(items, list) or len(items) != 3:
        raise RuntimeError(
            "La IA debe devolver exactamente tres propuestas de receta."
        )

    propuestas = [AIRecipeProposal(**item) for item in items]
    enfoques = {item.enfoque for item in propuestas}
    if enfoques != {"MINIMA", "ESTRUCTURAL", "ALTERNATIVA"}:
        raise RuntimeError(
            "Las tres propuestas deben usar los enfoques "
            "MINIMA, ESTRUCTURAL y ALTERNATIVA."
        )
    return propuestas


def _construir_contexto(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    descripcion: str,
    detalle: str,
    source_relative: str,
    source_text: str,
    metadata_hallazgo: dict | None = None,
    matriz_pruebas: list[dict] | None = None,
    intento_anterior: dict | None = None,
) -> dict:
    pistas = _pistas_utiles(control_id, descripcion, detalle, source_relative)
    limpio = redactar_secretos(source_text)
    recortado = recortar_codigo(limpio, pistas)

    return {
        "sistema": cfg.sistema,
        "version_objetivo": cfg.version_objetivo,
        "control_id": control_id,
        "descripcion_hallazgo": descripcion,
        "detalle_observado": detalle,
        "hallazgo_objetivo": metadata_hallazgo or {},
        "matriz_de_pruebas_del_mismo_control": matriz_pruebas or [],
        "intento_anterior_fallido": intento_anterior,
        "archivo_seleccionado": source_relative,
        "codigo_relevante_redactado": recortado,
        "criterio_de_exito": (
            "La fila objetivo debe pasar a SIN_HALLAZGO y ninguna fila del "
            "mismo control que estaba en SIN_HALLAZGO puede convertirse en "
            "HALLAZGO o ERROR."
        ),
        "restricciones": {
            "solo_archivo_seleccionado": True,
            "no_incluir_credenciales": True,
            "tres_propuestas_diferentes": True,
            "verificacion_posterior_obligatoria": True,
            "no_romper_pruebas_que_ya_pasaban": True,
        },
    }


def generar_tres_recetas(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    descripcion: str,
    detalle: str,
    source_relative: str,
    source_text: str,
    provider: AIProviderConfig | None = None,
    metadata_hallazgo: dict | None = None,
    matriz_pruebas: list[dict] | None = None,
    intento_anterior: dict | None = None,
    timeout: int = 120,
) -> tuple[list[AIRecipeProposal], dict, AIProviderConfig]:
    """Solicita tres recetas a llmlab/lab-coder vía chat/completions."""
    provider = provider or cargar_configuracion_opencode()

    contexto = _construir_contexto(
        cfg,
        control_id=control_id,
        descripcion=descripcion,
        detalle=detalle,
        source_relative=source_relative,
        source_text=source_text,
        metadata_hallazgo=metadata_hallazgo,
        matriz_pruebas=matriz_pruebas,
        intento_anterior=intento_anterior,
    )

    system_prompt = (
        "Eres un asistente defensivo de remediación de código para un "
        "auditor de seguridad. Debes proponer exactamente tres recetas "
        "diferentes para el mismo hallazgo: "
        "MINIMA (cambio pequeño y localizado), "
        "ESTRUCTURAL (mejora de diseño o centralización) y "
        "ALTERNATIVA (otro enfoque válido). "
        "Todas deben modificar únicamente el archivo seleccionado. "
        "No inventes archivos. No incluyas secretos ni credenciales. "
        "Cuando uses replace_exact, el campo buscar debe ser texto literal "
        "que aparezca en el código recibido. Cuando uses regex_replace, "
        "buscar debe ser una expresión regular acotada. "
        "La IA solo propone; un humano seleccionará una opción y un motor "
        "determinista hará preview, backup, aplicación y verificación. "
        "El objetivo NO es solo producir un cambio sintáctico: la receta debe "
        "hacer que la prueba objetivo pase de HALLAZGO a SIN_HALLAZGO. Usa "
        "hallazgo_objetivo como contrato exacto (cuenta, método, ruta y "
        "resultado esperado/observado). Usa matriz_de_pruebas_del_mismo_control "
        "como conjunto de regresión: cualquier fila que ya estaba en "
        "SIN_HALLAZGO debe seguir segura después del cambio. Si existe "
        "intento_anterior_fallido, analiza por qué no resolvió el comportamiento "
        "y NO repitas la misma solución ni una variante superficial. "
        "Prioriza la validación de autorización/propiedad en el punto donde se "
        "decide el acceso al recurso. Responde únicamente con JSON válido, "
        "sin Markdown."
    )

    formato = {
        "propuestas": [
            {
                "id": "IA-1",
                "titulo": "texto",
                "enfoque": "MINIMA",
                "explicacion": "texto",
                "riesgo": "BAJO",
                "estrategia": "replace_exact",
                "buscar": "texto exacto o regex",
                "reemplazar": "texto de reemplazo",
                "requiere_reinicio": True,
                "consideraciones": "texto",
            },
            {
                "id": "IA-2",
                "titulo": "texto",
                "enfoque": "ESTRUCTURAL",
                "explicacion": "texto",
                "riesgo": "MEDIO",
                "estrategia": "replace_exact",
                "buscar": "texto exacto o regex",
                "reemplazar": "texto de reemplazo",
                "requiere_reinicio": True,
                "consideraciones": "texto",
            },
            {
                "id": "IA-3",
                "titulo": "texto",
                "enfoque": "ALTERNATIVA",
                "explicacion": "texto",
                "riesgo": "MEDIO",
                "estrategia": "regex_replace",
                "buscar": "texto exacto o regex",
                "reemplazar": "texto de reemplazo",
                "requiere_reinicio": True,
                "consideraciones": "texto",
            },
        ]
    }

    user_prompt = (
        "Analiza el siguiente hallazgo y genera exactamente tres recetas que "
        "tengan posibilidad real de hacer pasar la prueba de seguridad. "
        "No repitas una receta fallida incluida en el contexto.\n\n"
        "FORMATO JSON OBLIGATORIO:\n"
        + json.dumps(formato, ensure_ascii=False, indent=2)
        + "\n\nCONTEXTO:\n"
        + json.dumps(contexto, ensure_ascii=False, indent=2)
    )

    endpoint = provider.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": provider.model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
    }

    resp = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        detalle_error = resp.text[:1200]
        raise RuntimeError(
            "Laboratorio UTB respondió HTTP "
            f"{resp.status_code}: {detalle_error}"
        )

    response_json = resp.json()
    texto = _extraer_contenido_chat(response_json)
    data = _extraer_json(texto)
    propuestas = _validar_propuestas(data)
    return propuestas, contexto, provider


def propuesta_a_correccion(
    propuesta: AIRecipeProposal,
    *,
    control_id: str,
    source_relative: str,
) -> Correccion:
    if propuesta.estrategia == "replace_exact":
        op = {
            "estrategia": "replace_exact",
            "buscar": propuesta.buscar,
            "reemplazar": propuesta.reemplazar,
            "max_reemplazos": 1,
        }
    else:
        op = {
            "estrategia": "regex_replace",
            "patron": propuesta.buscar,
            "sustitucion": propuesta.reemplazar,
            "max_reemplazos": 1,
        }

    return Correccion(
        control_id=control_id,
        archivo=source_relative,
        descripcion=(
            f"Receta IA {propuesta.id}: {propuesta.titulo}. "
            f"{propuesta.explicacion}"
        ),
        requiere_reinicio=propuesta.requiere_reinicio,
        operaciones=[op],
    )


def inferir_archivo_control(
    cfg: ConfigObjetivo,
    control_id: str,
) -> str | None:
    receta = cfg.correccion_por_control(control_id)
    if receta:
        return receta.archivo

    for check in cfg.chequeos_pilar2:
        if check.id_control == control_id and check.archivo:
            return check.archivo
    return None


def guardar_sesion_ia(
    evidence_base: str | Path,
    *,
    contexto: dict,
    propuestas: list[AIRecipeProposal],
    provider: AIProviderConfig,
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = Path(evidence_base) / "ia" / ts
    root.mkdir(parents=True, exist_ok=True)

    (root / "contexto_redactado.json").write_text(
        json.dumps(contexto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "propuestas.json").write_text(
        json.dumps(
            {
                "proveedor": provider.public_dict(),
                "propuestas": [p.as_dict() for p in propuestas],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def guardar_seleccion_ia(
    session_dir: str | Path,
    *,
    propuesta: AIRecipeProposal,
    correccion: Correccion,
    resultado: dict | None = None,
) -> None:
    root = Path(session_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "propuesta": propuesta.as_dict(),
        "correccion_normalizada": asdict(correccion),
        "resultado_ciclo": resultado,
    }
    (root / "seleccion.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
