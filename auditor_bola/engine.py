"""Motor determinista del Pilar 1: Identidad y Control de Acceso."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

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


def auditar(cfg: ConfigObjetivo) -> list[Hallazgo]:
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
    return hallazgos


def auditar_controles_acceso(cfg: ConfigObjetivo) -> list[ResultadoAcceso]:
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
    return resultados


def auditar_alcance_agente(cfg: ConfigObjetivo) -> list[HallazgoAgente]:
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
    return resultados
