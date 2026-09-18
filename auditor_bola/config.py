"""Carga y validación de la configuración del objetivo a auditar.

Esta es la única frontera entre el motor genérico y un sistema real. Nada
en engine.py sabe el nombre de ningún sistema: todo entra por aquí.

Formato: JSON puro (sin dependencias extra — json es de la librería
estándar de Python, a diferencia de YAML).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Cuenta:
    username: str
    password: str
    role: str


@dataclass
class Endpoint:
    metodo: str
    ruta: str  # plantilla, ej: /api/recurso/{id}
    id_prueba: str
    propietario_esperado: str
    cuerpo_prueba: dict | None = None
    codigos_permitidos: tuple[int, ...] = (200, 201, 204)


@dataclass
class ChequeoAgente:
    """Compara la API directa contra un agente conversacional, con la misma cuenta.

    Ver agent_scope.py: portado del control P1-SCOPE-006 del equipo, aquí
    generalizado a cualquier sistema con un endpoint "directo" y otro que
    invoca un agente/asistente.
    """
    nombre: str
    cuenta: str  # username de baja privilegio con el que se prueban ambos lados
    direct_metodo: str
    direct_ruta: str
    agent_ruta: str
    agent_cuerpo: dict
    direct_json_path: str = "$"
    steps_json_path: str = "$.pasos"
    tool_name: str = "listar_solicitudes"
    tool_field: str = "herramienta"
    count_field: str = "devueltas"
    id_field: str = "id"
    agent_items_json_path: str | None = None


@dataclass
class ConfigObjetivo:
    sistema: str
    base_url: str
    cuentas: list[Cuenta]
    endpoints: list[Endpoint]
    roles_privilegiados: list[str] = field(default_factory=list)
    chequeos_agente: list[ChequeoAgente] = field(default_factory=list)

    def cuenta_por_username(self, username: str) -> Cuenta | None:
        for c in self.cuentas:
            if c.username == username:
                return c
        return None


def cargar_config(path: str | Path) -> ConfigObjetivo:
    datos = json.loads(Path(path).read_text(encoding="utf-8"))

    cuentas = [Cuenta(**c) for c in datos["cuentas"]]
    endpoints = []
    for e in datos["endpoints"]:
        e = dict(e)
        if "codigos_permitidos" in e:
            e["codigos_permitidos"] = tuple(e["codigos_permitidos"])
        endpoints.append(Endpoint(**e))

    chequeos_agente = [ChequeoAgente(**c) for c in datos.get("chequeos_agente", [])]

    return ConfigObjetivo(
        sistema=datos["sistema"],
        base_url=datos["base_url"].rstrip("/"),
        cuentas=cuentas,
        endpoints=endpoints,
        roles_privilegiados=datos.get("roles_privilegiados", []),
        chequeos_agente=chequeos_agente,
    )
