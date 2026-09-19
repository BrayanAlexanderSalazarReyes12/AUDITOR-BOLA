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


DEFAULT_MODEL = os.getenv("AUDITOR_AI_MODEL", "gpt-6-astra")
DEFAULT_BASE_URL = os.getenv(
    "AUDITOR_AI_BASE_URL", "https://api.openai.com/v1"
).rstrip("/")


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


def _extraer_output_text(response_json: dict) -> str:
    textos: list[str] = []
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                textos.append(content["text"])
    if not textos and response_json.get("output_text"):
        textos.append(str(response_json["output_text"]))
    if not textos:
        raise RuntimeError("La respuesta de IA no contiene output_text.")
    return "".join(textos)


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
        "archivo_seleccionado": source_relative,
        "codigo_relevante_redactado": recortado,
        "restricciones": {
            "solo_archivo_seleccionado": True,
            "no_incluir_credenciales": True,
            "tres_propuestas_diferentes": True,
            "verificacion_posterior_obligatoria": True,
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
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: int = 90,
) -> tuple[list[AIRecipeProposal], dict]:
    """Solicita tres recetas estructuradas al proveedor de IA."""
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "Falta OPENAI_API_KEY. Defínela en el entorno antes de usar IA."
        )

    modelo = model or DEFAULT_MODEL
    endpoint = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/responses"
    contexto = _construir_contexto(
        cfg,
        control_id=control_id,
        descripcion=descripcion,
        detalle=detalle,
        source_relative=source_relative,
        source_text=source_text,
    )

    instructions = (
        "Actúas como asistente de remediación de código para un auditor "
        "de seguridad defensivo. Debes generar exactamente 3 recetas "
        "diferentes para el mismo hallazgo: MINIMA (cambio mínimo), "
        "ESTRUCTURAL (mejora de diseño) y ALTERNATIVA (otro enfoque válido). "
        "No inventes otros archivos: todas las propuestas deben modificar "
        "únicamente el archivo seleccionado. El campo buscar debe copiar "
        "texto real del código recibido cuando uses replace_exact. "
        "Para regex_replace, buscar debe ser una expresión regular acotada. "
        "No incluyas secretos, claves ni credenciales. La IA solo propone; "
        "un humano seleccionará una opción y un motor determinista la "
        "previsualizará, respaldará, aplicará y verificará."
    )

    payload = {
        "model": modelo,
        "instructions": instructions,
        "input": (
            "Genera las tres propuestas de remediación en JSON estructurado "
            "para este contexto:\n" + json.dumps(
                contexto, ensure_ascii=False, indent=2
            )
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "auditor_recipe_proposals",
                "strict": True,
                "schema": _json_schema(),
            }
        },
        "store": False,
    }

    resp = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        detalle_error = resp.text[:1200]
        raise RuntimeError(
            f"Proveedor IA respondió HTTP {resp.status_code}: {detalle_error}"
        )

    response_json = resp.json()
    text = _extraer_output_text(response_json)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "La respuesta estructurada de IA no pudo convertirse a JSON."
        ) from exc

    propuestas = _validar_propuestas(data)
    return propuestas, contexto


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
    model: str,
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
                "modelo": model,
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
