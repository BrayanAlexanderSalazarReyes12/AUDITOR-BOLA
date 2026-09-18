"""Carga y validación de la configuración del objetivo a auditar.

La configuración es la única frontera entre el motor y el sistema objetivo.
El formato es JSON puro y permite declarar controles de los dos pilares:

Pilar 1: Identidad y Control de Acceso.
Pilar 2: Arquitectura y Configuración.
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
    ruta: str
    id_prueba: str
    propietario_esperado: str
    cuerpo_prueba: dict | None = None
    codigos_permitidos: tuple[int, ...] = (200, 201, 204)
    id_control: str | None = None
    descripcion: str | None = None


@dataclass
class ChequeoAgente:
    """Compara la API directa contra un agente con la misma cuenta."""

    nombre: str
    cuenta: str
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
    id_control: str = "P1-SCOPE"


@dataclass
class ChequeoAcceso:
    """Control RBAC/ABAC puntual no basado en propiedad de objetos."""

    id_control: str
    nombre: str
    cuenta: str
    metodo: str
    ruta: str
    acceso_esperado: bool
    cuerpo: dict | None = None
    codigos_permitidos: tuple[int, ...] = (200, 201, 204)


@dataclass
class ChequeoPilar2:
    """Control declarativo de arquitectura/configuración.

    Tipos soportados:
    - cors_reflection: detecta reflexión de Origin con credenciales.
    - http_status_policy: valida que una petición sensible sea rechazada.
    - source_contains: busca un patrón inseguro en un archivo local.
    - docker_non_root: verifica que el Dockerfile declare USER no root.
    """

    id_control: str
    nombre: str
    tipo: str
    metodo: str = "GET"
    ruta: str = "/"
    cuenta: str | None = None
    cuerpo: dict | None = None
    headers: dict[str, str] = field(default_factory=dict)
    codigos_seguros: tuple[int, ...] = (400, 401, 403, 429)
    campo_repetir: str | None = None
    caracter: str = "x"
    cantidad: int = 0
    archivo: str | None = None
    patron_inseguro: str | None = None
    patron_seguro: str | None = None


@dataclass
class ConfigObjetivo:
    sistema: str
    base_url: str
    cuentas: list[Cuenta]
    endpoints: list[Endpoint]
    roles_privilegiados: list[str] = field(default_factory=list)
    chequeos_agente: list[ChequeoAgente] = field(default_factory=list)
    chequeos_acceso: list[ChequeoAcceso] = field(default_factory=list)
    chequeos_pilar2: list[ChequeoPilar2] = field(default_factory=list)
    version_objetivo: str | None = None

    def cuenta_por_username(self, username: str) -> Cuenta | None:
        for cuenta in self.cuentas:
            if cuenta.username == username:
                return cuenta
        return None


def _tuple_codigos(datos: dict, campo: str) -> None:
    if campo in datos:
        datos[campo] = tuple(datos[campo])


def cargar_config(path: str | Path) -> ConfigObjetivo:
    datos = json.loads(Path(path).read_text(encoding="utf-8"))

    cuentas = [Cuenta(**c) for c in datos["cuentas"]]

    endpoints: list[Endpoint] = []
    for raw in datos.get("endpoints", []):
        item = dict(raw)
        _tuple_codigos(item, "codigos_permitidos")
        endpoints.append(Endpoint(**item))

    chequeos_agente = [
        ChequeoAgente(**item) for item in datos.get("chequeos_agente", [])
    ]

    chequeos_acceso: list[ChequeoAcceso] = []
    for raw in datos.get("chequeos_acceso", []):
        item = dict(raw)
        _tuple_codigos(item, "codigos_permitidos")
        chequeos_acceso.append(ChequeoAcceso(**item))

    chequeos_pilar2: list[ChequeoPilar2] = []
    for raw in datos.get("chequeos_pilar2", []):
        item = dict(raw)
        _tuple_codigos(item, "codigos_seguros")
        chequeos_pilar2.append(ChequeoPilar2(**item))

    return ConfigObjetivo(
        sistema=datos["sistema"],
        base_url=datos["base_url"].rstrip("/"),
        cuentas=cuentas,
        endpoints=endpoints,
        roles_privilegiados=datos.get("roles_privilegiados", []),
        chequeos_agente=chequeos_agente,
        chequeos_acceso=chequeos_acceso,
        chequeos_pilar2=chequeos_pilar2,
        version_objetivo=datos.get("version_objetivo"),
    )
