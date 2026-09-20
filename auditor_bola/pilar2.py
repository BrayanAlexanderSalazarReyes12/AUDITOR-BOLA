"""Motor determinista del Pilar 2: Arquitectura y Configuración."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import ChequeoPilar2, ConfigObjetivo
from .transport import request_http


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
    confianza: str = "alta"
    causa_raiz: str = "configuracion_insegura"
    evidencia: list[dict[str, Any]] = field(default_factory=list)
    recomendacion: str | None = None
    archivo: str | None = None
    ruta: str | None = None
    metodo: str | None = None
    componente: str | None = None
    origen: str | None = None
    configuracion_detectada: dict[str, Any] = field(default_factory=dict)
    casos_prueba: list[dict[str, Any]] = field(default_factory=list)

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
            "COOKIE": "SESSION",
            "BYPASS": "LIMIT_BYPASS",
        }
        return aliases.get(explicit, explicit)
    control_id = str(chequeo.id_control or "")
    tipo = str(chequeo.tipo or "")
    nombre = str(chequeo.nombre or "")
    joined = f"{control_id} {tipo} {nombre}".lower()

    if "cors" in joined:
        return "CORS"
    if any(token in joined for token in ("secret", "token", "api_key", "api-key")):
        return "SECRET"
    if any(token in joined for token in ("docker", "container", "contenedor")):
        return "CONTAINER"
    if "debug" in joined:
        return "DEBUG"
    if any(token in joined for token in ("cookie", "session", "sesion")):
        return "SESSION"
    if any(
        token in joined
        for token in ("bypass", "limit", "limite", "quota", "cuota")
    ):
        return "LIMIT_BYPASS"
    return "GENERIC"


def _metadata_hallazgo(
    chequeo: ChequeoPilar2,
) -> tuple[str, str, str, str]:
    family = _familia(chequeo)
    data = {
        "CORS": (
            "ALTA",
            "politica_cors",
            "Restringir Access-Control-Allow-Origin a una allowlist explícita y "
            "habilitar credenciales solo para orígenes confiables.",
        ),
        "SECRET": (
            "ALTA",
            "gestion_secretos",
            "Eliminar secretos o fallbacks predecibles del código y obtenerlos "
            "desde un gestor de secretos o variables de entorno obligatorias.",
        ),
        "CONTAINER": (
            "MEDIA",
            "privilegios_contenedor",
            "Ejecutar el contenedor con un usuario no privilegiado y limitar "
            "capabilities, permisos y montajes al mínimo necesario.",
        ),
        "DEBUG": (
            "MEDIA",
            "configuracion_debug",
            "Deshabilitar debug en configuraciones desplegables y separar "
            "claramente configuración de desarrollo y producción.",
        ),
        "SESSION": (
            "MEDIA",
            "configuracion_sesion",
            "Configurar cookies de sesión con Secure, HttpOnly y SameSite "
            "apropiados para el flujo de autenticación.",
        ),
        "LIMIT_BYPASS": (
            "ALTA",
            "autorizacion_excepcion_limites",
            "Proteger cualquier excepción de límites con autorización explícita "
            "y registrar el uso de la vía excepcional.",
        ),
        "GENERIC": (
            "MEDIA",
            "configuracion_insegura",
            "Corregir la condición insegura observada y repetir la prueba para "
            "verificar que el control queda efectivo.",
        ),
    }
    severity, root_cause, recommendation = data.get(
        family,
        data["GENERIC"],
    )
    return family, severity, root_cause, recommendation


def _resultado(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    vulnerable: bool,
    detalle: str,
    http_status: int | None = None,
    *,
    evidencia: list[dict[str, Any]] | None = None,
    confianza: str | None = None,
    estado: str | None = None,
    configuracion_detectada: dict[str, Any] | None = None,
    casos_prueba: list[dict[str, Any]] | None = None,
) -> ResultadoPilar2:
    family, severity, root_cause, recommendation = _metadata_hallazgo(
        chequeo
    )
    return ResultadoPilar2(
        sistema=cfg.sistema,
        id_control=chequeo.id_control,
        nombre=chequeo.nombre,
        tipo=chequeo.tipo,
        vulnerable=vulnerable,
        estado=estado or ("HALLAZGO" if vulnerable else "SIN_HALLAZGO"),
        detalle=detalle,
        http_status=http_status,
        ts=_ts(),
        familia=family,
        severidad=severity,
        confianza=(
            confianza
            or chequeo.confianza_inicial
            or ("alta" if vulnerable else "media-alta")
        ),
        causa_raiz=root_cause,
        evidencia=list(evidencia or []),
        recomendacion=recommendation,
        archivo=chequeo.archivo,
        ruta=chequeo.ruta,
        metodo=str(chequeo.metodo or "").upper() or None,
        componente=chequeo.componente or chequeo.archivo,
        origen=chequeo.origen,
        configuracion_detectada=dict(configuracion_detectada or {}),
        casos_prueba=list(casos_prueba or []),
    )


def _cors(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
) -> ResultadoPilar2:
    headers = dict(chequeo.headers)
    origen = headers.setdefault(
        "Origin",
        "https://origen-no-autorizado.example",
    )
    cuenta = _cuenta(cfg, chequeo.cuenta)
    resp = request_http(
        chequeo.metodo,
        cfg.base_url + chequeo.ruta,
        cuenta=cuenta,
        headers=headers,
        cuerpo=_preparar_cuerpo(chequeo),
        timeout=10,
    )
    acao = resp.headers.get("Access-Control-Allow-Origin")
    cred = str(
        resp.headers.get("Access-Control-Allow-Credentials", "")
    ).lower()
    vary = str(resp.headers.get("Vary", ""))
    allow_methods = str(
        resp.headers.get("Access-Control-Allow-Methods", "")
    )
    allow_headers = str(
        resp.headers.get("Access-Control-Allow-Headers", "")
    )

    preflight = None
    preflight_error = None
    try:
        pre_headers = {
            "Origin": origen,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type, authorization",
        }
        preflight = request_http(
            "OPTIONS",
            cfg.base_url + chequeo.ruta,
            cuenta=cuenta,
            headers=pre_headers,
            timeout=10,
        )
    except Exception as exc:  # la ausencia de OPTIONS no invalida la sonda GET
        preflight_error = exc.__class__.__name__

    pre_acao = (
        preflight.headers.get("Access-Control-Allow-Origin")
        if preflight is not None
        else None
    )
    pre_cred = (
        str(
            preflight.headers.get(
                "Access-Control-Allow-Credentials",
                "",
            )
        ).lower()
        if preflight is not None
        else ""
    )

    reflected = acao == origen or pre_acao == origen
    wildcard_with_credentials = (
        (acao == "*" and cred == "true")
        or (pre_acao == "*" and pre_cred == "true")
    )
    credentialed_external_origin = (
        (acao == origen and cred == "true")
        or (pre_acao == origen and pre_cred == "true")
    )
    vulnerable = credentialed_external_origin or wildcard_with_credentials

    detalle = (
        f"Origin externo={origen}; ACAO={acao!r}; credenciales={cred!r}; "
        f"Vary={vary!r}; preflight_ACAO={pre_acao!r}; "
        f"preflight_credenciales={pre_cred!r}; HTTP={resp.status_code}"
    )
    evidencia = [
        {
            "tipo": "http_runtime",
            "prueba": "cors_origen_externo",
            "origin_enviado": origen,
            "access_control_allow_origin": acao,
            "access_control_allow_credentials": cred,
            "vary": vary,
            "allow_methods": allow_methods,
            "allow_headers": allow_headers,
            "http_status": resp.status_code,
            "origin_reflejado": reflected,
            "wildcard_con_credenciales": wildcard_with_credentials,
        },
        {
            "tipo": "http_runtime",
            "prueba": "cors_preflight",
            "origin_enviado": origen,
            "access_control_allow_origin": pre_acao,
            "access_control_allow_credentials": pre_cred,
            "http_status": (
                preflight.status_code
                if preflight is not None
                else None
            ),
            "error": preflight_error,
        },
    ]
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detalle,
        resp.status_code,
        evidencia=evidencia,
        confianza="alta" if vulnerable else "media-alta",
        configuracion_detectada={
            "origin_reflejado": reflected,
            "credenciales_externas": credentialed_external_origin,
            "wildcard_con_credenciales": wildcard_with_credentials,
            "vary_origin": "origin" in vary.lower(),
        },
        casos_prueba=[
            {
                "tipo": "GET_OR_HEAD",
                "ruta": chequeo.ruta,
                "origin": origen,
                "no_destructivo": True,
            },
            {
                "tipo": "OPTIONS_PREFLIGHT",
                "ruta": chequeo.ruta,
                "origin": origen,
                "no_destructivo": True,
            },
        ],
    )
def _http_status_policy(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
) -> ResultadoPilar2:
    cuenta = _cuenta(cfg, chequeo.cuenta)
    resp = request_http(
        chequeo.metodo,
        cfg.base_url + chequeo.ruta,
        cuenta=cuenta,
        headers=chequeo.headers,
        cuerpo=_preparar_cuerpo(chequeo),
        timeout=15,
    )
    safe_codes = list(chequeo.codigos_seguros)
    vulnerable = resp.status_code not in chequeo.codigos_seguros
    detalle = (
        f"HTTP observado={resp.status_code}; códigos seguros esperados="
        f"{safe_codes}"
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detalle,
        resp.status_code,
        evidencia=[
            {
                "tipo": "http_runtime",
                "http_status": resp.status_code,
                "codigos_seguros": safe_codes,
            }
        ],
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


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

    ruta = source_root / chequeo.archivo
    texto = ruta.read_text(
        encoding="utf-8",
        errors="ignore",
    )
    insecure_offset = texto.find(chequeo.patron_inseguro)
    safe_offset = (
        texto.find(chequeo.patron_seguro)
        if chequeo.patron_seguro
        else -1
    )
    inseguro = insecure_offset >= 0
    seguro = safe_offset >= 0
    vulnerable = inseguro and not seguro

    insecure_line = (
        _line_number(texto, insecure_offset)
        if inseguro
        else None
    )
    safe_line = (
        _line_number(texto, safe_offset)
        if seguro
        else None
    )
    detalle = (
        f"archivo={chequeo.archivo}; patrón inseguro presente={inseguro}"
        + (f" en línea {insecure_line}" if insecure_line else "")
        + f"; patrón seguro presente={seguro}"
        + (f" en línea {safe_line}" if safe_line else "")
    )

    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detalle,
        evidencia=[
            {
                "tipo": "fuente_estatica",
                "archivo": chequeo.archivo,
                "patron_inseguro_presente": inseguro,
                "linea_insegura": insecure_line,
                "patron_seguro_presente": seguro,
                "linea_segura": safe_line,
            }
        ],
    )


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

    ruta = source_root / chequeo.archivo
    texto = ruta.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    try:
        insecure_match = re.search(
            chequeo.patron_inseguro,
            texto,
            re.I | re.M | re.S,
        )
        safe_match = (
            re.search(
                chequeo.patron_seguro,
                texto,
                re.I | re.M | re.S,
            )
            if chequeo.patron_seguro
            else None
        )
    except re.error as exc:
        raise ValueError(
            f"{chequeo.id_control}: regex inválida: {exc}"
        ) from exc

    inseguro = insecure_match is not None
    seguro = safe_match is not None
    vulnerable = inseguro and not seguro

    insecure_line = (
        _line_number(texto, insecure_match.start())
        if insecure_match
        else None
    )
    safe_line = (
        _line_number(texto, safe_match.start())
        if safe_match
        else None
    )
    detalle = (
        f"archivo={chequeo.archivo}; regex insegura presente={inseguro}"
        + (f" en línea {insecure_line}" if insecure_line else "")
        + f"; regex segura presente={seguro}"
        + (f" en línea {safe_line}" if safe_line else "")
    )

    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detalle,
        evidencia=[
            {
                "tipo": "fuente_estatica",
                "archivo": chequeo.archivo,
                "regex_insegura_presente": inseguro,
                "linea_insegura": insecure_line,
                "regex_segura_presente": seguro,
                "linea_segura": safe_line,
            }
        ],
    )


def _parse_docker_runtime(text: str) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        from_match = re.match(
            r"(?i)^FROM\\s+([^\\s]+)(?:\\s+AS\\s+([^\\s]+))?",
            line,
        )
        if from_match:
            current = {
                "image": from_match.group(1),
                "name": from_match.group(2),
                "user": None,
            }
            stages.append(current)
            continue
        user_match = re.match(r"(?i)^USER\\s+([^\\s#]+)", line)
        if user_match and current is not None:
            current["user"] = user_match.group(1)
    final = stages[-1] if stages else {
        "image": None,
        "name": None,
        "user": None,
    }
    return {
        "stages": stages,
        "stage_final": final,
        "usuario_efectivo_declarado": final.get("user"),
    }


def _runtime_manifest_evidence(
    source_root: Path,
    manifests: list[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for relative in manifests:
        path = source_root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lower = text.lower()
        item = {
            "archivo": relative,
            "privileged_true": bool(
                re.search(r"(?im)^\\s*privileged\\s*:\\s*true\\s*$", text)
            ),
            "run_as_user_0": bool(
                re.search(r"(?im)\\brunasuser\\s*:\\s*0\\b", text)
            ),
            "run_as_non_root_true": bool(
                re.search(r"(?im)\\brunasnonroot\\s*:\\s*true\\b", text)
            ),
            "run_as_non_root_false": bool(
                re.search(r"(?im)\\brunasnonroot\\s*:\\s*false\\b", text)
            ),
            "compose_user_root": bool(
                re.search(
                    r"(?im)^\\s*user\\s*:\\s*[\"']?(?:root|0(?::0)?)[\"']?\\s*$",
                    text,
                )
            ),
            "docker_socket_mount": "/var/run/docker.sock" in lower,
            "host_network": bool(
                re.search(r"(?im)\\bhostnetwork\\s*:\\s*true\\b", text)
            )
            or bool(
                re.search(r"(?im)^\\s*network_mode\\s*:\\s*host\\s*$", text)
            ),
            "host_pid": bool(
                re.search(r"(?im)\\bhostpid\\s*:\\s*true\\b", text)
            ),
            "dangerous_capability": bool(
                re.search(r"(?i)\\b(?:SYS_ADMIN|NET_ADMIN)\\b", text)
            ),
        }
        evidence.append(item)
    return evidence


def _docker_non_root(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    source_root: Path | None,
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para inspección estática"
        )

    archivo = chequeo.archivo or "Dockerfile"
    path = source_root / archivo
    texto = path.read_text(encoding="utf-8", errors="ignore")
    parsed = _parse_docker_runtime(texto)
    final = parsed["stage_final"]
    usuario = final.get("user")
    imagen = final.get("image")

    if usuario is None:
        return _resultado(
            cfg,
            chequeo,
            False,
            (
                f"archivo={archivo}; stage final={imagen!r}; USER no declarado; "
                "no se asume root sin resolver imagen/runtime efectivo"
            ),
            evidencia=[{
                "tipo": "contenedor_estatico",
                "archivo": archivo,
                **parsed,
            }],
            confianza="media",
            estado="POR_CONFIRMAR",
            configuracion_detectada=parsed,
        )

    vulnerable = str(usuario).lower() in {"root", "0", "0:0"}
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        (
            f"archivo={archivo}; imagen final={imagen!r}; "
            f"USER efectivo declarado={usuario!r}"
        ),
        evidencia=[{
            "tipo": "contenedor_estatico",
            "archivo": archivo,
            **parsed,
        }],
        confianza="alta",
        configuracion_detectada=parsed,
    )


def _container_runtime_policy(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    source_root: Path | None,
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para inspección estática"
        )
    archivo = chequeo.archivo or "Dockerfile"
    path = source_root / archivo
    text = path.read_text(encoding="utf-8", errors="ignore")
    parsed = _parse_docker_runtime(text)
    metadata = dict(chequeo.metadata or {})
    manifests = [
        str(item)
        for item in metadata.get("manifiestos_runtime") or []
    ]
    runtime_evidence = _runtime_manifest_evidence(
        source_root,
        manifests,
    )
    user = parsed["stage_final"].get("user")
    explicit_root = str(user or "").lower() in {"root", "0", "0:0"}
    runtime_insecure = any(
        item.get("privileged_true")
        or item.get("run_as_user_0")
        or item.get("run_as_non_root_false")
        or item.get("compose_user_root")
        or item.get("docker_socket_mount")
        or item.get("host_network")
        or item.get("host_pid")
        or item.get("dangerous_capability")
        for item in runtime_evidence
    )
    runtime_safe = any(
        item.get("run_as_non_root_true")
        for item in runtime_evidence
    )
    vulnerable = explicit_root or runtime_insecure

    if vulnerable:
        state = "HALLAZGO"
        confidence = "alta"
    elif user and str(user).lower() not in {"root", "0", "0:0"}:
        state = "SIN_HALLAZGO"
        confidence = "alta" if not runtime_evidence or runtime_safe else "media-alta"
    else:
        state = "POR_CONFIRMAR"
        confidence = "media"

    detail = (
        f"Dockerfile={archivo}; USER final={user!r}; "
        f"manifiestos runtime={len(runtime_evidence)}; "
        f"override inseguro={runtime_insecure}"
    )
    evidence = [{
        "tipo": "contenedor_estatico",
        "archivo": archivo,
        **parsed,
    }]
    evidence.extend(
        {"tipo": "runtime_manifest", **item}
        for item in runtime_evidence
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detail,
        evidencia=evidence,
        confianza=confidence,
        estado=state,
        configuracion_detectada={
            **parsed,
            "runtime": runtime_evidence,
        },
        casos_prueba=[{
            "tipo": "container_effective_policy",
            "dockerfile": archivo,
            "manifiestos": manifests,
            "no_destructivo": True,
        }],
    )


def _secret_fallback_context(
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
    offset = text.find(chequeo.patron_inseguro)
    present = offset >= 0
    metadata = dict(chequeo.metadata or {})
    production_signal = bool(metadata.get("senal_produccion"))
    variable = metadata.get("variable")
    line = (
        _line_number(text, offset)
        if present
        else metadata.get("linea")
    )

    # Una coincidencia estática aislada conserva la hipótesis pero no se
    # convierte en vulnerabilidad confirmada. Solo una señal de despliegue
    # productivo correlacionada eleva este control estático a hallazgo.
    vulnerable = bool(present and production_signal)
    state = (
        "HALLAZGO"
        if vulnerable
        else ("POR_CONFIRMAR" if present else "SIN_HALLAZGO")
    )
    confidence = (
        "media-alta"
        if vulnerable
        else ("media" if present else "alta")
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        (
            f"archivo={chequeo.archivo}; variable={variable!r}; "
            f"fallback presente={present}; señal producción={production_signal}; "
            f"línea={line}"
        ),
        evidencia=[{
            "tipo": "secreto_contextual",
            "archivo": chequeo.archivo,
            "linea": line,
            "variable": variable,
            "fallback_presente": present,
            "fallback_hash": metadata.get("fallback_hash"),
            "fallback_longitud": metadata.get("fallback_longitud"),
            "senal_produccion": production_signal,
            "valor_expuesto": False,
        }],
        confianza=confidence,
        estado=state,
        configuracion_detectada={
            "variable": variable,
            "fallback_presente": present,
            "senal_produccion": production_signal,
        },
    )
def auditar_pilar2(
    cfg: ConfigObjetivo,
    source_root: str | Path | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[ResultadoPilar2]:
    root = Path(source_root).resolve() if source_root else None
    resultados: list[ResultadoPilar2] = []

    for chequeo in cfg.chequeos_pilar2:
        try:
            if chequeo.tipo == "cors_reflection":
                resultado = _cors(
                    cfg,
                    chequeo,
                )
            elif chequeo.tipo == "http_status_policy":
                resultado = _http_status_policy(
                    cfg,
                    chequeo,
                )
            elif chequeo.tipo == "source_contains":
                resultado = _source_contains(
                    cfg,
                    chequeo,
                    root,
                )
            elif chequeo.tipo == "source_regex":
                resultado = _source_regex(
                    cfg,
                    chequeo,
                    root,
                )
            elif chequeo.tipo == "docker_non_root":
                resultado = _docker_non_root(
                    cfg,
                    chequeo,
                    root,
                )
            elif chequeo.tipo == "container_runtime_policy":
                resultado = _container_runtime_policy(
                    cfg,
                    chequeo,
                    root,
                )
            elif chequeo.tipo == "secret_fallback_context":
                resultado = _secret_fallback_context(
                    cfg,
                    chequeo,
                    root,
                )
            else:
                raise ValueError(
                    f"tipo de control no soportado: {chequeo.tipo}"
                )
        except Exception as exc:
            (
                family,
                severity,
                root_cause,
                recommendation,
            ) = _metadata_hallazgo(chequeo)
            resultado = ResultadoPilar2(
                sistema=cfg.sistema,
                id_control=chequeo.id_control,
                nombre=chequeo.nombre,
                tipo=chequeo.tipo,
                vulnerable=False,
                estado="ERROR",
                detalle=str(exc),
                http_status=None,
                ts=_ts(),
                familia=family,
                severidad=severity,
                confianza="baja",
                causa_raiz=root_cause,
                evidencia=[
                    {
                        "tipo": "error_ejecucion",
                        "error": exc.__class__.__name__,
                    }
                ],
                recomendacion=recommendation,
                archivo=chequeo.archivo,
                ruta=chequeo.ruta,
                metodo=str(chequeo.metodo or "").upper() or None,
                componente=chequeo.componente or chequeo.archivo,
                origen=chequeo.origen,
                configuracion_detectada=dict(chequeo.metadata or {}),
            )

        resultados.append(resultado)
        if progress_callback:
            progress_callback(
                "Pilar 2 · "
                f"{chequeo.nombre} · {resultado.estado}"
            )

    return resultados