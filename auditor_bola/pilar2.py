"""Motor genérico del Pilar 2: configuración, políticas y runtime.

Flujo:
DESCUBRIR -> CORRELACIONAR -> CANDIDATO -> PRUEBA -> EVIDENCIA ->
CONFIRMAR/DESCARTAR -> DEDUPLICAR -> HALLAZGO -> CORRECCIÓN -> REPRUEBA.

Un control es un caso de prueba. Un hallazgo es una causa raíz confirmada y
puede contener múltiples controles/evidencias.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .config import ChequeoPilar2, ConfigObjetivo
from .pilar2_discovery import (
    analyze_container_security,
    analyze_secret_file,
)
from .transport import request_http


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(*parts: Any) -> str:
    raw = "|".join(str(part or "").strip().lower() for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


@dataclass
class ResultadoPilar2:
    sistema: str
    id_control: str
    nombre: str
    tipo: str
    vulnerable: bool
    estado: str
    detalle: str
    http_status: int | None
    ts: str
    familia: str = "GENERIC"
    severidad: str = "MEDIA"
    confianza: str = "media"
    causa_raiz: str = "configuracion_insegura"
    evidencia: list[dict[str, Any]] = field(default_factory=list)
    recomendacion: str | None = None
    archivo: str | None = None
    ruta: str | None = None
    metodo: str | None = None
    estado_control: str = "ejecutado"
    fingerprint: str | None = None
    componente: str | None = None
    parametro: str | None = None
    autogenerado: bool = False
    archivos_fuente: list[str] = field(default_factory=list)
    endpoints_afectados: list[str] = field(default_factory=list)
    casos_prueba: list[dict[str, Any]] = field(default_factory=list)
    configuracion_detectada: dict[str, Any] = field(default_factory=dict)
    estrategia_correccion: dict[str, Any] = field(default_factory=dict)
    verificacion: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _cuenta(cfg: ConfigObjetivo, username: str | None):
    if not username:
        return None
    cuenta = cfg.cuenta_por_username(username)
    if cuenta is None:
        raise ValueError(f"cuenta '{username}' no configurada")
    return cuenta


def _preparar_cuerpo(chequeo: ChequeoPilar2) -> dict | None:
    cuerpo = dict(chequeo.cuerpo or {})
    if chequeo.campo_repetir and chequeo.cantidad > 0:
        cuerpo[chequeo.campo_repetir] = chequeo.caracter * chequeo.cantidad
    return cuerpo or None


def _familia(chequeo: ChequeoPilar2) -> str:
    explicit = str(chequeo.familia or "").strip().upper()
    if explicit:
        aliases = {
            "DOCKER": "CONTAINER",
            "BYPASS": "LIMIT_BYPASS",
            "LIMIT": "LIMIT_BYPASS",
            "COOKIE": "SESSION",
        }
        return aliases.get(explicit, explicit)

    joined = " ".join(
        [
            str(chequeo.id_control or ""),
            str(chequeo.tipo or ""),
            str(chequeo.nombre or ""),
        ]
    ).lower()
    if "cors" in joined:
        return "CORS"
    if any(
        token in joined
        for token in (
            "secret", "token", "api_key", "api-key", "password",
            "signing", "encryption",
        )
    ):
        return "SECRET"
    if any(token in joined for token in ("docker", "container", "contenedor")):
        return "CONTAINER"
    if "debug" in joined:
        return "DEBUG"
    if any(token in joined for token in ("cookie", "session", "sesion")):
        return "SESSION"
    if any(
        token in joined
        for token in (
            "bypass", "limit", "limite", "quota", "cuota",
            "rate", "budget", "presupuesto",
        )
    ):
        return "LIMIT_BYPASS"
    return "GENERIC"


def _family_defaults(
    family: str,
) -> tuple[str, str, str]:
    data = {
        "CORS": (
            "ALTA",
            "politica_cors",
            "Restringir CORS a orígenes explícitamente confiables y habilitar "
            "credenciales solo dentro de esa política.",
        ),
        "SECRET": (
            "ALTA",
            "gestion_secretos",
            "Obtener secretos desde una fuente externa segura y hacer fallar "
            "el arranque productivo cuando falten o sean valores inseguros.",
        ),
        "CONTAINER": (
            "ALTA",
            "privilegios_contenedor",
            "Ejecutar el runtime con usuario no privilegiado y eliminar "
            "privilegios, capabilities, host modes y mounts innecesarios.",
        ),
        "DEBUG": (
            "MEDIA",
            "configuracion_debug",
            "Separar entornos y deshabilitar debug en configuración desplegable.",
        ),
        "SESSION": (
            "MEDIA",
            "configuracion_sesion",
            "Configurar sesión/cookies con atributos y transporte adecuados.",
        ),
        "LIMIT_BYPASS": (
            "ALTA",
            "autorizacion_excepcion_limites",
            "Autorizar explícitamente cualquier capacidad que modifique u "
            "omita una política antes de aplicar la excepción.",
        ),
        "GENERIC": (
            "MEDIA",
            "configuracion_insegura",
            "Corregir la condición insegura y repetir el control con regresión.",
        ),
    }
    return data.get(family, data["GENERIC"])


def _abstract_recipe(family: str) -> dict[str, Any]:
    recipes = {
        "CORS": {
            "problema": "origen no confiable admitido por la política CORS",
            "estrategia": [
                "Localizar middleware/configuración CORS efectiva.",
                "Reemplazar reflexión/patrones permisivos por allowlist explícita.",
                "Permitir credenciales solo para orígenes confiables.",
                "Emitir Vary: Origin cuando la respuesta dependa del Origin.",
            ],
            "restricciones": [
                "No asumir un framework concreto.",
                "No reutilizar rutas o archivos del proyecto benchmark.",
            ],
            "verificacion": [
                "Repetir Origin externo, null y origen de borde.",
                "Confirmar que el origen no confiable no recibe permiso.",
            ],
        },
        "SECRET": {
            "problema": "secreto fallback potencialmente utilizable en producción",
            "estrategia": [
                "Detectar el entorno y la fuente externa del secreto.",
                "En producción rechazar secreto ausente.",
                "En producción rechazar valores default conocidos.",
                "Permitir fallback local solo si la política lo define.",
            ],
            "restricciones": [
                "No insertar un nombre de variable universal.",
                "No almacenar el secreto literal en la receta aprendida.",
            ],
            "verificacion": [
                "Producción no inicia sin secreto.",
                "Producción no inicia con fallback inseguro.",
                "Desarrollo conserva únicamente el comportamiento permitido.",
            ],
        },
        "LIMIT_BYPASS": {
            "problema": "capacidad excepcional puede alterar una política",
            "estrategia": [
                "Resolver identidad, rol/permisos o atributos.",
                "Autorizar la excepción antes de alterar la política.",
                "Rechazar de forma cerrada a identidades no autorizadas.",
                "Registrar el uso de la vía excepcional.",
            ],
            "restricciones": [
                "No basar la receta en el nombre literal del parámetro.",
                "No confundir funcionalidad excepcional con vulnerabilidad.",
            ],
            "verificacion": [
                "Operación normal conserva comportamiento.",
                "Bypass no privilegiado queda rechazado.",
                "Bypass privilegiado funciona únicamente si corresponde.",
            ],
        },
        "CONTAINER": {
            "problema": "runtime de contenedor con privilegios excesivos",
            "estrategia": [
                "Resolver usuario efectivo del stage/runtime final.",
                "Crear o utilizar usuario no privilegiado.",
                "Asignar ownership solo a directorios necesarios.",
                "Eliminar privileged, capabilities y mounts no requeridos.",
            ],
            "restricciones": [
                "No insertar USER app ciegamente.",
                "Considerar Compose/Kubernetes como overrides del Dockerfile.",
            ],
            "verificacion": [
                "El proceso efectivo no ejecuta como UID 0.",
                "La aplicación inicia y conserva smoke tests.",
            ],
        },
    }
    return recipes.get(
        family,
        {
            "problema": "condición de seguridad incumplida",
            "estrategia": [
                "Localizar la decisión de seguridad.",
                "Aplicar validación antes del efecto sensible.",
            ],
            "restricciones": ["Generar parche contextual."],
            "verificacion": [
                "Repetir el control original.",
                "Ejecutar regresión de controles relacionados.",
            ],
        },
    )


def _semantic_fingerprint(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    family: str,
    root_cause: str,
) -> str:
    # CORS se consolida por componente responsable. Distintos endpoints del
    # mismo middleware son evidencias del mismo hallazgo, pero dos servicios o
    # componentes CORS distintos conservan hallazgos independientes.
    if family == "CORS":
        cors_component = (
            chequeo.componente
            or chequeo.archivo
            or str((chequeo.metadata or {}).get("alcance") or "")
            or "service-global"
        )
        return _digest(
            family,
            cfg.base_url,
            root_cause,
            cors_component,
        )
    if family == "CONTAINER":
        return _digest(family, root_cause, "container-runtime")
    if chequeo.fingerprint:
        return str(chequeo.fingerprint)
    component = (
        chequeo.componente
        or chequeo.archivo
        or str((chequeo.metadata or {}).get("componente") or "")
    )
    semantic_subject = (
        chequeo.parametro
        or str((chequeo.metadata or {}).get("variable") or "")
        or str((chequeo.metadata or {}).get("alcance") or "")
    )
    return _digest(
        family,
        root_cause,
        component,
        semantic_subject,
        chequeo.ruta if family == "LIMIT_BYPASS" else "",
    )


def _resultado(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    *,
    vulnerable: bool,
    estado: str,
    estado_control: str,
    detalle: str,
    http_status: int | None = None,
    evidencia: list[dict[str, Any]] | None = None,
    confianza: str | None = None,
    severidad: str | None = None,
    configuracion: dict[str, Any] | None = None,
    casos_prueba: list[dict[str, Any]] | None = None,
    endpoints_afectados: list[str] | None = None,
) -> ResultadoPilar2:
    family = _familia(chequeo)
    default_severity, default_root, recommendation = _family_defaults(family)
    root_cause = chequeo.causa_raiz or default_root
    recipe = dict(chequeo.estrategia_correccion or {})
    if not recipe:
        recipe = _abstract_recipe(family)
    verification = dict(chequeo.verificacion or {})
    if not verification:
        verification = {
            "obligatoria": True,
            "criterios": list(recipe.get("verificacion") or []),
            "regresion": True,
        }

    return ResultadoPilar2(
        sistema=cfg.sistema,
        id_control=chequeo.id_control,
        nombre=chequeo.nombre,
        tipo=chequeo.tipo,
        vulnerable=vulnerable,
        estado=estado,
        detalle=detalle,
        http_status=http_status,
        ts=_ts(),
        familia=family,
        severidad=severidad or default_severity,
        confianza=confianza or chequeo.confianza or (
            "alta" if vulnerable and estado == "HALLAZGO" else "media"
        ),
        causa_raiz=root_cause,
        evidencia=list(evidencia or []),
        recomendacion=recommendation,
        archivo=chequeo.archivo,
        ruta=chequeo.ruta,
        metodo=str(chequeo.metodo or "").upper() or None,
        estado_control=estado_control,
        fingerprint=_semantic_fingerprint(
            cfg,
            chequeo,
            family,
            root_cause,
        ),
        componente=(
            chequeo.componente
            or chequeo.archivo
            or str((chequeo.metadata or {}).get("componente") or "")
            or None
        ),
        parametro=chequeo.parametro,
        autogenerado=bool(chequeo.autogenerado),
        archivos_fuente=list(
            dict.fromkeys(
                [
                    *list(chequeo.archivos_fuente or []),
                    *([chequeo.archivo] if chequeo.archivo else []),
                ]
            )
        ),
        endpoints_afectados=list(
            dict.fromkeys(
                endpoints_afectados
                or ([chequeo.ruta] if chequeo.ruta else [])
            )
        ),
        casos_prueba=list(casos_prueba or []),
        configuracion_detectada=dict(configuracion or {}),
        estrategia_correccion=recipe,
        verificacion=verification,
    )


Evaluator = Callable[
    [ConfigObjetivo, ChequeoPilar2, Path | None],
    ResultadoPilar2,
]
_EVALUATORS: dict[str, Evaluator] = {}


def register_pilar2_evaluator(*types: str):
    """Registra nuevos tipos de prueba sin ampliar un bloque if/else."""

    def decorator(func: Evaluator) -> Evaluator:
        for type_name in types:
            _EVALUATORS[type_name] = func
        return func

    return decorator


def _http_observation(
    *,
    label: str,
    origin: str,
    response: Any,
) -> dict[str, Any]:
    headers = response.headers
    return {
        "tipo": "http_runtime",
        "prueba": label,
        "origin_enviado": origin,
        "http_status": response.status_code,
        "access_control_allow_origin": headers.get(
            "Access-Control-Allow-Origin"
        ),
        "access_control_allow_credentials": str(
            headers.get("Access-Control-Allow-Credentials", "")
        ).lower(),
        "access_control_allow_headers": headers.get(
            "Access-Control-Allow-Headers"
        ),
        "access_control_allow_methods": headers.get(
            "Access-Control-Allow-Methods"
        ),
        "vary": headers.get("Vary"),
    }


def _cors_reasons(observation: dict[str, Any]) -> list[str]:
    origin = str(observation.get("origin_enviado") or "")
    acao = str(observation.get("access_control_allow_origin") or "")
    credentials = (
        str(
            observation.get("access_control_allow_credentials")
            or ""
        ).lower()
        == "true"
    )
    allowed_headers = str(
        observation.get("access_control_allow_headers") or ""
    ).lower()
    reasons: list[str] = []

    reflected = bool(origin and acao == origin)
    if reflected and credentials:
        reasons.append("reflexion_origin_con_credenciales")
    if reflected and "authorization" in allowed_headers:
        reasons.append("reflexion_origin_con_authorization")
    if origin == "null" and acao == "null" and credentials:
        reasons.append("origin_null_con_credenciales")
    if acao == "*" and credentials:
        reasons.append("wildcard_con_credenciales")
    return reasons


@register_pilar2_evaluator("cors_reflection", "cors_policy")
def _cors(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    _source_root: Path | None,
) -> ResultadoPilar2:
    cuenta = _cuenta(cfg, chequeo.cuenta)
    origin = dict(chequeo.headers).get(
        "Origin",
        "https://origen-no-autorizado.example",
    )
    url = cfg.base_url + chequeo.ruta
    observations: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []

    response = request_http(
        chequeo.metodo or "GET",
        url,
        cuenta=cuenta,
        headers={**dict(chequeo.headers), "Origin": origin},
        cuerpo=None,
        timeout=10,
    )
    observations.append(
        _http_observation(
            label="cors_origin_externo",
            origin=origin,
            response=response,
        )
    )
    cases.append(
        {
            "tipo": "runtime",
            "metodo": str(chequeo.metodo or "GET").upper(),
            "ruta": chequeo.ruta,
            "origin": origin,
        }
    )

    extra_requests = [
        (
            "cors_preflight",
            "OPTIONS",
            origin,
            {
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        ),
        (
            "cors_origin_null",
            str(chequeo.metodo or "GET").upper(),
            "null",
            {"Origin": "null"},
        ),
    ]

    parsed = urlparse(cfg.base_url)
    host = parsed.hostname or "target.local"
    boundary_origin = f"https://{host}.attacker.example"
    extra_requests.append(
        (
            "cors_origin_borde_dominio",
            str(chequeo.metodo or "GET").upper(),
            boundary_origin,
            {"Origin": boundary_origin},
        )
    )

    for label, method, sent_origin, headers in extra_requests:
        try:
            extra = request_http(
                method,
                url,
                cuenta=cuenta,
                headers=headers,
                cuerpo=None,
                timeout=10,
            )
            observations.append(
                _http_observation(
                    label=label,
                    origin=sent_origin,
                    response=extra,
                )
            )
            cases.append(
                {
                    "tipo": "runtime",
                    "metodo": method,
                    "ruta": chequeo.ruta,
                    "origin": sent_origin,
                }
            )
        except Exception as exc:
            observations.append(
                {
                    "tipo": "http_runtime",
                    "prueba": label,
                    "origin_enviado": sent_origin,
                    "error": exc.__class__.__name__,
                }
            )

    reasons: list[str] = []
    for item in observations:
        reasons.extend(_cors_reasons(item))
    reasons = list(dict.fromkeys(reasons))
    vulnerable = bool(reasons)
    vary_values = [
        str(item.get("vary") or "")
        for item in observations
        if item.get("vary") is not None
    ]
    vary_origin = any(
        "origin" in value.lower()
        for value in vary_values
    )

    detail = (
        f"CORS probado en {chequeo.ruta}; "
        f"condiciones inseguras={reasons or 'ninguna'}; "
        f"Vary: Origin observado={vary_origin}"
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable=vulnerable,
        estado="HALLAZGO" if vulnerable else "SIN_HALLAZGO",
        estado_control="vulnerable" if vulnerable else "seguro",
        detalle=detail,
        http_status=response.status_code,
        evidencia=observations,
        confianza="alta" if vulnerable else "alta",
        configuracion={
            "vary_origin": vary_origin,
            "condiciones_inseguras": reasons,
        },
        casos_prueba=cases,
        endpoints_afectados=[chequeo.ruta],
    )


@register_pilar2_evaluator("http_status_policy")
def _http_status_policy(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    _source_root: Path | None,
) -> ResultadoPilar2:
    cuenta = _cuenta(cfg, chequeo.cuenta)
    response = request_http(
        chequeo.metodo,
        cfg.base_url + chequeo.ruta,
        cuenta=cuenta,
        headers=chequeo.headers,
        cuerpo=_preparar_cuerpo(chequeo),
        timeout=15,
    )
    safe_codes = list(chequeo.codigos_seguros)
    vulnerable = response.status_code not in chequeo.codigos_seguros
    detail = (
        f"HTTP observado={response.status_code}; "
        f"códigos seguros esperados={safe_codes}"
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable=vulnerable,
        estado="HALLAZGO" if vulnerable else "SIN_HALLAZGO",
        estado_control="vulnerable" if vulnerable else "seguro",
        detalle=detail,
        http_status=response.status_code,
        evidencia=[
            {
                "tipo": "http_runtime",
                "http_status": response.status_code,
                "codigos_seguros": safe_codes,
                "familia": _familia(chequeo),
            }
        ],
        confianza="alta",
        casos_prueba=[
            {
                "tipo": "runtime",
                "metodo": chequeo.metodo,
                "ruta": chequeo.ruta,
                "cuenta": chequeo.cuenta,
            }
        ],
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _static_result(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    *,
    unsafe: bool,
    safe: bool,
    detail: str,
    evidence: dict[str, Any],
) -> ResultadoPilar2:
    family = _familia(chequeo)
    observed = unsafe and not safe
    # Un bypass inferido solamente por código es hipótesis; necesita prueba
    # diferencial de identidad/política antes de ser vulnerabilidad.
    if family == "LIMIT_BYPASS" and observed:
        return _resultado(
            cfg,
            chequeo,
            vulnerable=False,
            estado="POR_CONFIRMAR",
            estado_control="por_confirmar",
            detalle=detail,
            evidencia=[evidence],
            confianza=chequeo.confianza or "media",
        )

    vulnerable = observed
    confidence = chequeo.confianza or (
        "media-alta"
        if family in {"SECRET", "DEBUG", "SESSION"}
        else "media"
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable=vulnerable,
        estado="HALLAZGO" if vulnerable else "SIN_HALLAZGO",
        estado_control="vulnerable" if vulnerable else "seguro",
        detalle=detail,
        evidencia=[evidence],
        confianza=confidence,
    )


@register_pilar2_evaluator("source_contains")
def _source_contains(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    source_root: Path | None,
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para inspección estática"
        )
    if not chequeo.archivo or not chequeo.patron_inseguro:
        raise ValueError(
            f"{chequeo.id_control}: archivo/patron_inseguro son obligatorios"
        )

    path = source_root / chequeo.archivo
    text = path.read_text(encoding="utf-8", errors="ignore")
    unsafe_offset = text.find(chequeo.patron_inseguro)
    safe_offset = (
        text.find(chequeo.patron_seguro)
        if chequeo.patron_seguro
        else -1
    )
    unsafe = unsafe_offset >= 0
    safe = safe_offset >= 0
    unsafe_line = _line_number(text, unsafe_offset) if unsafe else None
    safe_line = _line_number(text, safe_offset) if safe else None
    detail = (
        f"archivo={chequeo.archivo}; condición insegura={unsafe}"
        + (f" línea={unsafe_line}" if unsafe_line else "")
        + f"; condición segura={safe}"
        + (f" línea_segura={safe_line}" if safe_line else "")
    )
    return _static_result(
        cfg,
        chequeo,
        unsafe=unsafe,
        safe=safe,
        detail=detail,
        evidence={
            "tipo": "fuente_estatica",
            "archivo": chequeo.archivo,
            "condicion_insegura_presente": unsafe,
            "linea_insegura": unsafe_line,
            "condicion_segura_presente": safe,
            "linea_segura": safe_line,
        },
    )


@register_pilar2_evaluator("source_regex")
def _source_regex(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    source_root: Path | None,
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para inspección estática"
        )
    if not chequeo.archivo or not chequeo.patron_inseguro:
        raise ValueError(
            f"{chequeo.id_control}: archivo/patron_inseguro son obligatorios"
        )

    path = source_root / chequeo.archivo
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        unsafe_match = re.search(
            chequeo.patron_inseguro,
            text,
            re.I | re.M | re.S,
        )
        safe_match = (
            re.search(
                chequeo.patron_seguro,
                text,
                re.I | re.M | re.S,
            )
            if chequeo.patron_seguro
            else None
        )
    except re.error as exc:
        raise ValueError(
            f"{chequeo.id_control}: regex inválida: {exc}"
        ) from exc

    unsafe = unsafe_match is not None
    safe = safe_match is not None
    unsafe_line = (
        _line_number(text, unsafe_match.start())
        if unsafe_match
        else None
    )
    safe_line = (
        _line_number(text, safe_match.start())
        if safe_match
        else None
    )
    detail = (
        f"archivo={chequeo.archivo}; regex insegura presente={unsafe}"
        + (f" en línea {unsafe_line}" if unsafe_line else "")
        + f"; regex segura presente={safe}"
        + (f" en línea {safe_line}" if safe_line else "")
    )
    return _static_result(
        cfg,
        chequeo,
        unsafe=unsafe,
        safe=safe,
        detail=detail,
        evidence={
            "tipo": "fuente_estatica",
            "archivo": chequeo.archivo,
            "regex_insegura_presente": unsafe,
            "linea_insegura": unsafe_line,
            "regex_segura_presente": safe,
            "linea_segura": safe_line,
        },
    )


@register_pilar2_evaluator("secret_fallback")
def _secret_fallback(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    source_root: Path | None,
) -> ResultadoPilar2:
    if source_root is None or not chequeo.archivo:
        raise ValueError(
            f"{chequeo.id_control} requiere archivo y --target-root"
        )
    path = source_root / chequeo.archivo
    findings = analyze_secret_file(path, relative=chequeo.archivo)
    variable = str((chequeo.metadata or {}).get("variable") or "")
    expected_line = int((chequeo.metadata or {}).get("linea") or 0)

    matched = [
        item
        for item in findings
        if (not variable or str(item.get("variable") or "") == variable)
        and (
            not expected_line
            or int(item.get("linea") or 0) == expected_line
        )
    ]
    if not matched:
        return _resultado(
            cfg,
            chequeo,
            vulnerable=False,
            estado="SIN_HALLAZGO",
            estado_control="seguro",
            detalle=(
                "El fallback inseguro que originó el control ya no se "
                "encuentra en el flujo de configuración."
            ),
            evidencia=[
                {
                    "tipo": "fuente_estatica",
                    "archivo": chequeo.archivo,
                    "variable": variable or None,
                    "coincidencia": False,
                }
            ],
            confianza="media-alta",
        )

    evidence = matched[0]
    production_reachable = bool(
        evidence.get("produccion_puede_usar_fallback")
    )
    if production_reachable:
        state = "HALLAZGO"
        control_state = "vulnerable"
        vulnerable = True
        confidence = "media-alta"
    else:
        state = "POR_CONFIRMAR"
        control_state = "por_confirmar"
        vulnerable = False
        confidence = "baja"

    detail = (
        f"archivo={chequeo.archivo}; variable={evidence.get('variable')}; "
        f"línea={evidence.get('linea')}; producción puede usar fallback="
        f"{production_reachable}; valor={evidence.get('valor_fallback_redactado')}"
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable=vulnerable,
        estado=state,
        estado_control=control_state,
        detalle=detail,
        evidencia=[{"tipo": "flujo_configuracion", **evidence}],
        confianza=confidence,
        configuracion={
            "variable": evidence.get("variable"),
            "tipo_fuente": evidence.get("tipo_fuente"),
            "guardia_desarrollo": evidence.get("guardia_desarrollo"),
            "guardia_produccion_fail_closed": evidence.get(
                "guardia_produccion_fail_closed"
            ),
        },
    )


@register_pilar2_evaluator("container_security", "docker_non_root")
def _container_security(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    source_root: Path | None,
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para analizar runtime"
        )
    analysis = analyze_container_security(
        source_root,
        chequeo.archivo or "Dockerfile",
    )
    runtime_state = str(analysis.get("estado_runtime") or "no_aplica")
    vulnerable = bool(analysis.get("vulnerable_confirmado"))

    if vulnerable:
        state = "HALLAZGO"
        control_state = "vulnerable"
    elif runtime_state == "confirmado_non_root":
        state = "SIN_HALLAZGO"
        control_state = "seguro"
    elif runtime_state == "probable_root":
        state = "POR_CONFIRMAR"
        control_state = "por_confirmar"
    else:
        state = "NO_APLICABLE"
        control_state = "no_aplicable"

    detail = (
        f"runtime={runtime_state}; usuario_efectivo="
        f"{analysis.get('usuario_efectivo')!r}; "
        f"fuente={analysis.get('fuente_usuario_efectivo')!r}; "
        f"configuraciones_peligrosas="
        f"{len(analysis.get('configuraciones_peligrosas') or [])}"
    )
    sources = []
    docker = analysis.get("dockerfile") or {}
    if docker.get("archivo"):
        sources.append(docker.get("archivo"))
    sources.extend(
        item.get("archivo")
        for item in analysis.get("compose") or []
        if item.get("archivo")
    )
    sources.extend(
        item.get("archivo")
        for item in analysis.get("kubernetes") or []
        if item.get("archivo")
    )
    chequeo.archivos_fuente = list(
        dict.fromkeys([*chequeo.archivos_fuente, *sources])
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable=vulnerable,
        estado=state,
        estado_control=control_state,
        detalle=detail,
        evidencia=[
            {
                "tipo": "runtime_container_estatico",
                "estado_runtime": runtime_state,
                "usuario_efectivo": analysis.get("usuario_efectivo"),
                "fuente_usuario_efectivo": analysis.get(
                    "fuente_usuario_efectivo"
                ),
                "configuraciones_peligrosas": analysis.get(
                    "configuraciones_peligrosas"
                ),
                "dockerfile": analysis.get("dockerfile"),
                "compose": analysis.get("compose"),
                "kubernetes": analysis.get("kubernetes"),
            }
        ],
        confianza=str(analysis.get("confianza") or "media"),
        configuracion=analysis,
    )


@register_pilar2_evaluator("limit_differential")
def _limit_differential(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    _source_root: Path | None,
) -> ResultadoPilar2:
    cases = list((chequeo.metadata or {}).get("casos") or [])
    if not cases:
        return _resultado(
            cfg,
            chequeo,
            vulnerable=False,
            estado="NO_EJECUTABLE",
            estado_control="no_ejecutable",
            detalle=(
                "La hipótesis LIMIT requiere casos diferenciales derivados de "
                "evidencia; Aegis no inventará payloads ni identidades."
            ),
            evidencia=[
                {
                    "tipo": "seguridad_prueba",
                    "motivo": "faltan casos diferenciales seguros",
                }
            ],
            confianza="media",
        )

    observations: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        method = str(case.get("metodo") or chequeo.metodo or "GET").upper()
        body = case.get("cuerpo")
        if method in {"POST", "PUT", "PATCH"} and not isinstance(body, dict):
            continue
        if method == "DELETE":
            continue
        account_name = case.get("cuenta")
        account = _cuenta(cfg, account_name) if account_name else None
        route = str(case.get("ruta") or chequeo.ruta)
        response = request_http(
            method,
            cfg.base_url + route,
            cuenta=account,
            headers=dict(case.get("headers") or {}),
            cuerpo=body if isinstance(body, dict) else None,
            timeout=15,
        )
        observations.append(
            {
                "tipo": "http_runtime_diferencial",
                "etiqueta": case.get("etiqueta"),
                "clase": case.get("clase"),
                "cuenta": account_name,
                "metodo": method,
                "ruta": route,
                "http_status": response.status_code,
                "aceptado": 200 <= response.status_code < 300,
            }
        )

    low_special = next(
        (
            item
            for item in observations
            if item.get("clase") == "especial_no_privilegiado"
        ),
        None,
    )
    privileged_special = next(
        (
            item
            for item in observations
            if item.get("clase") == "especial_privilegiado"
        ),
        None,
    )
    capability_privileged = bool(
        (chequeo.metadata or {}).get("capacidad_privilegiada", True)
    )
    vulnerable = bool(
        capability_privileged
        and low_special
        and low_special.get("aceptado")
        and (
            privileged_special is None
            or privileged_special.get("aceptado")
        )
    )
    if not low_special:
        return _resultado(
            cfg,
            chequeo,
            vulnerable=False,
            estado="NO_EJECUTABLE",
            estado_control="no_ejecutable",
            detalle=(
                "No existe un caso especial no privilegiado ejecutable; "
                "la hipótesis no puede confirmarse."
            ),
            evidencia=observations,
            confianza="media",
        )

    return _resultado(
        cfg,
        chequeo,
        vulnerable=vulnerable,
        estado="HALLAZGO" if vulnerable else "SIN_HALLAZGO",
        estado_control="vulnerable" if vulnerable else "seguro",
        detalle=(
            "Prueba diferencial de excepción completada; "
            f"bypass no privilegiado aceptado={bool(low_special.get('aceptado'))}; "
            f"capacidad declarada privilegiada={capability_privileged}"
        ),
        http_status=low_special.get("http_status"),
        evidencia=observations,
        confianza="alta",
        casos_prueba=[
            {
                key: item.get(key)
                for key in (
                    "etiqueta", "clase", "cuenta", "metodo", "ruta",
                    "http_status",
                )
            }
            for item in observations
        ],
    )


def auditar_pilar2(
    cfg: ConfigObjetivo,
    source_root: str | Path | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[ResultadoPilar2]:
    root = Path(source_root).resolve() if source_root else None
    results: list[ResultadoPilar2] = []

    for check in cfg.chequeos_pilar2:
        evaluator = _EVALUATORS.get(str(check.tipo or ""))
        if evaluator is None:
            family = _familia(check)
            severity, root_cause, recommendation = _family_defaults(family)
            result = ResultadoPilar2(
                sistema=cfg.sistema,
                id_control=check.id_control,
                nombre=check.nombre,
                tipo=check.tipo,
                vulnerable=False,
                estado="NO_EJECUTABLE",
                detalle=f"tipo de control no registrado: {check.tipo}",
                http_status=None,
                ts=_ts(),
                familia=family,
                severidad=severity,
                confianza="baja",
                causa_raiz=check.causa_raiz or root_cause,
                evidencia=[
                    {
                        "tipo": "motor",
                        "motivo": "evaluador no registrado",
                    }
                ],
                recomendacion=recommendation,
                archivo=check.archivo,
                ruta=check.ruta,
                metodo=str(check.metodo or "").upper() or None,
                estado_control="no_ejecutable",
                fingerprint=_semantic_fingerprint(
                    cfg,
                    check,
                    family,
                    check.causa_raiz or root_cause,
                ),
                componente=check.componente or check.archivo,
                parametro=check.parametro,
                autogenerado=bool(check.autogenerado),
                archivos_fuente=list(check.archivos_fuente or []),
                estrategia_correccion=_abstract_recipe(family),
                verificacion={
                    "obligatoria": True,
                    "regresion": True,
                },
            )
        else:
            try:
                result = evaluator(cfg, check, root)
            except Exception as exc:
                family = _familia(check)
                severity, root_cause, recommendation = _family_defaults(family)
                result = ResultadoPilar2(
                    sistema=cfg.sistema,
                    id_control=check.id_control,
                    nombre=check.nombre,
                    tipo=check.tipo,
                    vulnerable=False,
                    estado="ERROR",
                    detalle=str(exc),
                    http_status=None,
                    ts=_ts(),
                    familia=family,
                    severidad=severity,
                    confianza="baja",
                    causa_raiz=check.causa_raiz or root_cause,
                    evidencia=[
                        {
                            "tipo": "error_ejecucion",
                            "error": exc.__class__.__name__,
                        }
                    ],
                    recomendacion=recommendation,
                    archivo=check.archivo,
                    ruta=check.ruta,
                    metodo=str(check.metodo or "").upper() or None,
                    estado_control="error",
                    fingerprint=_semantic_fingerprint(
                        cfg,
                        check,
                        family,
                        check.causa_raiz or root_cause,
                    ),
                    componente=check.componente or check.archivo,
                    parametro=check.parametro,
                    autogenerado=bool(check.autogenerado),
                    archivos_fuente=list(check.archivos_fuente or []),
                    estrategia_correccion=_abstract_recipe(family),
                    verificacion={
                        "obligatoria": True,
                        "regresion": True,
                    },
                )

        results.append(result)
        if progress_callback:
            progress_callback(
                "Pilar 2 · "
                f"{check.nombre} · {result.estado}"
            )

    return results