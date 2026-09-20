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
    control_id = str(chequeo.id_control or "").upper()
    tipo = str(chequeo.tipo or "").lower()
    nombre = str(chequeo.nombre or "").lower()
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
    if any(token in joined for token in ("bypass", "limit", "limite", "quota", "cuota")):
        return "LIMIT_BYPASS"
    return "GENERIC"


def _metadata_hallazgo(chequeo: ChequeoPilar2) -> tuple[str, str, str, str]:
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
    severity, root_cause, recommendation = data.get(family, data["GENERIC"])
    return family, severity, root_cause, recommendation


def _resultado(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    vulnerable: bool,
    detalle: str,
    http_status: int | None = None,
    *,
    evidencia: list[dict[str, Any]] | None = None,
    confianza: str = "alta",
) -> ResultadoPilar2:
    family, severity, root_cause, recommendation = _metadata_hallazgo(chequeo)
    return ResultadoPilar2(
        sistema=cfg.sistema,
        id_control=chequeo.id_control,
        nombre=chequeo.nombre,
        tipo=chequeo.tipo,
        vulnerable=vulnerable,
        estado="HALLAZGO" if vulnerable else "SIN_HALLAZGO",
        detalle=detalle,
        http_status=http_status,
        ts=_ts(),
        familia=family,
        severidad=severity,
        confianza=confianza,
        causa_raiz=root_cause,
        evidencia=list(evidencia or []),
        recomendacion=recommendation,
        archivo=chequeo.archivo,
        ruta=chequeo.ruta,
        metodo=str(chequeo.metodo or "").upper() or None,
    )


def _cors(cfg: ConfigObjetivo, chequeo: ChequeoPilar2) -> ResultadoPilar2:
    headers = dict(chequeo.headers)
    origen = headers.setdefault("Origin", "https://origen-no-autorizado.example")
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
    cred = resp.headers.get("Access-Control-Allow-Credentials", "").lower()
    vulnerable = acao == origen and cred == "true"
    detalle = (
        f"Origin no autorizado enviado={origen}; ACAO observado={acao!r}; "
        f"Allow-Credentials={cred!r}; HTTP={resp.status_code}"
    )
    evidencia = [
        {
            "tipo": "http_runtime",
            "prueba": "cors_origen_no_autorizado",
            "origin_enviado": origen,
            "access_control_allow_origin": acao,
            "access_control_allow_credentials": cred,
            "http_status": resp.status_code,
        }
    ]
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detalle,
        resp.status_code,
        evidencia=evidencia,
    )


def _http_status_policy(
    cfg: ConfigObjetivo, chequeo: ChequeoPilar2
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
        f"HTTP observado={resp.status_code}; códigos seguros esperados={safe_codes}"
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
    cfg: ConfigObjetivo, chequeo: ChequeoPilar2, source_root: Path | None
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
    texto = ruta.read_text(encoding="utf-8", errors="ignore")
    insecure_offset = texto.find(chequeo.patron_inseguro)
    safe_offset = (
        texto.find(chequeo.patron_seguro)
        if chequeo.patron_seguro
        else -1
    )
    inseguro = insecure_offset >= 0
    seguro = safe_offset >= 0
    vulnerable = inseguro and not seguro
    insecure_line = _line_number(texto, insecure_offset) if inseguro else None
    safe_line = _line_number(texto, safe_offset) if seguro else None
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
    texto = ruta.read_text(encoding="utf-8", errors="ignore")

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


def _docker_non_root(
    cfg: ConfigObjetivo, chequeo: ChequeoPilar2, source_root: Path | None
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para inspección estática"
        )
    archivo = chequeo.archivo or "Dockerfile"
    texto = (source_root / archivo).read_text(encoding="utf-8", errors="ignore")
    usuarios = re.findall(r"(?im)^\s*USER\s+([^\s#]+)", texto)
    imagenes = re.findall(r"(?im)^\s*FROM\s+([^\s]+)", texto)
    usuario = usuarios[-1] if usuarios else None
    imagen = imagenes[-1] if imagenes else None
    vulnerable = usuario is None or usuario.lower() in {"root", "0"}
    detalle = (
        f"archivo={archivo}; imagen efectiva={imagen!r}; "
        f"USER efectivo declarado={usuario!r}"
    )
    return _resultado(
        cfg,
        chequeo,
        vulnerable,
        detalle,
        evidencia=[
            {
                "tipo": "fuente_estatica",
                "archivo": archivo,
                "imagen_efectiva": imagen,
                "usuario_efectivo": usuario,
                "usuario_no_privilegiado": not vulnerable,
            }
        ],
        confianza="alta" if usuario is not None else "media",
    )


def auditar_pilar2(
    cfg: ConfigObjetivo,
    source_root: str | Path | None = None,