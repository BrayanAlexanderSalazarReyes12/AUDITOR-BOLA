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
    no_destructivo: bool = True
    objetivo: str | None = None


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
