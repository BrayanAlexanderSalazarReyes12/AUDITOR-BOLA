"""Configuración declarativa del auditor.

El motor no conoce nombres de aplicaciones, frameworks ni rutas concretas.
Todo lo específico del sistema objetivo vive en un perfil JSON.

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
    password: str | None
    role: str
    auth_type: str = "basic"  # basic | bearer | header | none
    token: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


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
    archivos_fuente: list[str] = field(default_factory=list)
    pistas_codigo: list[str] = field(default_factory=list)


@dataclass
class ChequeoAgente:
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
    archivos_fuente: list[str] = field(default_factory=list)
    pistas_codigo: list[str] = field(default_factory=list)


@dataclass
class ChequeoAcceso:
    id_control: str
    nombre: str
    cuenta: str
    metodo: str
    ruta: str
    acceso_esperado: bool
    cuerpo: dict | None = None
    codigos_permitidos: tuple[int, ...] = (200, 201, 204)
    archivos_fuente: list[str] = field(default_factory=list)
    pistas_codigo: list[str] = field(default_factory=list)


@dataclass
class ChequeoPilar2:
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
    archivos_fuente: list[str] = field(default_factory=list)
    pistas_codigo: list[str] = field(default_factory=list)


@dataclass
class Correccion:
    """Receta declarativa compuesta por operaciones genéricas."""

    control_id: str
    archivo: str
    operaciones: list[dict] = field(default_factory=list)
    descripcion: str | None = None
    requiere_reinicio: bool = False


@dataclass
class RuntimeConfig:
    """Cómo preparar/iniciar/detener/reiniciar una copia local del objetivo.

    Los campos *_por_so permiten adaptar el mismo perfil a Windows, Linux y
    macOS sin duplicar el resto de la configuración. Las claves soportadas son
    windows, linux, macos y default.

    comandos_preparacion permite declarar uno o más comandos previos al
    arranque (por ejemplo npm install o pip install). Se ejecutan una vez por
    instancia administrada cuando preparar_automaticamente es True.
    """

    modo: str = "process"  # process | command (legacy) | service | external
    nombre: str = ""
    origen: str = ""
    # auto: usa la estrategia declarada y cae a alternativas ejecutables.
    # local: prioriza procesos locales antes de contenedores.
    # contenedor: prioriza Docker/Podman si están disponibles.
    preferencia_arranque: str = "auto"
    permitir_fallback_local: bool = True
    descripcion_ejecucion: str = ""
    comando_inicio: list[str] = field(default_factory=list)
    comando_detener: list[str] = field(default_factory=list)
    comando_reinicio: list[str] = field(default_factory=list)
    comando_inicio_por_so: dict[str, list[str]] = field(default_factory=dict)
    comando_detener_por_so: dict[str, list[str]] = field(default_factory=dict)
    comando_reinicio_por_so: dict[str, list[str]] = field(default_factory=dict)

    preparar_automaticamente: bool = False
    comandos_preparacion: list[list[str]] = field(default_factory=list)
    comandos_preparacion_por_so: dict[str, list[list[str]]] = field(
        default_factory=dict
    )

    directorio_trabajo: str = "."
    espera_inicio: float = 1.2
    timeout_inicio: float = 30.0
    variables: dict[str, str] = field(default_factory=dict)
    base_url: str = ""

    # Estrategias alternativas completas de runtime. Aegis prueba la
    # estrategia principal y, si su ejecutable no está disponible, intenta
    # estas alternativas en orden.
    alternativas: list[dict] = field(default_factory=list)

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
    correcciones: list[Correccion] = field(default_factory=list)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    version_objetivo: str | None = None

    def cuenta_por_username(self, username: str) -> Cuenta | None:
        for cuenta in self.cuentas:
            if cuenta.username == username:
                return cuenta
        return None

    def correccion_por_control(self, control_id: str) -> Correccion | None:
        for correccion in self.correcciones:
            if correccion.control_id == control_id:
                return correccion
        return None


def _tuple_codigos(datos: dict, campo: str) -> None:
    if campo in datos:
        datos[campo] = tuple(datos[campo])


def cargar_config(path: str | Path) -> ConfigObjetivo:
    datos = json.loads(Path(path).read_text(encoding="utf-8"))

    cuentas = [Cuenta(**c) for c in datos.get("cuentas", [])]

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

    correcciones = [
        Correccion(**item) for item in datos.get("correcciones", [])
    ]
    runtime = RuntimeConfig(**datos.get("runtime", {}))

    return ConfigObjetivo(
        sistema=datos["sistema"],
        base_url=datos.get("base_url", "").rstrip("/"),
        cuentas=cuentas,
        endpoints=endpoints,
        roles_privilegiados=datos.get("roles_privilegiados", []),
        chequeos_agente=chequeos_agente,
        chequeos_acceso=chequeos_acceso,
        chequeos_pilar2=chequeos_pilar2,
        correcciones=correcciones,
        runtime=runtime,
        version_objetivo=datos.get("version_objetivo"),
    )
