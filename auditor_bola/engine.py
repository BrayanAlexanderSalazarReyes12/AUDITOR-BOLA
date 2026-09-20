"""Motor determinista del Pilar 1: Identidad y Control de Acceso."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any, Callable

from .agent_scope import ResultadoAlcanceAgente, evaluar_alcance_agente
from .config import ConfigObjetivo, Cuenta, Endpoint
from .transport import request_http


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Hallazgo:
    sistema: str
    endpoint: str
    metodo: str
    cuenta: str
    rol: str
    acceso_esperado: bool
    acceso_real: bool
    http_status: int
    confirmado_bola: bool
    ts: str
    id_control: str | None = None
    descripcion: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoAcceso:
    sistema: str
    id_control: str
    nombre: str
    cuenta: str
    rol: str
    endpoint: str
    metodo: str
    acceso_esperado: bool
    acceso_real: bool
    http_status: int
    vulnerable: bool
    ts: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoMatrizAcceso:
    sistema: str
    cuenta: str
    rol: str
    endpoint_detectado: str
    endpoint_ejecutado: str | None
    metodo: str
    http_status: int | None
    acceso_real: bool | None
    clasificacion: str
    detalle: str
    ts: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class HallazgoAgente:
    sistema: str
    id_control: str
    nombre_chequeo: str
    cuenta: str
    resultado: ResultadoAlcanceAgente
    ts: str

    def as_dict(self) -> dict:
        data = asdict(self)
        data["resultado"] = asdict(self.resultado)
        return data


def _acceso_esperado(
    cuenta: Cuenta, endpoint: Endpoint, roles_privilegiados: list[str]
) -> bool:
    es_propietario = cuenta.username == endpoint.propietario_esperado
    es_privilegiado = cuenta.role in roles_privilegiados
    return es_propietario or es_privilegiado


def _armar_url(base_url: str, endpoint: Endpoint) -> str:
    return base_url + endpoint.ruta.format(id=endpoint.id_prueba)


def _disparar(base_url: str, endpoint: Endpoint, cuenta: Cuenta):
    return request_http(
        endpoint.metodo,
        _armar_url(base_url, endpoint),
        cuenta=cuenta,
        cuerpo=endpoint.cuerpo_prueba,
    )


def auditar(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[Hallazgo]:
    """Prueba BOLA para cada combinación cuenta + endpoint declarada."""
    hallazgos: list[Hallazgo] = []
    for endpoint in cfg.endpoints:
        for cuenta in cfg.cuentas:
            esperado = _acceso_esperado(cuenta, endpoint, cfg.roles_privilegiados)
            resp = _disparar(cfg.base_url, endpoint, cuenta)
            real = resp.status_code in endpoint.codigos_permitidos
            confirmado = real and not esperado
            hallazgos.append(
                Hallazgo(
                    sistema=cfg.sistema,
                    endpoint=endpoint.ruta,
                    metodo=endpoint.metodo.upper(),
                    cuenta=cuenta.username,
                    rol=cuenta.role,
                    acceso_esperado=esperado,
                    acceso_real=real,
                    http_status=resp.status_code,
                    confirmado_bola=confirmado,
                    ts=_ts(),
                    id_control=endpoint.id_control,
                    descripcion=endpoint.descripcion,
                )
            )
            if progress_callback:
                progress_callback(
                    "Pilar 1 · BOLA · "
                    f"{endpoint.metodo.upper()} {endpoint.ruta} · "
                    f"cuenta {cuenta.username}"
                )
    return hallazgos


def auditar_controles_acceso(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[ResultadoAcceso]:
    """Ejecuta controles RBAC/ABAC puntuales declarados en la configuración."""
    resultados: list[ResultadoAcceso] = []
    for chequeo in cfg.chequeos_acceso:
        cuenta = cfg.cuenta_por_username(chequeo.cuenta)
        if cuenta is None:
            raise ValueError(
                f"control '{chequeo.id_control}': cuenta '{chequeo.cuenta}' no configurada"
            )
        resp = request_http(
            chequeo.metodo,
            cfg.base_url + chequeo.ruta,
            cuenta=cuenta,
            cuerpo=chequeo.cuerpo,
        )
        real = resp.status_code in chequeo.codigos_permitidos
        resultados.append(
            ResultadoAcceso(
                sistema=cfg.sistema,
                id_control=chequeo.id_control,
                nombre=chequeo.nombre,
                cuenta=cuenta.username,
                rol=cuenta.role,
                endpoint=chequeo.ruta,
                metodo=chequeo.metodo.upper(),
                acceso_esperado=chequeo.acceso_esperado,
                acceso_real=real,
                http_status=resp.status_code,
                vulnerable=real != chequeo.acceso_esperado,
                ts=_ts(),
            )
        )
        if progress_callback:
            progress_callback(
                "Pilar 1 · Acceso · "
                f"{chequeo.metodo.upper()} {chequeo.ruta} · "
                f"cuenta {cuenta.username}"
            )
    return resultados


def _normalizar_ruta_matriz(ruta: str) -> str:
    valor = str(ruta or "").strip()
    valor = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", "{id}", valor)
    valor = re.sub(r"\{[^{}]+\}", "{id}", valor)
    valor = re.sub(
        r":(?:id|[A-Za-z_][A-Za-z0-9_]*_id)(?=/|$)",
        "{id}",
        valor,
        flags=re.I,
    )
    return valor


def _ruta_ejecutable_matriz(
    cfg: ConfigObjetivo,
    metodo: str,
    ruta: str,
) -> tuple[str | None, str]:
    """Materializa rutas parametrizadas solo con evidencia ya disponible."""
    original = str(ruta or "").strip()
    if not original:
        return None, "ruta vacía"

    normalizada = _normalizar_ruta_matriz(original)
    if "{id}" not in normalizada:
        return original, "ruta literal"

    for endpoint in cfg.endpoints:
        if endpoint.metodo.upper() != metodo.upper():
            continue
        if _normalizar_ruta_matriz(endpoint.ruta) != normalizada:
            continue
        return (
            normalizada.format(id=endpoint.id_prueba),
            (
                "ruta parametrizada materializada con id de control BOLA "
                f"{endpoint.id_control or 'P1-BOLA'}"
            ),
        )

    # Si el inventario contiene también una variante literal de la misma ruta,
    # se utilizará en su propia fila. No inventamos IDs para esta variante.
    return None, "ruta parametrizada sin identificador de prueba verificable"


def _clasificar_status_matriz(status: int) -> tuple[bool | None, str]:
    if 200 <= status < 400:
        return True, "ACCESO"
    if status in {401, 403}:
        return False, "DENEGADO"
    if status in {400, 404, 405, 409, 415, 422}:
        return None, "NO_CONCLUYENTE"
    if 500 <= status:
        return None, "ERROR_SERVIDOR"
    return None, "OBSERVADO"


def auditar_matriz_acceso(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[ResultadoMatrizAcceso]:
    """Prueba cada endpoint detectado con cada cuenta configurada.

    La matriz es observacional: no inventa una política de acceso. GET/HEAD/
    OPTIONS se ejecutan normalmente. POST/PUT/PATCH usan cuerpo vacío para
    evitar reutilizar datos de negocio válidos y reducir efectos laterales.
    DELETE se registra pero no se dispara automáticamente para no destruir
    información. Una ruta parametrizada solo se ejecuta si ya existe un ID
    verificable en un control BOLA.
    """
    resultados: list[ResultadoMatrizAcceso] = []
    if not cfg.probar_todos_endpoints_con_todos_usuarios:
        return resultados
    if not cfg.endpoints_detectados or not cfg.cuentas:
        return resultados

    vistos: set[tuple[str, str]] = set()
    inventario: list[dict[str, Any]] = []
    for item in cfg.endpoints_detectados:
        metodo = str(item.get("metodo") or "GET").upper().strip()
        ruta = str(item.get("ruta") or "").strip()
        if not ruta:
            continue
        key = (metodo, ruta)
        if key in vistos:
            continue
        vistos.add(key)
        inventario.append(item)

    for item in inventario:
        metodo = str(item.get("metodo") or "GET").upper().strip()
        ruta = str(item.get("ruta") or "").strip()
        ejecutable, razon_ruta = _ruta_ejecutable_matriz(
            cfg,
            metodo,
            ruta,
        )

        for cuenta in cfg.cuentas:
            if ejecutable is None:
                resultados.append(
                    ResultadoMatrizAcceso(
                        sistema=cfg.sistema,
                        cuenta=cuenta.username,
                        rol=cuenta.role,
                        endpoint_detectado=ruta,
                        endpoint_ejecutado=None,
                        metodo=metodo,
                        http_status=None,
                        acceso_real=None,
                        clasificacion="NO_EJECUTABLE",
                        detalle=razon_ruta,
                        ts=_ts(),
                    )
                )
            elif metodo == "DELETE":
                resultados.append(
                    ResultadoMatrizAcceso(
                        sistema=cfg.sistema,
                        cuenta=cuenta.username,
                        rol=cuenta.role,
                        endpoint_detectado=ruta,
                        endpoint_ejecutado=ejecutable,
                        metodo=metodo,
                        http_status=None,
                        acceso_real=None,
                        clasificacion="NO_EJECUTABLE",
                        detalle=(
                            "DELETE omitido en matriz automática para evitar "
                            "eliminar datos del objetivo"
                        ),
                        ts=_ts(),
                    )
                )
            else:
                cuerpo = (
                    {}
                    if metodo in {"POST", "PUT", "PATCH"}
                    else None
                )
                try:
                    resp = request_http(
                        metodo,
                        cfg.base_url + ejecutable,
                        cuenta=cuenta,
                        cuerpo=cuerpo,
                    )
                    acceso_real, clasificacion = (
                        _clasificar_status_matriz(resp.status_code)
                    )
                    detalle = (
                        f"HTTP {resp.status_code} · {razon_ruta}"
                    )
                except Exception as exc:
                    resp = None
                    acceso_real = None
                    clasificacion = "ERROR"
                    detalle = f"{type(exc).__name__}: {exc}"

                resultados.append(
                    ResultadoMatrizAcceso(
                        sistema=cfg.sistema,
                        cuenta=cuenta.username,
                        rol=cuenta.role,
                        endpoint_detectado=ruta,
                        endpoint_ejecutado=ejecutable,
                        metodo=metodo,
                        http_status=(
                            resp.status_code if resp is not None else None
                        ),
                        acceso_real=acceso_real,
                        clasificacion=clasificacion,
                        detalle=detalle,
                        ts=_ts(),
                    )
                )

            if progress_callback:
                progress_callback(
                    "Pilar 1 · Matriz de acceso · "
                    f"{metodo} {ruta} · cuenta {cuenta.username}"
                )

    return resultados


def auditar_alcance_agente(
    cfg: ConfigObjetivo,
    progress_callback: Callable[[str], None] | None = None,
) -> list[HallazgoAgente]:
    resultados: list[HallazgoAgente] = []
    for chequeo in cfg.chequeos_agente:
        cuenta = cfg.cuenta_por_username(chequeo.cuenta)
        if cuenta is None:
            raise ValueError(
                f"chequeo '{chequeo.nombre}': cuenta '{chequeo.cuenta}' no configurada"
            )

        resp_directa = request_http(
            chequeo.direct_metodo,
            cfg.base_url + chequeo.direct_ruta,
            cuenta=cuenta,
        )
        resp_agente = request_http(
            "POST",
            cfg.base_url + chequeo.agent_ruta,
            cuenta=cuenta,
            cuerpo=chequeo.agent_cuerpo,
            timeout=15,
        )

        resp_directa.raise_for_status()
        resp_agente.raise_for_status()

        resultado = evaluar_alcance_agente(
            resp_directa.json(),
            resp_agente.json(),
            direct_json_path=chequeo.direct_json_path,
            steps_json_path=chequeo.steps_json_path,
            tool_name=chequeo.tool_name,
            tool_field=chequeo.tool_field,
            count_field=chequeo.count_field,
            id_field=chequeo.id_field,
            agent_items_json_path=chequeo.agent_items_json_path,
        )
        resultados.append(
            HallazgoAgente(
                sistema=cfg.sistema,
                id_control=chequeo.id_control,
                nombre_chequeo=chequeo.nombre,
                cuenta=cuenta.username,
                resultado=resultado,
                ts=_ts(),
            )
        )
        if progress_callback:
            progress_callback(
                "Pilar 1 · Alcance del agente · "
                f"{chequeo.nombre} · cuenta {cuenta.username}"
            )
    return resultados
