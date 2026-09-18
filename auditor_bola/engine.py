"""Motor genérico de pruebas BOLA (Broken Object Level Authorization).

Determinista: sin IA, sin heurísticas de texto. Para cada endpoint y cada
cuenta configurada, calcula si el acceso DEBERÍA permitirse (según la
config, no según lo que el sistema responda) y lo compara contra lo que
el sistema responde de verdad. Cualquier sistema HTTP con autenticación
Basic y recursos identificados por id en la URL sirve como objetivo,
sin cambiar una línea de este archivo — todo lo que varía vive en
config.py / el YAML.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import requests

from .config import ConfigObjetivo, Endpoint, Cuenta, ChequeoAgente
from .agent_scope import evaluar_alcance_agente, ResultadoAlcanceAgente


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

    def as_dict(self) -> dict:
        return asdict(self)


def _acceso_esperado(cuenta: Cuenta, endpoint: Endpoint, roles_privilegiados: list[str]) -> bool:
    es_propietario = cuenta.username == endpoint.propietario_esperado
    es_privilegiado = cuenta.role in roles_privilegiados
    return es_propietario or es_privilegiado


def _armar_url(base_url: str, endpoint: Endpoint) -> str:
    return base_url + endpoint.ruta.format(id=endpoint.id_prueba)


def _disparar(base_url: str, endpoint: Endpoint, cuenta: Cuenta) -> requests.Response:
    url = _armar_url(base_url, endpoint)
    auth = (cuenta.username, cuenta.password)
    metodo = endpoint.metodo.upper()
    if metodo == "GET":
        return requests.get(url, auth=auth, timeout=10)
    if metodo == "PATCH":
        return requests.patch(url, auth=auth, json=endpoint.cuerpo_prueba or {}, timeout=10)
    if metodo == "POST":
        return requests.post(url, auth=auth, json=endpoint.cuerpo_prueba or {}, timeout=10)
    if metodo == "DELETE":
        return requests.delete(url, auth=auth, timeout=10)
    raise ValueError(f"método no soportado: {endpoint.metodo}")


def auditar(cfg: ConfigObjetivo) -> list[Hallazgo]:
    """Corre todas las cuentas contra todos los endpoints configurados.

    Devuelve un hallazgo POR combinación cuenta+endpoint (no solo los que
    fallan), para que la evidencia sea completa y auditable, no solo la
    lista de problemas.
    """
    hallazgos: list[Hallazgo] = []
    for endpoint in cfg.endpoints:
        for cuenta in cfg.cuentas:
            esperado = _acceso_esperado(cuenta, endpoint, cfg.roles_privilegiados)
            resp = _disparar(cfg.base_url, endpoint, cuenta)
            real = resp.status_code in endpoint.codigos_permitidos

            # BOLA confirmado: alguien que NO debería tener acceso, lo tiene.
            # (el caso contrario -el propietario legítimo bloqueado- es un
            # bug distinto, de disponibilidad, no de autorización rota).
            confirmado = real and not esperado

            hallazgos.append(Hallazgo(
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
            ))
    return hallazgos


@dataclass
class HallazgoAgente:
    sistema: str
    nombre_chequeo: str
    cuenta: str
    resultado: ResultadoAlcanceAgente
    ts: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["resultado"] = asdict(self.resultado)
        return d


def auditar_alcance_agente(cfg: ConfigObjetivo) -> list[HallazgoAgente]:
    """Corre los chequeos de 'alcance del agente' declarados en la config.

    Para cada uno: pide el mismo recurso por la API directa y por el
    agente, con la MISMA cuenta de bajo privilegio, y compara con
    agent_scope.evaluar_alcance_agente (ver ese módulo para el criterio).
    """
    resultados: list[HallazgoAgente] = []
    for chequeo in cfg.chequeos_agente:
        cuenta = cfg.cuenta_por_username(chequeo.cuenta)
        if cuenta is None:
            raise ValueError(f"chequeo '{chequeo.nombre}': cuenta '{chequeo.cuenta}' no está en 'cuentas'")

        auth = (cuenta.username, cuenta.password)
        url_directa = cfg.base_url + chequeo.direct_ruta
        if chequeo.direct_metodo.upper() == "GET":
            resp_directa = requests.get(url_directa, auth=auth, timeout=10)
        else:
            resp_directa = requests.post(url_directa, auth=auth, timeout=10)

        url_agente = cfg.base_url + chequeo.agent_ruta
        resp_agente = requests.post(url_agente, auth=auth, json=chequeo.agent_cuerpo, timeout=15)

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
        resultados.append(HallazgoAgente(
            sistema=cfg.sistema,
            nombre_chequeo=chequeo.nombre,
            cuenta=cuenta.username,
            resultado=resultado,
            ts=_ts(),
        ))
    return resultados
