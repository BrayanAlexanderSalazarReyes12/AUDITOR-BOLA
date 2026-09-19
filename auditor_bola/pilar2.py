"""Motor determinista del Pilar 2: Arquitectura y Configuración."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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


def _resultado(
    cfg: ConfigObjetivo,
    chequeo: ChequeoPilar2,
    vulnerable: bool,
    detalle: str,
    http_status: int | None = None,
) -> ResultadoPilar2:
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
        f"Origin enviado={origen}; Access-Control-Allow-Origin={acao!r}; "
        f"Allow-Credentials={cred!r}"
    )
    return _resultado(cfg, chequeo, vulnerable, detalle, resp.status_code)


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
    vulnerable = resp.status_code not in chequeo.codigos_seguros
    detalle = (
        f"HTTP observado={resp.status_code}; códigos seguros esperados="
        f"{list(chequeo.codigos_seguros)}"
    )
    return _resultado(cfg, chequeo, vulnerable, detalle, resp.status_code)


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
    texto = ruta.read_text(encoding="utf-8")
    inseguro = chequeo.patron_inseguro in texto
    seguro = bool(
        chequeo.patron_seguro and chequeo.patron_seguro in texto
    )
    vulnerable = inseguro and not seguro
    detalle = (
        f"archivo={chequeo.archivo}; patrón inseguro presente={inseguro}; "
        f"patrón seguro presente={seguro}"
    )
    return _resultado(cfg, chequeo, vulnerable, detalle)


def _docker_non_root(
    cfg: ConfigObjetivo, chequeo: ChequeoPilar2, source_root: Path | None
) -> ResultadoPilar2:
    if source_root is None:
        raise ValueError(
            f"{chequeo.id_control} requiere --target-root para inspección estática"
        )
    archivo = chequeo.archivo or "Dockerfile"
    texto = (source_root / archivo).read_text(encoding="utf-8")
    usuarios = re.findall(r"(?im)^\s*USER\s+([^\s#]+)", texto)
    usuario = usuarios[-1] if usuarios else None
    vulnerable = usuario is None or usuario.lower() in {"root", "0"}
    detalle = f"USER efectivo declarado={usuario!r}"
    return _resultado(cfg, chequeo, vulnerable, detalle)


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
                resultado = _cors(cfg, chequeo)
            elif chequeo.tipo == "http_status_policy":
                resultado = _http_status_policy(cfg, chequeo)
            elif chequeo.tipo == "source_contains":
                resultado = _source_contains(cfg, chequeo, root)
            elif chequeo.tipo == "docker_non_root":
                resultado = _docker_non_root(cfg, chequeo, root)
            else:
                raise ValueError(
                    f"tipo de control no soportado: {chequeo.tipo}"
                )
        except Exception as exc:
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
            )
        resultados.append(resultado)
        if progress_callback:
            progress_callback(
                "Pilar 2 · "
                f"{chequeo.nombre} · {resultado.estado}"
            )

    return resultados
