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
        )
        for _path, relative, text in files:
            lower = text.lower()
            hit = next((token for token in concepts if token in lower), None)
            if not hit:
                continue
            offset = lower.find(hit)
            kind = _source_kind(relative)
            confidence = "baja" if kind in {"documentacion", "test_o_ejemplo"} else "media"
            sources.append((relative, confidence, _line(text, offset)))

        if not sources:
            return candidates, checks

        deploy_sources = [item for item in sources if item[1] != "baja"]
        component = deploy_sources[0][0] if deploy_sources else sources[0][0]
        evidence = [
            P2Evidence("CORS", source, _source_kind(source), line, conf, {"concepto_cors": True})
            for source, conf, line in sources[:8]
        ]
        candidate = P2Candidate(
            "CORS", "politica_cors", component,
            "media" if deploy_sources else "baja",
            "La aplicacion configura CORS; comprobar si acepta origenes no confiables con credenciales.",
            evidence=evidence, remediation=_recipe("CORS"),
            state="candidato" if deploy_sources else "evidencia_insuficiente",
        )

        safe_routes = []
        for item in endpoints:
            method = str(item.get("metodo") or "").upper()
            route = str(item.get("ruta") or "")
            if method not in {"GET", "HEAD", "OPTIONS"}:
                continue
            if any(token in route for token in ("{", "<", ":id")):
                continue
            safe_routes.append(route)
        safe_routes = list(dict.fromkeys(safe_routes))[:3]
        for route in safe_routes:
            control_id = _stable_control_id("CORS", component, route)
            test = {
                "id_control": control_id,
                "tipo": "cors_reflection",
                "metodo": "GET",
                "ruta": route,
                "no_destructivo": True,
                "objetivo": "comparar GET/OPTIONS con Origin externo controlado",
            }
            candidate.tests.append(test)
            checks.append({
                **test,
                "nombre": "CORS no debe autorizar origenes externos con credenciales",
                "familia": "CORS",
                "componente": component,
                "confianza_inicial": "media",
                "origen": "auto",
                "archivos_fuente": [item[0] for item in deploy_sources[:8]] or [component],
                "pistas_codigo": ["configuracion CORS", "prueba Origin externo", "preflight OPTIONS"],
            })
        candidates.append(candidate)
        return candidates, checks


class SecretPlugin(P2FamilyPlugin):
    SECRET_NAME = re.compile(r"(?i)(secret|token|api[_\-.]?key|password|passwd|pwd|jwt|signing|encryption|client[_\-.]?secret)")
    FALLBACK_PATTERNS = (
        re.compile(r"""(?is)(?:getenv|environ\.get)\s*\(\s*["'](?P<var>[^"']+)["']\s*,\s*["'](?P<value>[^"']{3,})["']\s*\)"""),
        re.compile(r"""(?is)process\.env\.(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\|\||\?\?)\s*["'](?P<value>[^"']{3,})["']"""),
        re.compile(r"""(?is)\$\{(?P<var>[A-Za-z_][A-Za-z0-9_.-]*):(?P<value>[^}]{3,})\}"""),
        re.compile(r"""(?is)GetEnvironmentVariable\s*\(\s*["'](?P<var>[^"']+)["']\s*\)\s*\?\?\s*["'](?P<value>[^"']{3,})["']"""),
    )

    def __init__(self):
        super().__init__("SECRET", "Secretos y fallbacks")

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        for _path, relative, text in files:
            kind = _source_kind(relative)
            for pattern in self.FALLBACK_PATTERNS:
                for match in pattern.finditer(text):
                    var = str(match.groupdict().get("var") or "")
                    if not self.SECRET_NAME.search(var):
                        continue
                    value = str(match.groupdict().get("value") or "")
                    if not value or value.lower() in {"none", "null", "undefined"}:
                        continue
                    source_line = _line(text, match.start())
                    prod_signal = bool(re.search(r"(?i)\b(prod|production|produccion)\b", text[max(0, match.start()-1200):match.end()+1200]))
                    confidence = "baja" if kind in {"documentacion", "test_o_ejemplo"} else ("media-alta" if prod_signal else "media")
                    component = f"{relative}:{var}"
                    evidence = P2Evidence(
                        "SECRET", relative, kind, source_line, confidence,
                        {
                            "variable": var,
                            "fallback_presente": True,
                            "fallback_longitud": len(value),
                            "fallback_hash": hashlib.sha256(value.encode()).hexdigest()[:12],
                            "senal_produccion": prod_signal,
                        },
                    )
                    candidate = P2Candidate(
                        "SECRET", "gestion_secretos", component, confidence,
                        f"La variable {var} posee fallback; evaluar si produccion puede utilizarlo.",
                        evidence=[evidence], remediation=_recipe("SECRET"),
                        state="evidencia_insuficiente" if confidence == "baja" else "por_confirmar",
                    )
                    candidates.append(candidate)
                    if confidence != "baja":
                        control_id = _stable_control_id("SECRET", component)
                        checks.append({
                            "id_control": control_id,
                            "nombre": "Produccion no debe usar fallback de secreto",
                            "tipo": "secret_fallback_context",
                            "familia": "SECRET",
                            "archivo": relative,
                            "patron_inseguro": match.group(0),
                            "componente": component,
                            "confianza_inicial": confidence,
                            "origen": "auto",
                            "metadata": {
                                "variable": var,
                                "linea": source_line,
                                "senal_produccion": prod_signal,
                                "fallback_hash": evidence.facts["fallback_hash"],
                                "fallback_longitud": len(value),
                            },
                            "archivos_fuente": [relative],
                            "pistas_codigo": ["fallback de secreto", "contexto de entorno"],
                        })
        return candidates[:80], checks[:40]


class LimitBypassPlugin(P2FamilyPlugin):
    PARAM_TOKENS = ("bypass", "override", "force", "forced", "skip", "urgent", "urgente", "unlimited", "emergency", "priority", "privileged", "internal")
    POLICY_TOKENS = ("limit", "limite", "quota", "cuota", "budget", "rate", "throttle", "max_", "maximum", "size", "tokens", "concurr", "circuit")
    GUARD_TOKENS = ("authorize", "authorization", "permission", "permiso", "role", "rol", "is_admin", "has_permission", "policy", "guard", "coordinator", "supervisor")

    def __init__(self):
        super().__init__("LIMIT_BYPASS", "Bypass de limites y politicas")

    def discover(self, root, files, endpoints):
        candidates: list[P2Candidate] = []
        for _path, relative, text in files:
            kind = _source_kind(relative)
            if kind == "documentacion":
                continue
            lower = text.lower()
            for token in self.PARAM_TOKENS:
                for match in re.finditer(rf"\b{re.escape(token)}\b", lower):
                    window = lower[max(0, match.start()-900):match.end()+1400]
                    if not any(policy in window for policy in self.POLICY_TOKENS):
                        continue
                    guard_window = lower[max(0, match.start()-350):match.end()+500]
                    has_guard = any(guard in guard_window for guard in self.GUARD_TOKENS)
                    confidence = "baja" if kind == "test_o_ejemplo" else ("media" if not has_guard else "baja")
                    evidence = P2Evidence(
                        "LIMIT_BYPASS", relative, kind, _line(text, match.start()), confidence,
                        {
                            "parametro_o_flag": token,
                            "politica_cercana": True,
                            "guardia_autorizacion_observada": has_guard,
                            "flujo": "entrada -> condicion -> politica",
                        },
                    )
                    candidates.append(P2Candidate(
                        "LIMIT_BYPASS", "autorizacion_excepcion_limites",
                        f"{relative}:{token}", confidence,
                        "Una opcion especial parece alterar una politica; confirmar efecto y autorizacion diferencial.",
                        evidence=[evidence],
                        tests=[{
                            "tipo": "diferencial_limite",
                            "casos": ["normal", "opcion_especial_bajo_privilegio", "opcion_especial_privilegiado"],
                            "seguridad": "usar el minimo valor no destructivo que demuestre la condicion",
                            "estado": "no_ejecutable_sin_payload_seguro",
                        }],
                        remediation=_recipe("LIMIT_BYPASS"),
                        state="por_confirmar" if confidence == "media" else "evidencia_insuficiente",
                    ))
                    break
        return candidates[:60], []


class ContainerPlugin(P2FamilyPlugin):
    def __init__(self):
        super().__init__("CONTAINER", "Seguridad de contenedores")

    def discover(self, root, files, endpoints):
        dockerfiles = [(relative, text) for _p, relative, text in files if Path(relative).name.lower().startswith("dockerfile")]
        manifests = [
            relative for _p, relative, text in files
            if Path(relative).name.lower() in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
            or ("securitycontext" in text.lower() and Path(relative).suffix.lower() in {".yaml", ".yml"})
        ]
        candidates: list[P2Candidate] = []
        checks: list[dict[str, Any]] = []
        for relative, text in dockerfiles:
            users = re.findall(r"(?im)^\s*USER\s+([^\s#]+)", text)
            final_user = users[-1] if users else None
            confidence = "alta" if final_user else "media"
            evidence = [
                P2Evidence("CONTAINER", relative, "despliegue", None, confidence, {
                    "usuario_final_declarado": final_user,
                    "stages": len(re.findall(r"(?im)^\s*FROM\s+", text)),
                    "manifiestos_runtime": manifests[:12],
                })
            ]
            candidate = P2Candidate(
                "CONTAINER", "privilegios_contenedor", relative, confidence,
                "Resolver usuario y privilegios efectivos del runtime final, incluyendo overrides del orquestador.",
                evidence=evidence, remediation=_recipe("CONTAINER"),
                state="prueba_preparada",
            )
            control_id = _stable_control_id("CONTAINER", relative)
            test = {
                "id_control": control_id,
                "tipo": "container_runtime_policy",
                "archivo": relative,
                "no_destructivo": True,
                "objetivo": "resolver stage final y overrides de runtime",
            }
            candidate.tests.append(test)
            checks.append({
                **test,
                "nombre": "El runtime de contenedor no debe ejecutar con privilegios excesivos",
                "familia": "CONTAINER",
                "componente": relative,
                "confianza_inicial": confidence,
                "origen": "auto",
                "metadata": {"manifiestos_runtime": manifests[:12]},
                "archivos_fuente": [relative] + manifests[:12],
                "pistas_codigo": ["stage final", "USER efectivo", "Compose/Kubernetes overrides", "privileged/capabilities/mounts"],
            })
            candidates.append(candidate)
        return candidates, checks


DEFAULT_P2_REGISTRY = P2FamilyRegistry((
    CorsPlugin(),
    SecretPlugin(),
    LimitBypassPlugin(),
    ContainerPlugin(),
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
