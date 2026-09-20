"""Motor genérico de descubrimiento del Pilar 2.

Separa evidencia, candidatos, casos de prueba, hallazgos y estrategias de
corrección. No contiene nombres de aplicaciones, usuarios ni rutas fijas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib
import re
from typing import Any, Iterable


CONFIDENCE_ORDER = {"baja": 1, "media": 2, "media-alta": 3, "alta": 4}
TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".java", ".kt",
    ".php", ".cs", ".rb", ".go", ".rs", ".properties", ".env", ".cfg",
    ".conf", ".ini", ".yaml", ".yml", ".toml", ".json", ".xml", ".md",
    ".txt", ".sh", ".ps1", ".tf", ".hcl",
}
IGNORED_DIRS = {
    ".git", ".idea", ".vscode", "node_modules", "vendor", "dist", "build",
    "target", ".venv", "venv", "__pycache__", ".pytest_cache",
}


@dataclass
class P2Evidence:
    family: str
    source: str
    kind: str
    line: int | None
    confidence: str
    facts: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class P2Candidate:
    family: str
    cause: str
    component: str
    confidence: str
    hypothesis: str
    evidence: list[P2Evidence] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    remediation: dict[str, Any] = field(default_factory=dict)
    state: str = "candidato"

    def as_dict(self) -> dict[str, Any]:
        return {
            "familia": self.family,
            "causa_raiz": self.cause,
            "componente": self.component,
            "confianza": self.confidence,
            "hipotesis": self.hypothesis,
            "estado": self.state,
            "evidencia": [item.as_dict() for item in self.evidence],
            "casos_prueba": list(self.tests),
            "estrategia_correccion": dict(self.remediation),
        }


@dataclass(frozen=True)
class P2FamilyPlugin:
    code: str
    description: str

    def discover(
        self,
        root: Path,
        files: list[tuple[Path, str, str]],
        endpoints: list[dict[str, Any]],
    ) -> tuple[list[P2Candidate], list[dict[str, Any]]]:
        raise NotImplementedError


class P2FamilyRegistry:
    def __init__(self, plugins: Iterable[P2FamilyPlugin] = ()):
        self._plugins: dict[str, P2FamilyPlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: P2FamilyPlugin) -> None:
        self._plugins[plugin.code.upper()] = plugin

    def discover(
        self,
        root: Path,
        files: list[tuple[Path, str, str]],
        endpoints: list[dict[str, Any]],
    ) -> tuple[list[P2Candidate], list[dict[str, Any]]]:
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        for plugin in self._plugins.values():
            c, t = plugin.discover(root, files, endpoints)
            candidates.extend(c)
            checks.extend(t)
        return candidates, checks


def _source_kind(relative: str) -> str:
    value = relative.lower().replace("\\", "/")
    name = Path(relative).name.lower()
    if any(token in value.split("/") for token in ("test", "tests", "spec", "fixtures", "fixture", "examples", "example", "samples", "sample")):
        return "test_o_ejemplo"
    if name.startswith(("readme", "changelog", "license")) or Path(name).suffix in {".md", ".txt"}:
        return "documentacion"
    if any(token in name for token in ("prod", "production", "deploy", "docker", "compose", "helm", "kube")):
        return "despliegue"
    return "codigo_configuracion"


def _iter_text_files(root: Path) -> list[tuple[Path, str, str]]:
    found: list[tuple[Path, str, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.lower() in IGNORED_DIRS for part in relative.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", ".env"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if text:
            found.append((path, relative.as_posix(), text[:2_000_000]))
    return found


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _stable_control_id(family: str, component: str, suffix: str = "") -> str:
    digest = hashlib.sha256(f"{family}|{component}|{suffix}".encode()).hexdigest()[:8]
    return f"P2-AUTO-{family}-{digest.upper()}"


def _recipe(family: str) -> dict[str, Any]:
    recipes = {
        "CORS": {
            "problema": "politica CORS acepta origenes no confiables",
            "estrategia": "localizar el componente CORS y reemplazar reflexion/permisividad por allowlist explicita; credenciales solo para origenes autorizados; Vary: Origin cuando aplique",
            "restricciones": ["adaptar al framework detectado", "no fijar rutas ni nombres de archivo"],
            "verificacion": ["repetir Origin externo", "repetir preflight", "smoke test de origen permitido"],
        },
        "SECRET": {
            "problema": "secreto desplegable puede caer en fallback inseguro",
            "estrategia": "obtener el secreto desde fuente externa; en produccion fallar el arranque si falta o coincide con un default inseguro",
            "restricciones": ["preservar fallback local solo si la politica lo permite", "no almacenar el valor del secreto en la receta"],
            "verificacion": ["produccion sin secreto debe fallar", "produccion con secreto seguro debe iniciar", "repetir control"],
        },
        "LIMIT_BYPASS": {
            "problema": "una excepcion puede alterar una politica sin autorizacion suficiente",
            "estrategia": "autorizar explicitamente la capacidad privilegiada antes de modificar/omitir la politica y auditar su uso",
            "restricciones": ["no asumir que el nombre del parametro implica vulnerabilidad"],
            "verificacion": ["usuario normal sin excepcion", "usuario normal con excepcion", "usuario autorizado con excepcion"],
        },
        "CONTAINER": {
            "problema": "runtime de contenedor con privilegios excesivos",
            "estrategia": "resolver usuario y privilegios efectivos; usar identidad no privilegiada y permisos/capabilities/mounts minimos",
            "restricciones": ["no insertar USER a ciegas", "considerar Dockerfile, Compose y orquestador"],
            "verificacion": ["construir imagen", "iniciar runtime", "comprobar usuario efectivo", "smoke tests"],
        },
    }
    return recipes.get(family, {
        "problema": "configuracion insegura",
        "estrategia": "corregir la causa raiz de forma contextual",
        "restricciones": [],
        "verificacion": ["repetir control", "smoke tests"],
    })


class CorsPlugin(P2FamilyPlugin):
    def __init__(self):
        super().__init__("CORS", "Politica CORS")

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        sources: list[tuple[str, str, int]] = []
        concepts = (
            "access-control-allow-origin", "allow_origins", "alloworigin",
            "corsconfiguration", "flask-cors", "cors(", "allowedorigins",
            "crossorigin", "corsmiddleware",
        )
        for _path, relative, text in files:
            lower = text.lower()
            hit = next((token for token in concepts if token in lower), None)
            if not hit:
                continue
            offset = lower.find(hit)
            kind = _source_kind(relative)
            confidence = (
                "baja"
                if kind in {"documentacion", "test_o_ejemplo"}
                else "media"
            )
            sources.append((relative, confidence, _line(text, offset)))

        if not sources:
            return candidates, checks

        deploy_sources = [item for item in sources if item[1] != "baja"]
        component = deploy_sources[0][0] if deploy_sources else sources[0][0]
        evidence = [
            P2Evidence(
                "CORS",
                source,
                _source_kind(source),
                line,
                conf,
                {"concepto_cors": True},
            )
            for source, conf, line in sources[:8]
        ]
        candidate = P2Candidate(
            "CORS",
            "politica_cors",
            component,
            "media" if deploy_sources else "baja",
            (
                "La aplicacion configura CORS; comprobar dinamicamente si "
                "acepta origenes no confiables, credenciales o preflight "
                "permisivo."
            ),
            evidence=evidence,
            remediation=_recipe("CORS"),
            state="candidato" if deploy_sources else "evidencia_insuficiente",
        )

        safe_routes: list[str] = []
        for item in endpoints:
            method = str(item.get("metodo") or "").upper()
            route = str(item.get("ruta") or "")
            if method not in {"GET", "HEAD", "OPTIONS"}:
                continue
            if any(token in route for token in ("{", "<", ":id")):
                continue
            safe_routes.append(route)
        # No depende de una ruta concreta: usa el inventario real detectado.
        safe_routes = list(dict.fromkeys(safe_routes))[:3]

        for index, route in enumerate(safe_routes, start=1):
            control_id = f"P2-AUTO-CORS-{index:03d}"
            test = {
                "id_control": control_id,
                "tipo": "cors_reflection",
                "metodo": "GET",
                "ruta": route,
                "no_destructivo": True,
                "objetivo": (
                    "comparar respuesta simple y OPTIONS con Origin "
                    "externo controlado"
                ),
            }
            candidate.tests.append(test)
            checks.append({
                **test,
                "nombre": (
                    "CORS no debe autorizar origenes externos con "
                    "credenciales"
                ),
                "familia": "CORS",
                "componente": component,
                "confianza_inicial": "media",
                "origen": "auto",
                "archivos_fuente": [
                    item[0] for item in deploy_sources[:8]
                ] or [component],
                "pistas_codigo": [
                    "configuracion CORS",
                    "prueba Origin externo",
                    "preflight OPTIONS",
                ],
            })
        candidates.append(candidate)
        return candidates, checks

class SecretPlugin(P2FamilyPlugin):
    SECRET_NAME = re.compile(
        r"(?i)(secret|token|api[_\-.]?key|password|passwd|pwd|jwt|"
        r"signing|encryption|client[_\-.]?secret)"
    )
    FALLBACK_PATTERNS = (
        re.compile(
            r"""(?is)(?:getenv|environ\.get)\s*\(\s*["']"""
            r"""(?P<var>[^"']+)["']\s*,\s*["']"""
            r"""(?P<value>[^"']{3,})["']\s*\)"""
        ),
        re.compile(
            r"""(?is)process\.env\.(?P<var>[A-Za-z_]"""
            r"""[A-Za-z0-9_]*)\s*(?:\|\||\?\?)\s*["']"""
            r"""(?P<value>[^"']{3,})["']"""
        ),
        re.compile(
            r"""(?is)\$\{(?P<var>[A-Za-z_][A-Za-z0-9_.-]*):"""
            r"""(?P<value>[^}]{3,})\}"""
        ),
        re.compile(
            r"""(?is)GetEnvironmentVariable\s*\(\s*["']"""
            r"""(?P<var>[^"']+)["']\s*\)\s*\?\?\s*["']"""
            r"""(?P<value>[^"']{3,})["']"""
        ),
    )
    SYMBOLIC_PYTHON = re.compile(
        r"""(?is)(?:getenv|environ\.get)\s*\(\s*["']"""
        r"""(?P<var>[^"']+)["']\s*,\s*"""
        r"""(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)\s*\)"""
    )

    def __init__(self):
        super().__init__("SECRET", "Secretos y fallbacks")

    @staticmethod
    def _production_signal(text: str, start: int, end: int, relative: str) -> bool:
        window = text[max(0, start - 1800):min(len(text), end + 1800)]
        return (
            bool(
                re.search(
                    r"(?i)\b(prod|production|produccion|environment|env)\b",
                    window,
                )
            )
            or "prod" in relative.lower()
            or "production" in relative.lower()
        )

    @staticmethod
    def _symbol_value(text: str, symbol: str) -> str | None:
        pattern = re.compile(
            rf"""(?im)^\s*{re.escape(symbol)}\s*[:=]\s*["']"""
            rf"""([^"'\n]{{3,}})["']"""
        )
        match = pattern.search(text)
        return match.group(1) if match else None

    def _add_match(
        self,
        *,
        candidates: list[P2Candidate],
        checks: list[dict[str, Any]],
        relative: str,
        text: str,
        kind: str,
        start: int,
        end: int,
        matched_text: str,
        variable: str,
        value: str,
        control_index: int,
    ) -> int:
        if not self.SECRET_NAME.search(variable):
            return control_index
        if not value or value.lower() in {"none", "null", "undefined"}:
            return control_index

        source_line = _line(text, start)
        prod_signal = self._production_signal(
            text, start, end, relative
        )
        confidence = (
            "baja"
            if kind in {"documentacion", "test_o_ejemplo"}
            else ("media-alta" if prod_signal else "media")
        )
        component = f"{relative}:{variable}"
        fallback_hash = hashlib.sha256(value.encode()).hexdigest()[:12]
        evidence = P2Evidence(
            "SECRET",
            relative,
            kind,
            source_line,
            confidence,
            {
                "variable": variable,
                "fallback_presente": True,
                "fallback_longitud": len(value),
                "fallback_hash": fallback_hash,
                "senal_produccion": prod_signal,
                "valor_expuesto": False,
            },
        )
        candidate = P2Candidate(
            "SECRET",
            "gestion_secretos",
            component,
            confidence,
            (
                f"La variable {variable} posee un fallback; evaluar si "
                "produccion puede alcanzarlo."
            ),
            evidence=[evidence],
            remediation=_recipe("SECRET"),
            state=(
                "evidencia_insuficiente"
                if confidence == "baja"
                else "por_confirmar"
            ),
        )
        candidates.append(candidate)

        if confidence != "baja":
            control_id = f"P2-AUTO-SECRET-{control_index:03d}"
            checks.append({
                "id_control": control_id,
                "nombre": "Produccion no debe usar fallback de secreto",
                "tipo": "secret_fallback_context",
                "familia": "SECRET",
                "archivo": relative,
                "patron_inseguro": matched_text,
                "componente": component,
                "confianza_inicial": confidence,
                "origen": "auto",
                "metadata": {
                    "variable": variable,
                    "linea": source_line,
                    "senal_produccion": prod_signal,
                    "fallback_hash": fallback_hash,
                    "fallback_longitud": len(value),
                },
                "archivos_fuente": [relative],
                "pistas_codigo": [
                    "fallback de secreto",
                    "contexto de entorno",
                    "valor no almacenado en evidencia",
                ],
            })
            control_index += 1
        return control_index

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        control_index = 1

        for _path, relative, text in files:
            kind = _source_kind(relative)
            seen_offsets: set[int] = set()

            for pattern in self.FALLBACK_PATTERNS:
                for match in pattern.finditer(text):
                    value = str(match.groupdict().get("value") or "")
                    variable = str(match.groupdict().get("var") or "")
                    control_index = self._add_match(
                        candidates=candidates,
                        checks=checks,
                        relative=relative,
                        text=text,
                        kind=kind,
                        start=match.start(),
                        end=match.end(),
                        matched_text=match.group(0),
                        variable=variable,
                        value=value,
                        control_index=control_index,
                    )
                    seen_offsets.add(match.start())

            # Python permite DEFAULT_SECRET como segundo argumento. Solo se
            # activa si podemos resolver el simbolo a un literal local.
            for match in self.SYMBOLIC_PYTHON.finditer(text):
                if match.start() in seen_offsets:
                    continue
                symbol = str(match.group("symbol") or "")
                value = self._symbol_value(text, symbol)
                if not value:
                    continue
                control_index = self._add_match(
                    candidates=candidates,
                    checks=checks,
                    relative=relative,
                    text=text,
                    kind=kind,
                    start=match.start(),
                    end=match.end(),
                    matched_text=match.group(0),
                    variable=str(match.group("var") or ""),
                    value=value,
                    control_index=control_index,
                )

        return candidates[:80], checks[:40]

class LimitBypassPlugin(P2FamilyPlugin):
    PARAM_TOKENS = (
        "bypass", "override", "force", "forced", "skip", "urgent",
        "urgente", "unlimited", "emergency", "priority",
        "privileged", "internal",
    )
    POLICY_TOKENS = (
        "limit", "limite", "quota", "cuota", "budget", "rate",
        "throttle", "max_", "maximum", "size", "tokens", "concurr",
        "circuit",
    )
    GUARD_TOKENS = (
        "authorize", "authorization", "permission", "permiso", "role",
        "rol", "is_admin", "has_permission", "policy", "guard",
        "coordinator", "coordinador", "supervisor",
    )

    def __init__(self):
        super().__init__("LIMIT_BYPASS", "Bypass de limites y politicas")

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        control_index = 1

        for _path, relative, text in files:
            kind = _source_kind(relative)
            if kind == "documentacion":
                continue
            lower = text.lower()

            for token in self.PARAM_TOKENS:
                for match in re.finditer(
                    rf"\b{re.escape(token)}\b",
                    lower,
                ):
                    window = lower[
                        max(0, match.start() - 900):
                        match.end() + 1400
                    ]
                    if not any(
                        policy in window
                        for policy in self.POLICY_TOKENS
                    ):
                        continue

                    guard_window = lower[
                        max(0, match.start() - 350):
                        match.end() + 500
                    ]
                    has_guard = any(
                        guard in guard_window
                        for guard in self.GUARD_TOKENS
                    )
                    confidence = (
                        "baja"
                        if kind == "test_o_ejemplo" or has_guard
                        else "media"
                    )
                    evidence = P2Evidence(
                        "LIMIT_BYPASS",
                        relative,
                        kind,
                        _line(text, match.start()),
                        confidence,
                        {
                            "parametro_o_flag": token,
                            "politica_cercana": True,
                            "guardia_autorizacion_observada": has_guard,
                            "flujo": (
                                "entrada -> condicion -> modificacion "
                                "de politica"
                            ),
                        },
                    )
                    candidate = P2Candidate(
                        "LIMIT_BYPASS",
                        "autorizacion_excepcion_limites",
                        f"{relative}:{token}",
                        confidence,
                        (
                            "Una opcion especial parece alterar una politica; "
                            "confirmar efecto y autorizacion diferencial."
                        ),
                        evidence=[evidence],
                        tests=[{
                            "tipo": "diferencial_limite",
                            "casos": [
                                "normal",
                                "opcion_especial_bajo_privilegio",
                                "opcion_especial_privilegiado",
                            ],
                            "seguridad": (
                                "usar el minimo valor no destructivo que "
                                "demuestre la condicion"
                            ),
                            "estado": (
                                "no_ejecutable_sin_payload_seguro"
                            ),
                        }],
                        remediation=_recipe("LIMIT_BYPASS"),
                        state=(
                            "por_confirmar"
                            if confidence == "media"
                            else "evidencia_insuficiente"
                        ),
                    )
                    candidates.append(candidate)

                    # Solo creamos un control ejecutable-estatico cuando no
                    # observamos guardia. Este control nunca confirma por si
                    # solo: mantiene POR_CONFIRMAR hasta prueba diferencial.
                    if confidence == "media":
                        checks.append({
                            "id_control": (
                                f"P2-AUTO-BYPASS-{control_index:03d}"
                            ),
                            "nombre": (
                                "La excepcion de politica requiere "
                                "autorizacion diferencial"
                            ),
                            "tipo": "limit_bypass_candidate",
                            "familia": "LIMIT_BYPASS",
                            "archivo": relative,
                            "componente": f"{relative}:{token}",
                            "confianza_inicial": "media",
                            "origen": "auto",
                            "metadata": {
                                "parametro": token,
                                "linea": _line(text, match.start()),
                                "guardia_observada": False,
                            },
                            "archivos_fuente": [relative],
                            "pistas_codigo": [
                                f"parametro={token}",
                                "politica cercana",
                                "sin guardia cercana",
                            ],
                        })
                        control_index += 1
                    break

        return candidates[:60], checks[:30]

class ContainerPlugin(P2FamilyPlugin):
    def __init__(self):
        super().__init__("CONTAINER", "Seguridad de contenedores")

    @staticmethod
    def _final_user(text: str) -> tuple[str | None, int]:
        # USER se reinicia conceptualmente al cambiar de stage: un USER del
        # builder no prueba el usuario del runtime final.
        stages = re.split(r"(?im)(?=^\s*FROM\s+)", text)
        stages = [stage for stage in stages if stage.strip()]
        final = stages[-1] if stages else text
        users = re.findall(
            r"(?im)^\s*USER\s+([^\s#]+)",
            final,
        )
        return (users[-1] if users else None, len(stages))

    def discover(self, root, files, endpoints):
        dockerfiles = [
            (relative, text)
            for _p, relative, text in files
            if Path(relative).name.lower().startswith("dockerfile")
        ]
        manifests = [
            relative
            for _p, relative, text in files
            if (
                Path(relative).name.lower()
                in {
                    "docker-compose.yml",
                    "docker-compose.yaml",
                    "compose.yml",
                    "compose.yaml",
                }
                or (
                    "securitycontext" in text.lower()
                    and Path(relative).suffix.lower()
                    in {".yaml", ".yml"}
                )
            )
        ]

        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        for index, (relative, text) in enumerate(
            dockerfiles,
            start=1,
        ):
            final_user, stage_count = self._final_user(text)
            confidence = "alta" if final_user else "media"
            evidence = [
                P2Evidence(
                    "CONTAINER",
                    relative,
                    "despliegue",
                    None,
                    confidence,
                    {
                        "usuario_final_declarado": final_user,
                        "stages": stage_count,
                        "manifiestos_runtime": manifests[:12],
                    },
                )
            ]
            candidate = P2Candidate(
                "CONTAINER",
                "privilegios_contenedor",
                relative,
                confidence,
                (
                    "Resolver usuario y privilegios efectivos del runtime "
                    "final, incluyendo overrides del orquestador."
                ),
                evidence=evidence,
                remediation=_recipe("CONTAINER"),
                state="prueba_preparada",
            )
            control_id = f"P2-AUTO-DOCKER-{index:03d}"
            test = {
                "id_control": control_id,
                "tipo": "container_runtime_policy",
                "archivo": relative,
                "no_destructivo": True,
                "objetivo": (
                    "resolver stage final y overrides de runtime"
                ),
            }
            candidate.tests.append(test)
            checks.append({
                **test,
                "nombre": (
                    "El runtime de contenedor no debe ejecutar con "
                    "privilegios excesivos"
                ),
                "familia": "CONTAINER",
                "componente": relative,
                "confianza_inicial": confidence,
                "origen": "auto",
                "metadata": {
                    "manifiestos_runtime": manifests[:12]
                },
                "archivos_fuente": [relative] + manifests[:12],
                "pistas_codigo": [
                    "stage final",
                    "USER efectivo",
                    "Compose/Kubernetes overrides",
                    "privileged/capabilities/mounts",
                ],
            })
            candidates.append(candidate)
        return candidates, checks

class DebugPlugin(P2FamilyPlugin):
    PATTERNS = (
        re.compile(
            r"(?i)\bdebug\s*[:=]\s*(?:true|1|on)\b"
        ),
        re.compile(
            r"(?i)\bdebug\s*=\s*True\b"
        ),
    )

    def __init__(self):
        super().__init__("DEBUG", "Modo debug")

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        index = 1
        for _path, relative, text in files:
            kind = _source_kind(relative)
            if kind in {"documentacion", "test_o_ejemplo"}:
                continue
            match = next(
                (pattern.search(text) for pattern in self.PATTERNS
                 if pattern.search(text)),
                None,
            )
            if not match:
                continue
            component = relative
            candidates.append(
                P2Candidate(
                    "DEBUG",
                    "configuracion_debug",
                    component,
                    "media",
                    (
                        "Se observa debug habilitado en una fuente "
                        "desplegable; confirmar valor efectivo por entorno."
                    ),
                    evidence=[P2Evidence(
                        "DEBUG",
                        relative,
                        kind,
                        _line(text, match.start()),
                        "media",
                        {"debug_habilitado": True},
                    )],
                    remediation={
                        "problema": "debug desplegable habilitado",
                        "estrategia": (
                            "deshabilitar debug fuera de desarrollo y "
                            "separar configuracion por entorno"
                        ),
                        "restricciones": [
                            "no modificar configuracion exclusiva de tests"
                        ],
                        "verificacion": [
                            "arranque produccion sin debug",
                            "smoke tests",
                        ],
                    },
                    state="por_confirmar",
                )
            )
            checks.append({
                "id_control": f"P2-AUTO-DEBUG-{index:03d}",
                "nombre": (
                    "El modo debug no debe quedar habilitado en despliegue"
                ),
                "tipo": "debug_context",
                "familia": "DEBUG",
                "archivo": relative,
                "patron_inseguro": match.re.pattern,
                "componente": component,
                "confianza_inicial": "media",
                "origen": "auto",
                "metadata": {
                    "senal_produccion": (
                        "prod" in relative.lower()
                        or "production" in relative.lower()
                        or "deploy" in relative.lower()
                    ),
                    "linea": _line(text, match.start()),
                },
                "archivos_fuente": [relative],
                "pistas_codigo": ["debug habilitado"],
            })
            index += 1
        return candidates, checks


class SessionPlugin(P2FamilyPlugin):
    PATTERNS = (
        re.compile(
            r"(?im)^\s*SESSION_COOKIE_SECURE\s*=\s*False\s*$"
        ),
        re.compile(
            r"(?is)(?:cookie|session).{0,180}"
            r"\bsecure\s*[:=]\s*false\b"
        ),
    )

    def __init__(self):
        super().__init__("SESSION", "Cookies y sesion")

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        index = 1
        for _path, relative, text in files:
            kind = _source_kind(relative)
            if kind in {"documentacion", "test_o_ejemplo"}:
                continue
            match = None
            for pattern in self.PATTERNS:
                match = pattern.search(text)
                if match:
                    break
            if not match:
                continue
            candidates.append(
                P2Candidate(
                    "SESSION",
                    "configuracion_sesion",
                    relative,
                    "media",
                    (
                        "La configuracion de cookie/sesion declara "
                        "Secure=false; confirmar contexto de transporte."
                    ),
                    evidence=[P2Evidence(
                        "SESSION",
                        relative,
                        kind,
                        _line(text, match.start()),
                        "media",
                        {"secure_false": True},
                    )],
                    remediation={
                        "problema": "cookie de sesion sin Secure",
                        "estrategia": (
                            "habilitar atributos Secure/HttpOnly/SameSite "
                            "de acuerdo con el flujo y transporte"
                        ),
                        "restricciones": [
                            "considerar desarrollo HTTP local"
                        ],
                        "verificacion": [
                            "inspeccionar Set-Cookie en runtime",
                            "smoke de autenticacion",
                        ],
                    },
                    state="por_confirmar",
                )
            )
            checks.append({
                "id_control": f"P2-AUTO-COOKIE-{index:03d}",
                "nombre": (
                    "La cookie de sesion no debe desactivar Secure "
                    "en despliegue"
                ),
                "tipo": "session_cookie_context",
                "familia": "SESSION",
                "archivo": relative,
                "patron_inseguro": match.re.pattern,
                "componente": relative,
                "confianza_inicial": "media",
                "origen": "auto",
                "metadata": {
                    "senal_produccion": (
                        "prod" in relative.lower()
                        or "production" in relative.lower()
                        or "deploy" in relative.lower()
                    ),
                    "linea": _line(text, match.start()),
                },
                "archivos_fuente": [relative],
                "pistas_codigo": ["cookie/session", "secure=false"],
            })
            index += 1
        return candidates, checks

DEFAULT_P2_REGISTRY = P2FamilyRegistry((
    CorsPlugin(),
    SecretPlugin(),
    LimitBypassPlugin(),
    ContainerPlugin(),
    DebugPlugin(),
    SessionPlugin(),
))


def discover_pilar2(
    root: str | Path,
    endpoints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root_path = Path(root).expanduser().resolve()
    files = _iter_text_files(root_path)
    candidates, checks = DEFAULT_P2_REGISTRY.discover(
        root_path,
        files,
        list(endpoints or []),
    )
    return {
        "candidatos": [item.as_dict() for item in candidates],
        "controles": checks,
        "estrategias_correccion": [
            {"familia": family, **_recipe(family)}
            for family in ("CORS", "SECRET", "LIMIT_BYPASS", "CONTAINER")
        ],
        "estadisticas": {
            "archivos_analizados": len(files),
            "candidatos": len(candidates),
            "controles_ejecutables": len(checks),
            "familias": sorted({item.family for item in candidates}),
        },
    }