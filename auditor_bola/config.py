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
    familia: str | None = None
    componente: str | None = None
    confianza_inicial: str | None = None
    origen: str | None = None
    metadata: dict = field(default_factory=dict)


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
    # Registro canónico del Pilar 1. Mantiene en un solo bloque BOLA,
    # RBAC/ABAC y alcance de agente. Los campos legacy anteriores se conservan
    # para compatibilidad con perfiles existentes y con el motor actual.
    chequeos_pilar1: list[dict] = field(default_factory=list)
    chequeos_pilar2: list[ChequeoPilar2] = field(default_factory=list)
    correcciones: list[Correccion] = field(default_factory=list)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    version_objetivo: str | None = None
    # Inventario completo detectado por el auto-perfil. Se conserva para
    # ejecutar una matriz endpoint x cuenta además de los controles P1
    # semánticamente confirmados.
    endpoints_detectados: list[dict] = field(default_factory=list)
    probar_todos_endpoints_con_todos_usuarios: bool = True
    # Candidatos P1 conservados para que la matriz pueda convertir
    # observaciones dinámicas en hallazgos cuando existe una expectativa de
    # seguridad inferible (por ejemplo RBAC de bajo privilegio).
    candidatos_pilar1: list[dict] = field(default_factory=list)
    # Hipótesis P2 que aún no son hallazgos. Permite conservar evidencia
    # estática/dinámica sin elevarla prematuramente a vulnerabilidad.
    candidatos_pilar2: list[dict] = field(default_factory=list)

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


def construir_registro_pilar1(
    endpoints: list[Endpoint],
    chequeos_acceso: list[ChequeoAcceso],
    chequeos_agente: list[ChequeoAgente],
) -> list[dict]:
    """Normaliza todos los controles ejecutables de P1 en un solo registro."""
    registro: list[dict] = []

    for endpoint in endpoints:
        registro.append(
            {
                "tipo": "bola",
                "id_control": endpoint.id_control or "P1-BOLA",
                "nombre": (
                    endpoint.descripcion
                    or "Control BOLA por propiedad de objeto"
                ),
                "metodo": endpoint.metodo,
                "ruta": endpoint.ruta,
                "id_prueba": endpoint.id_prueba,
                "propietario_esperado": endpoint.propietario_esperado,
                "cuerpo_prueba": endpoint.cuerpo_prueba,
                "codigos_permitidos": list(
                    endpoint.codigos_permitidos
                ),
                "archivos_fuente": list(endpoint.archivos_fuente),
                "pistas_codigo": list(endpoint.pistas_codigo),
            }
        )

    for check in chequeos_acceso:
        registro.append(
            {
                "tipo": "acceso",
                "id_control": check.id_control,
                "nombre": check.nombre,
                "cuenta": check.cuenta,
                "metodo": check.metodo,
                "ruta": check.ruta,
                "acceso_esperado": check.acceso_esperado,
                "cuerpo": check.cuerpo,
                "codigos_permitidos": list(
                    check.codigos_permitidos
                ),
                "archivos_fuente": list(check.archivos_fuente),
                "pistas_codigo": list(check.pistas_codigo),
            }
        )

    for check in chequeos_agente:
        registro.append(
            {
                "tipo": "alcance_agente",
                "id_control": check.id_control,
                "nombre": check.nombre,
                "cuenta": check.cuenta,
                "direct_metodo": check.direct_metodo,
                "direct_ruta": check.direct_ruta,
                "agent_ruta": check.agent_ruta,
                "agent_cuerpo": dict(check.agent_cuerpo),
                "direct_json_path": check.direct_json_path,
                "steps_json_path": check.steps_json_path,
                "tool_name": check.tool_name,
                "tool_field": check.tool_field,
                "count_field": check.count_field,
                "id_field": check.id_field,
                "agent_items_json_path": check.agent_items_json_path,
                "archivos_fuente": list(check.archivos_fuente),
                "pistas_codigo": list(check.pistas_codigo),
            }
        )

    return registro


def _agregar_p1_desde_registro(
    raw_registry: list,
    endpoints: list[Endpoint],
    chequeos_acceso: list[ChequeoAcceso],
    chequeos_agente: list[ChequeoAgente],
) -> None:
    """Materializa chequeos_pilar1 en las estructuras ejecutables legacy."""
    endpoint_keys = {
        (
            item.id_control or "P1-BOLA",
            item.metodo.upper(),
            item.ruta,
            str(item.id_prueba),
            item.propietario_esperado,
        )
        for item in endpoints
    }
    access_keys = {
        (
            item.id_control,
            item.cuenta,
            item.metodo.upper(),
            item.ruta,
        )
        for item in chequeos_acceso
    }
    agent_keys = {
        (
            item.id_control,
            item.cuenta,
            item.direct_ruta,
            item.agent_ruta,
        )
        for item in chequeos_agente
    }

    for raw in raw_registry:
        if not isinstance(raw, dict):
            continue
        tipo = str(
            raw.get("tipo")
            or raw.get("tipo_control")
            or ""
        ).strip().lower()

        if tipo in {"bola", "object_access", "object-ownership"}:
            required = (
                raw.get("metodo"),
                raw.get("ruta"),
                raw.get("id_prueba"),
                raw.get("propietario_esperado"),
            )
            if any(value in (None, "") for value in required):
                continue
            item = {
                key: raw[key]
                for key in (
                    "metodo",
                    "ruta",
                    "id_prueba",
                    "propietario_esperado",
                    "cuerpo_prueba",
                    "codigos_permitidos",
                    "id_control",
                    "descripcion",
                    "archivos_fuente",
                    "pistas_codigo",
                )
                if key in raw
            }
            if "descripcion" not in item and raw.get("nombre"):
                item["descripcion"] = raw.get("nombre")
            _tuple_codigos(item, "codigos_permitidos")
            endpoint = Endpoint(**item)
            key = (
                endpoint.id_control or "P1-BOLA",
                endpoint.metodo.upper(),
                endpoint.ruta,
                str(endpoint.id_prueba),
                endpoint.propietario_esperado,
            )
            if key not in endpoint_keys:
                endpoints.append(endpoint)
                endpoint_keys.add(key)
            continue

        if tipo in {"acceso", "rbac", "abac", "rbac_abac"}:
            required = (
                raw.get("id_control"),
                raw.get("cuenta"),
                raw.get("metodo"),
                raw.get("ruta"),
            )
            if any(value in (None, "") for value in required):
                continue
            if "acceso_esperado" not in raw:
                continue
            item = {
                key: raw[key]
                for key in (
                    "id_control",
                    "nombre",
                    "cuenta",
                    "metodo",
                    "ruta",
                    "acceso_esperado",
                    "cuerpo",
                    "codigos_permitidos",
                    "archivos_fuente",
                    "pistas_codigo",
                )
                if key in raw
            }
            item.setdefault(
                "nombre",
                str(raw.get("id_control") or "Control de acceso"),
            )
            _tuple_codigos(item, "codigos_permitidos")
            check = ChequeoAcceso(**item)
            key = (
                check.id_control,
                check.cuenta,
                check.metodo.upper(),
                check.ruta,
            )
            if key not in access_keys:
                chequeos_acceso.append(check)
                access_keys.add(key)
            continue

        if tipo in {
            "alcance_agente",
            "agent_scope",
            "scope",
        }:
            required = (
                raw.get("cuenta"),
                raw.get("direct_metodo"),
                raw.get("direct_ruta"),
                raw.get("agent_ruta"),
                raw.get("agent_cuerpo"),
            )
            if any(value in (None, "") for value in required):
                continue
            item = {
                key: raw[key]
                for key in (
                    "nombre",
                    "cuenta",
                    "direct_metodo",
                    "direct_ruta",
                    "agent_ruta",
                    "agent_cuerpo",
                    "direct_json_path",
                    "steps_json_path",
                    "tool_name",
                    "tool_field",
                    "count_field",
                    "id_field",
                    "agent_items_json_path",
                    "id_control",
                    "archivos_fuente",
                    "pistas_codigo",
                )
                if key in raw
            }
            item.setdefault(
                "nombre",
                str(raw.get("id_control") or "Alcance de agente"),
            )
            check = ChequeoAgente(**item)
            key = (
                check.id_control,
                check.cuenta,
                check.direct_ruta,
                check.agent_ruta,
            )
            if key not in agent_keys:
                chequeos_agente.append(check)
                agent_keys.add(key)


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

    raw_pilar1 = [
        dict(item)
        for item in datos.get("chequeos_pilar1", [])
        if isinstance(item, dict)
    ]
    _agregar_p1_desde_registro(
        raw_pilar1,
        endpoints,
        chequeos_acceso,
        chequeos_agente,
    )
    registro_pilar1 = (
        raw_pilar1
        if raw_pilar1
        else construir_registro_pilar1(
            endpoints,
            chequeos_acceso,
            chequeos_agente,
        )
    )

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
        chequeos_pilar1=registro_pilar1,
        chequeos_pilar2=chequeos_pilar2,
        correcciones=correcciones,
        runtime=runtime,
        version_objetivo=datos.get("version_objetivo"),
        endpoints_detectados=[
            dict(item)
            for item in datos.get("endpoints_detectados", [])
            if isinstance(item, dict)
        ],
        probar_todos_endpoints_con_todos_usuarios=bool(
            datos.get(
                "probar_todos_endpoints_con_todos_usuarios",
                True,
            )
        ),
        candidatos_pilar1=[
            dict(item)
            for item in (
                datos.get("candidatos_pilar1")
                or (
                    datos.get("metadata_detectada", {})
                    if isinstance(
                        datos.get("metadata_detectada"), dict
                    )
                    else {}
                ).get("candidatos_pilar1", [])
            )
            if isinstance(item, dict)
        ],
        candidatos_pilar2=[
            dict(item)
            for item in (
                datos.get("candidatos_pilar2")
                or (
                    datos.get("metadata_detectada", {})
                    if isinstance(
                        datos.get("metadata_detectada"), dict
                    )
                    else {}
                ).get("candidatos_pilar2", [])
            )
            if isinstance(item, dict)
        ],
    )