"""Chequeo de "alcance del agente" (agent scope consistency).

Complementa al BOLA de engine.py con una pregunta distinta: no si un
usuario puede leer el recurso de otro por su propio id, sino si un AGENTE
conversacional expone, por una identidad de bajo privilegio, más objetos
o identificadores de los que esa misma identidad ve por la API directa.

Origen: adaptado del control P1-SCOPE-006 de auditor_tramitia.py
(equipo auditor-seguridad-tres-pilares, docs/MEJORA_P1_ALCANCE_AGENTE.md),
que ya lo dejó parametrizado para "otros sistemas" vía
agent_items_json_path / id_field. Aquí se generaliza un paso más: ya no
asume nombres de campo de Tramitia (se pasan todos por config).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class RutaJsonInvalida(Exception):
    pass


def json_path_get(payload: Any, path: str) -> Any:
    """Subconjunto mínimo de JSONPath: soporta $ , $.a.b y $.a[0].b."""
    if path == "$":
        return payload
    if not path.startswith("$."):
        raise RutaJsonInvalida(f"json_path no soportado: {path}")
    current = payload
    tokens = re.findall(r"(?:^|\.)([^.\[\]]+)|\[(\d+)\]", path[2:])
    if not tokens:
        raise RutaJsonInvalida(f"json_path no soportado: {path}")
    for key, index in tokens:
        if key:
            if not isinstance(current, dict) or key not in current:
                raise RutaJsonInvalida(f"json_path inexistente: {path}")
            current = current[key]
        else:
            position = int(index)
            if not isinstance(current, list) or position >= len(current):
                raise RutaJsonInvalida(f"json_path inexistente: {path}")
            current = current[position]
    return current


@dataclass
class ResultadoAlcanceAgente:
    precondicion_valida: bool
    vulnerable: bool
    herramienta: str
    invocaciones_herramienta: int
    cantidad_api_directa: int
    cantidad_agente: int | None
    ids_api_directa: list[str]
    ids_agente: list[str] | None
    ids_expuestos_por_agente: list[str] | None
    exceso: int | None


def evaluar_alcance_agente(
    direct_payload: Any,
    agent_payload: Any,
    *,
    direct_json_path: str = "$",
    steps_json_path: str = "$.pasos",
    tool_name: str = "listar_solicitudes",
    tool_field: str = "herramienta",
    count_field: str = "devueltas",
    id_field: str = "id",
    agent_items_json_path: str | None = None,
) -> ResultadoAlcanceAgente:
    """Compara lo que una identidad ve por la API directa con lo que obtiene vía el agente.

    La API directa es la referencia autorizada: define cuántos objetos puede
    ver esa identidad. Si la herramienta del agente devuelve más objetos (o
    identificadores que la API directa no entrega), el agente está
    ejecutando con una identidad distinta a la del solicitante real — sin
    importar qué rol declare el propio agente sobre sí mismo.
    """
    direct_items = json_path_get(direct_payload, direct_json_path)
    if not isinstance(direct_items, list):
        raise RutaJsonInvalida("direct_json_path no apunta a una lista")
    direct_ids = sorted({
        str(item[id_field]) for item in direct_items
        if isinstance(item, dict) and id_field in item
    })

    steps = json_path_get(agent_payload, steps_json_path)
    if not isinstance(steps, list):
        raise RutaJsonInvalida("steps_json_path no apunta a una lista")
    invocaciones = [
        s for s in steps if isinstance(s, dict) and str(s.get(tool_field)) == tool_name
    ]
    conteos = [
        int(s[count_field]) for s in invocaciones
        if isinstance(s.get(count_field), int) and not isinstance(s.get(count_field), bool)
    ]
    cantidad_agente: int | None = max(conteos) if conteos else None

    ids_agente: list[str] | None = None
    ids_expuestos: list[str] | None = None
    if agent_items_json_path:
        agent_items = json_path_get(agent_payload, agent_items_json_path)
        if not isinstance(agent_items, list):
            raise RutaJsonInvalida("agent_items_json_path no apunta a una lista")
        ids_agente = sorted({
            str(item[id_field]) for item in agent_items
            if isinstance(item, dict) and id_field in item
        })
        ids_expuestos = sorted(set(ids_agente) - set(direct_ids))
        if cantidad_agente is None:
            cantidad_agente = len(agent_items)

    precondicion_valida = cantidad_agente is not None
    vulnerable = precondicion_valida and (
        cantidad_agente > len(direct_items) or bool(ids_expuestos)
    )

    return ResultadoAlcanceAgente(
        precondicion_valida=precondicion_valida,
        vulnerable=vulnerable,
        herramienta=tool_name,
        invocaciones_herramienta=len(invocaciones),
        cantidad_api_directa=len(direct_items),
        cantidad_agente=cantidad_agente,
        ids_api_directa=direct_ids,
        ids_agente=ids_agente,
        ids_expuestos_por_agente=ids_expuestos,
        exceso=(cantidad_agente - len(direct_items)) if cantidad_agente is not None else None,
    )
