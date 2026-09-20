"""Descubrimiento genérico y análisis semántico del Pilar 2.

Este módulo no contiene nombres, rutas, usuarios ni vulnerabilidades de una
aplicación concreta. Convierte evidencia estática y de despliegue en
candidatos y controles ejecutables cuando existe contexto suficiente.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any


_IGNORE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    "node_modules", "target", "build", "dist", ".venv", "venv",
    "vendor", "bin", "obj", "coverage", ".next", ".nuxt",
}

_TEXT_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".java", ".kt", ".kts", ".php", ".cs", ".go", ".rb", ".rs",
    ".scala", ".swift", ".dart", ".ex", ".exs",
    ".jsp", ".html", ".htm", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".properties", ".gradle", ".sh", ".ps1", ".bat", ".cmd",
    ".sql", ".env", ".ini", ".conf", ".cfg", ".txt", ".md", ".rst",
}

_MAX_SCAN_BYTES = 5_000_000


def _stable_digest(*parts: Any, size: int = 16) -> str:
    raw = "|".join(str(part or "").strip().lower() for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:size]


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _mask_secret(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + ("*" * min(8, len(value) - 4)) + value[-2:]


def _source_kind(relative: str) -> str:
    lower = relative.replace("\\", "/").lower()
    name = Path(lower).name
    parts = set(Path(lower).parts)
    if (
        "/docs/" in f"/{lower}/"
        or name.startswith(("readme", "guide", "manual"))
        or Path(name).suffix in {".md", ".rst"}
    ):
        return "documentacion"
    if any(
        token in parts
        for token in {
            "test", "tests", "testing", "fixtures", "fixture", "seed",
            "seeds", "examples", "example", "samples", "sample",
        }
    ) or re.search(r"(?:^|[._-])test(?:[._-]|$)", name):
        return "test"
    if name == ".env.example" or ".example." in name or name.endswith(".sample"):
        return "ejemplo"
    if name in {
        "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "compose.yml", "compose.yaml",
    }:
        return "despliegue"
    if Path(name).suffix in {
        ".env", ".ini", ".conf", ".cfg", ".properties", ".yaml", ".yml",
        ".toml", ".json", ".xml",
    }:
        return "configuracion"
    return "codigo"


def _iter_text_files(root: Path, max_files: int = 6000):
    count = 0
    for path in root.rglob("*"):
        if count >= max_files:
            break
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in _IGNORE_DIRS for part in relative.parts):
            continue
        if not path.is_file():
            continue
        name = path.name.lower()
        if (
            path.suffix.lower() not in _TEXT_EXTENSIONS
            and name not in {
                "dockerfile", "makefile", "procfile", ".env",
            }
            and not name.startswith(".env.")
        ):
            continue
        try:
            if path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        count += 1
        yield path, relative.as_posix(), text


@dataclass
class Pilar2Candidate:
    candidate_id: str
    familia: str
    estado: str
    confianza: str
    causa_raiz: str
    motivo: str
    componente: str | None = None
    archivo: str | None = None
    linea: int | None = None
    parametro: str | None = None
    endpoints: list[str] = field(default_factory=list)
    evidencia: list[dict[str, Any]] = field(default_factory=list)
    prueba_sugerida: dict[str, Any] = field(default_factory=dict)
    estrategia_correccion: dict[str, Any] = field(default_factory=dict)
    fingerprint: str | None = None
    autogenerado: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate(
    *,
    family: str,
    root_cause: str,
    motive: str,
    confidence: str,
    state: str = "candidato",
    component: str | None = None,
    file: str | None = None,
    line: int | None = None,
    parameter: str | None = None,
    endpoints: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    test: dict[str, Any] | None = None,
    remediation: dict[str, Any] | None = None,
    fingerprint: str | None = None,
) -> Pilar2Candidate:
    fp = fingerprint or _stable_digest(
        family, root_cause, component, file, parameter, endpoints or []
    )
    return Pilar2Candidate(
        candidate_id=f"P2-CANDIDATE-{family}-{fp[:10].upper()}",
        familia=family,
        estado=state,
        confianza=confidence,
        causa_raiz=root_cause,
        motivo=motive,
        componente=component,
        archivo=file,
        linea=line,
        parametro=parameter,
        endpoints=list(endpoints or []),
        evidencia=list(evidence or []),
        prueba_sugerida=dict(test or {}),
        estrategia_correccion=dict(remediation or {}),
        fingerprint=fp,
    )


def _safe_get_routes(endpoint_inventory: list[dict[str, Any]]) -> list[str]:
    routes: list[str] = []
    for item in endpoint_inventory:
        method = str(item.get("metodo") or "").upper()
        route = str(item.get("ruta") or "").strip()
        if method not in {"GET", "HEAD"} or not route:
            continue
        if any(token in route for token in ("{", "}", "<", ">")):
            continue
        if route not in routes:
            routes.append(route)

    def rank(route: str) -> tuple[int, int, str]:
        lower = route.lower()
        if lower.startswith("/api/"):
            priority = 0
        elif lower in {"/health", "/status", "/ready", "/readiness"}:
            priority = 1
        else:
            priority = 2
        return priority, len(route), route

    return sorted(routes, key=rank)[:3] or ["/"]


_CORS_SIGNAL_PATTERNS = (
    r"access-control-allow-origin",
    r"access-control-allow-credentials",
    r"\ballow[_-]?origins?\b",
    r"\ballowedorigins?\b",
    r"\bcorsconfiguration\b",
    r"\bflask[_-]?cors\b",
    r"\baddcors\b",
    r"\busecors\b",
    r"\bcors\s*\(",
    r"@crossorigin\b",
)

_CORS_SUSPICIOUS_PATTERNS = (
    r"access-control-allow-origin[^\n]{0,180}(?:request|origin)",
    r"""(?:allow[_-]?origins?|allowedorigins?)[^\n]{0,180}[\[({]\s*["']\*["']""",
    r"origin\s*[:=]\s*true",
    r"allow[_-]?credentials\s*[:=]\s*true",
    r"setallowcredentials\s*\(\s*true\s*\)",
    r"allowcredentials\s*\(\s*true\s*\)",
)


def _discover_cors(
    root: Path,
    endpoint_inventory: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[Pilar2Candidate]]:
    checks: list[dict[str, Any]] = []
    candidates: list[Pilar2Candidate] = []
    routes = _safe_get_routes(endpoint_inventory)

    for _path, relative, text in _iter_text_files(root):
        if _source_kind(relative) in {"documentacion", "test", "ejemplo"}:
            continue
        signals = [
            pattern
            for pattern in _CORS_SIGNAL_PATTERNS
            if re.search(pattern, text, re.I | re.M | re.S)
        ]
        if not signals:
            continue

        suspicious = [
            pattern
            for pattern in _CORS_SUSPICIOUS_PATTERNS
            if re.search(pattern, text, re.I | re.M | re.S)
        ]
        component = relative
        fp = _stable_digest("CORS", component, "politica_cors")
        candidates.append(
            _candidate(
                family="CORS",
                root_cause="politica_cors",
                motive=(
                    "Se detectó un componente CORS; la política efectiva debe "
                    "confirmarse con un Origin controlado y preflight."
                ),
                confidence="media-alta" if suspicious else "media",
                state="prueba_preparada",
                component=component,
                file=relative,
                endpoints=routes,
                evidence=[
                    {
                        "tipo": "fuente_estatica",
                        "archivo": relative,
                        "senales_cors": signals,
                        "senales_politica_permisiva": suspicious,
                    }
                ],
                test={
                    "tipo": "cors_policy",
                    "metodo": "GET",
                    "endpoints": routes,
                    "no_destructiva": True,
                },
                remediation={
                    "problema": "politica CORS permisiva",
                    "estrategia": (
                        "Localizar el componente CORS y reemplazar reflexión o "
                        "patrones permisivos por una allowlist explícita; "
                        "habilitar credenciales solo para orígenes confiables."
                    ),
                    "verificacion": (
                        "Un origen externo y variantes de borde ya no deben "
                        "recibir permiso CORS con credenciales."
                    ),
                },
                fingerprint=fp,
            )
        )
        for idx, route in enumerate(routes, start=1):
            checks.append(
                {
                    "id_control": f"P2-AUTO-CORS-{fp[:8].upper()}-{idx:02d}",
                    "nombre": "La política CORS debe rechazar orígenes no confiables",
                    "tipo": "cors_policy",
                    "familia": "CORS",
                    "metodo": "GET",
                    "ruta": route,
                    "headers": {
                        "Origin": "https://origen-no-autorizado.example"
                    },
                    "archivo": relative,
                    "componente": component,
                    "confianza": "media-alta" if suspicious else "media",
                    "causa_raiz": "politica_cors",
                    "fingerprint": fp,
                    "autogenerado": True,
                    "archivos_fuente": [relative],
                    "pistas_codigo": [
                        "configuración/middleware CORS detectado",
                        *(
                            ["señal estática de política permisiva"]
                            if suspicious
                            else []
                        ),
                    ],
                    "metadata": {
                        "senales_cors": signals,
                        "senales_politica_permisiva": suspicious,
                        "alcance": component,
                    },
                }
            )
        break

    return checks, candidates


_SECRET_VAR = (
    r"(?:SECRET(?:_KEY)?|API[_-]?KEY|JWT[_-]?SECRET|TOKEN|PASSWORD|PASSWD|"
    r"CLIENT[_-]?SECRET|SIGNING[_-]?KEY|ENCRYPTION[_-]?KEY|PRIVATE[_-]?KEY|"
    r"[A-Za-z_][A-Za-z0-9_.-]*(?:SECRET|TOKEN|PASSWORD|PASSWD|API[_-]?KEY)"
    r"[A-Za-z0-9_.-]*)"
)

_SECRET_PATTERNS = (
    re.compile(
        rf"""(?imx)
        (?P<var>{_SECRET_VAR})
        \s*=\s*
        (?:os\.(?:getenv|environ\.get)|env|getenv)\(
        [^,\n]+,\s*(?P<quote>["'])(?P<fallback>[^"'\n]{{3,}})(?P=quote)\s*\)
        """
    ),
    re.compile(
        rf"""(?imx)
        (?P<var>{_SECRET_VAR})
        [^\n]{{0,180}}
        process\.env(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])
        \s*(?:\|\||\?\?)\s*
        (?P<quote>["'])(?P<fallback>[^"'\n]{{3,}})(?P=quote)
        """
    ),
    re.compile(
        rf"""(?imx)
        (?P<var>{_SECRET_VAR})
        \s*[:=]\s*
        \$\{{[A-Za-z_][A-Za-z0-9_]*:(?P<fallback>[^}}]{{3,}})\}}
        """
    ),
    re.compile(
        rf"""(?imx)
        (?P<var>{_SECRET_VAR})
        [^\n]{{0,180}}
        GetEnvironmentVariable\([^\n]+\)
        \s*\?\?\s*
        (?P<quote>["'])(?P<fallback>[^"'\n]{{3,}})(?P=quote)
        """
    ),
)

_PYTHON_SYMBOLIC_SECRET = re.compile(
    rf"""(?imx)
    (?P<var>{_SECRET_VAR})
    \s*=\s*
    os\.(?:getenv|environ\.get)\(
    [^,\n]+,\s*(?P<symbol>[A-Za-z_][A-Za-z0-9_]*)\s*\)
    """
)

_KNOWN_INSECURE_VALUES = {
    "secret", "changeme", "change_me", "password", "admin", "default",
    "defaultsecret", "development", "dev-secret", "dev_secret", "test",
    "123456", "12345678", "your-secret", "your_secret", "replace-me",
}


def _secret_context(text: str, start: int, end: int) -> dict[str, Any]:
    before = text[max(0, start - 900):start].lower()
    after = text[end:min(len(text), end + 900)].lower()
    window = before + "\n" + after
    dev_guard = bool(
        re.search(
            r"(?:env|environment|profile|mode).{0,80}"
            r"(?:dev|development|test|local)",
            window,
            re.I | re.S,
        )
        and re.search(r"\bif\b|\bwhen\b|\bswitch\b|\bcase\b", window)
    )
    production_guard = bool(
        re.search(r"\bprod(?:uction)?\b", window)
        and re.search(
            r"\b(?:raise|throw|exit|abort|fail|error|required|missing)\b",
            window,
        )
    )
    return {
        "guardia_desarrollo": dev_guard,
        "guardia_produccion_fail_closed": production_guard,
    }


def analyze_secret_file(
    path: Path,
    *,
    relative: str | None = None,
) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    relative = relative or path.name
    source_kind = _source_kind(relative)
    results: list[dict[str, Any]] = []

    for pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            fallback = str(match.groupdict().get("fallback") or "").strip()
            variable = str(match.groupdict().get("var") or "secreto").strip()
            normalized = fallback.lower().strip()
            if normalized in {"none", "null", "nil", "undefined"}:
                continue
            context = _secret_context(text, match.start(), match.end())
            obvious_default = (
                normalized in _KNOWN_INSECURE_VALUES
                or any(
                    token in normalized
                    for token in (
                        "default", "changeme", "dev", "development", "test",
                        "example", "sample", "secret", "password",
                    )
                )
            )
            deployable = source_kind not in {
                "documentacion", "test", "ejemplo"
            }
            production_reachable = (
                deployable
                and not context["guardia_desarrollo"]
                and not context["guardia_produccion_fail_closed"]
            )
            results.append(
                {
                    "archivo": relative,
                    "linea": _line_number(text, match.start()),
                    "variable": variable,
                    "valor_fallback_redactado": _mask_secret(fallback),
                    "fallback_sha256": hashlib.sha256(
                        fallback.encode("utf-8")
                    ).hexdigest(),
                    "fallback_default_conocido": obvious_default,
                    "tipo_fuente": source_kind,
                    "produccion_puede_usar_fallback": production_reachable,
                    **context,
                }
            )
    for match in _PYTHON_SYMBOLIC_SECRET.finditer(text):
        variable = str(match.group("var") or "secreto").strip()
        symbol = str(match.group("symbol") or "").strip()
        assignment = re.search(
            rf"""(?imx)^\s*{re.escape(symbol)}\s*=\s*
            (?P<quote>["'])(?P<fallback>[^"'\n]{{3,}})(?P=quote)\s*$""",
            text,
        )
        if not assignment:
            continue
        fallback = str(assignment.group("fallback") or "").strip()
        normalized = fallback.lower().strip()
        context = _secret_context(text, match.start(), match.end())
        obvious_default = (
            normalized in _KNOWN_INSECURE_VALUES
            or any(
                token in normalized
                for token in (
                    "default", "changeme", "dev", "development", "test",
                    "example", "sample", "secret", "password",
                )
            )
            or any(
                token in symbol.lower()
                for token in ("default", "dev", "test", "fallback")
            )
        )
        deployable = source_kind not in {
            "documentacion", "test", "ejemplo"
        }
        production_reachable = (
            deployable
            and not context["guardia_desarrollo"]
            and not context["guardia_produccion_fail_closed"]
        )
        results.append(
            {
                "archivo": relative,
                "linea": _line_number(text, match.start()),
                "variable": variable,
                "fallback_simbolico": symbol,
                "valor_fallback_redactado": _mask_secret(fallback),
                "fallback_sha256": hashlib.sha256(
                    fallback.encode("utf-8")
                ).hexdigest(),
                "fallback_default_conocido": obvious_default,
                "tipo_fuente": source_kind,
                "produccion_puede_usar_fallback": production_reachable,
                **context,
            }
        )

    return results


def _discover_secrets(
    root: Path,
) -> tuple[list[dict[str, Any]], list[Pilar2Candidate]]:
    checks: list[dict[str, Any]] = []
    candidates: list[Pilar2Candidate] = []

    seen: set[tuple[str, str, int]] = set()
    for path, relative, _text in _iter_text_files(root):
        for item in analyze_secret_file(path, relative=relative):
            key = (
                relative,
                str(item.get("variable") or ""),
                int(item.get("linea") or 0),
            )
            if key in seen:
                continue
            seen.add(key)
            variable = str(item.get("variable") or "secreto")
            fp = _stable_digest(
                "SECRET", relative, variable,
                item.get("fallback_sha256"), "gestion_secretos"
            )
            strong = bool(item.get("produccion_puede_usar_fallback"))
            confidence = "media-alta" if strong else "baja"
            candidate = _candidate(
                family="SECRET",
                root_cause="gestion_secretos",
                motive=(
                    "Se detectó un fallback de secreto. Debe determinarse si "
                    "producción puede iniciar usando ese valor."
                ),
                confidence=confidence,
                state="prueba_preparada" if strong else "candidato",
                component=f"{relative}:{variable}",
                file=relative,
                line=int(item.get("linea") or 0) or None,
                evidence=[{"tipo": "flujo_configuracion", **item}],
                test={
                    "tipo": "secret_fallback",
                    "variable": variable,
                    "archivo": relative,
                },
                remediation={
                    "problema": "fallback de secreto desplegable",
                    "estrategia": (
                        "Obtener el secreto desde una fuente externa; en "
                        "producción fallar el arranque si falta o corresponde "
                        "a un valor inseguro/default."
                    ),
                    "verificacion": (
                        "Producción no debe iniciar con el secreto ausente o "
                        "con el fallback inseguro."
                    ),
                },
                fingerprint=fp,
            )
            candidates.append(candidate)
            if strong:
                checks.append(
                    {
                        "id_control": f"P2-AUTO-SECRET-{fp[:10].upper()}",
                        "nombre": (
                            "Producción no debe poder usar un secreto fallback inseguro"
                        ),
                        "tipo": "secret_fallback",
                        "familia": "SECRET",
                        "archivo": relative,
                        "componente": f"{relative}:{variable}",
                        "confianza": confidence,
                        "causa_raiz": "gestion_secretos",
                        "fingerprint": fp,
                        "autogenerado": True,
                        "archivos_fuente": [relative],
                        "pistas_codigo": [
                            "fallback de secreto",
                            "flujo desplegable sin guardia de producción fail-closed",
                        ],
                        "metadata": {
                            "variable": variable,
                            "linea": item.get("linea"),
                            "fallback_sha256": item.get("fallback_sha256"),
                            "valor_fallback_redactado": item.get(
                                "valor_fallback_redactado"
                            ),
                            "tipo_fuente": item.get("tipo_fuente"),
                        },
                    }
                )

    return checks, candidates


_BYPASS_HINTS = (
    "bypass", "skip", "ignore", "override", "unlimited", "force", "forced",
    "urgent", "urgente", "emergency", "priority", "privileged", "internal",
    "unrestricted", "exempt", "exento",
)
_LIMIT_HINTS = (
    "limit", "limite", "límite", "quota", "cuota", "budget", "presupuesto",
    "rate", "throttle", "max_", "maximum", "size", "length", "longitud",
    "token", "concurrency", "concurrencia", "circuit", "timeout",
)
_INPUT_HINTS = (
    "request", "body", "payload", "query", "params", "header", "cookie",
    "get(", "json", "form", "input",
)
_AUTH_HINTS = (
    "authorize", "authorized", "permission", "permiso", "has_role", "role",
    "rol", "is_admin", "admin", "supervisor", "coordinator", "coordinador",
    "policy", "guard", "can_",
)


def _routes_for_source(
    endpoint_inventory: list[dict[str, Any]],
    source: str,
) -> list[str]:
    routes: list[str] = []
    for item in endpoint_inventory:
        files = list(item.get("archivos") or item.get("archivos_fuente") or [])
        if source not in files:
            continue
        route = str(item.get("ruta") or "")
        if route and route not in routes:
            routes.append(route)
    return routes[:5]


def _discover_limit_bypass(
    root: Path,
    endpoint_inventory: list[dict[str, Any]],
) -> list[Pilar2Candidate]:
    candidates: list[Pilar2Candidate] = []
    seen: set[tuple[str, int, str]] = set()

    for _path, relative, text in _iter_text_files(root):
        if _source_kind(relative) != "codigo":
            continue
        lower = text.lower()
        for token in _BYPASS_HINTS:
            for match in re.finditer(rf"\b{re.escape(token)}\w*\b", lower):
                start = max(0, match.start() - 900)
                end = min(len(text), match.end() + 1500)
                window = text[start:end]
                window_lower = window.lower()
                if not any(hint in window_lower for hint in _LIMIT_HINTS):
                    continue
                if not any(hint in window_lower for hint in _INPUT_HINTS):
                    continue
                if not re.search(r"\bif\b|\bwhen\b|\bswitch\b|\bcase\b", window_lower):
                    continue

                guard_start = max(0, match.start() - 360)
                guard_end = min(len(text), match.end() + 520)
                guard = text[guard_start:guard_end].lower()
                guarded = any(hint in guard for hint in _AUTH_HINTS)
                line = _line_number(text, match.start())
                parameter = match.group(0)
                key = (relative, line, parameter)
                if key in seen:
                    continue
                seen.add(key)
                routes = _routes_for_source(endpoint_inventory, relative)
                fp = _stable_digest(
                    "LIMIT_BYPASS", relative, line, parameter,
                    "autorizacion_excepcion_limites"
                )
                candidates.append(
                    _candidate(
                        family="LIMIT_BYPASS",
                        root_cause="autorizacion_excepcion_limites",
                        motive=(
                            "Una entrada controlable parece modificar una "
                            "política o límite. La existencia del parámetro no "
                            "confirma vulnerabilidad; requiere prueba diferencial."
                        ),
                        confidence="media" if not guarded else "baja",
                        state="por_confirmar" if not guarded else "candidato",
                        component=relative,
                        file=relative,
                        line=line,
                        parameter=parameter,
                        endpoints=routes,
                        evidence=[
                            {
                                "tipo": "flujo_estatico",
                                "archivo": relative,
                                "linea": line,
                                "parametro_o_rama": parameter,
                                "entrada_http_cercana": True,
                                "limite_cercano": True,
                                "guardia_autorizacion_cercana": guarded,
                            }
                        ],
                        test={
                            "tipo": "limit_differential",
                            "casos": [
                                "usuario normal + operación normal",
                                "usuario normal + opción especial",
                                "usuario privilegiado + opción especial",
                            ],
                            "requiere_payload_seguro": True,
                            "no_destructiva": True,
                        },
                        remediation={
                            "problema": "excepción de política potencialmente no autorizada",
                            "estrategia": (
                                "Autorizar explícitamente la capacidad de "
                                "excepción antes de modificar el límite y "
                                "registrar su uso."
                            ),
                            "verificacion": (
                                "La identidad no autorizada debe ser rechazada; "
                                "la identidad autorizada conserva la excepción."
                            ),
                        },
                        fingerprint=fp,
                    )
                )
    return candidates


def _parse_dockerfile(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    stages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        from_match = re.match(
            r"(?i)^FROM\s+([^\s]+)(?:\s+AS\s+([^\s]+))?", line
        )
        if from_match:
            current = {
                "imagen": from_match.group(1),
                "alias": from_match.group(2),
                "linea_from": index,
                "usuarios": [],
            }
            stages.append(current)
            continue
        if current is None:
            continue
        user_match = re.match(r"(?i)^USER\s+([^\s#]+)", line)
        if user_match:
            current["usuarios"].append(
                {"usuario": user_match.group(1), "linea": index}
            )

    final = stages[-1] if stages else {}
    users = list(final.get("usuarios") or [])
    declared_user = users[-1]["usuario"] if users else None
    return {
        "archivo": path.name,
        "stages": stages,
        "imagen_final": final.get("imagen"),
        "stage_final": final.get("alias"),
        "usuario_dockerfile_final": declared_user,
        "linea_usuario_final": users[-1]["linea"] if users else None,
    }


def _parse_compose(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for name in (
        "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    ):
        path = root / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        current_service: str | None = None
        in_services = False
        services_indent = -1
        for index, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            indent = len(raw) - len(raw.lstrip())
            stripped = raw.strip()
            if re.match(r"^services\s*:\s*$", stripped, re.I):
                in_services = True
                services_indent = indent
                current_service = None
                continue
            if in_services and indent <= services_indent and not stripped.startswith("-"):
                in_services = False
                current_service = None
            if in_services:
                service_match = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*$", stripped)
                if service_match and indent > services_indent:
                    current_service = service_match.group(1)
                    continue

            if not in_services or not current_service:
                continue
            user_match = re.match(r"""(?i)^user\s*:\s*["']?([^"'#\s]+)""", stripped)
            if user_match:
                findings.append(
                    {
                        "archivo": name,
                        "servicio": current_service,
                        "tipo": "user_override",
                        "valor": user_match.group(1),
                        "linea": index,
                    }
                )
            if re.match(r"(?i)^privileged\s*:\s*true\b", stripped):
                findings.append(
                    {
                        "archivo": name,
                        "servicio": current_service,
                        "tipo": "privileged",
                        "valor": True,
                        "linea": index,
                    }
                )
            if re.match(r"""(?i)^(?:network_mode|pid)\s*:\s*["']?host\b""", stripped):
                key = stripped.split(":", 1)[0].strip().lower()
                findings.append(
                    {
                        "archivo": name,
                        "servicio": current_service,
                        "tipo": key,
                        "valor": "host",
                        "linea": index,
                    }
                )
            if "docker.sock" in stripped.lower():
                findings.append(
                    {
                        "archivo": name,
                        "servicio": current_service,
                        "tipo": "docker_socket",
                        "valor": "montado",
                        "linea": index,
                    }
                )
            if re.match(r"(?i)^-?\s*(?:SYS_ADMIN|NET_ADMIN)\b", stripped):
                findings.append(
                    {
                        "archivo": name,
                        "servicio": current_service,
                        "tipo": "capability",
                        "valor": stripped.lstrip("- ").strip(),
                        "linea": index,
                    }
                )
    return findings


def _parse_kubernetes(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path, relative, text in _iter_text_files(root):
        if path.suffix.lower() not in {".yml", ".yaml"}:
            continue
        lower = text.lower()
        if not any(
            token in lower
            for token in ("securitycontext", "runasuser", "runasnonroot", "privileged:")
        ):
            continue
        for index, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            m = re.match(r"(?i)^runAsUser\s*:\s*(\d+)", stripped)
            if m:
                findings.append(
                    {
                        "archivo": relative,
                        "tipo": "runAsUser",
                        "valor": int(m.group(1)),
                        "linea": index,
                    }
                )
            m = re.match(r"(?i)^runAsNonRoot\s*:\s*(true|false)", stripped)
            if m:
                findings.append(
                    {
                        "archivo": relative,
                        "tipo": "runAsNonRoot",
                        "valor": m.group(1).lower() == "true",
                        "linea": index,
                    }
                )
            if re.match(r"(?i)^privileged\s*:\s*true\b", stripped):
                findings.append(
                    {
                        "archivo": relative,
                        "tipo": "privileged",
                        "valor": True,
                        "linea": index,
                    }
                )
    return findings


def analyze_container_security(
    root: Path,
    dockerfile: str = "Dockerfile",
) -> dict[str, Any]:
    docker_path = root / dockerfile
    docker = _parse_dockerfile(docker_path) if docker_path.exists() else {}
    compose = _parse_compose(root)
    kubernetes = _parse_kubernetes(root)

    effective_user = docker.get("usuario_dockerfile_final")
    effective_source = dockerfile if effective_user is not None else None

    for item in compose:
        if item.get("tipo") == "user_override":
            effective_user = str(item.get("valor"))
            effective_source = f"{item.get('archivo')}:{item.get('servicio')}"

    for item in kubernetes:
        if item.get("tipo") == "runAsUser":
            effective_user = str(item.get("valor"))
            effective_source = item.get("archivo")
        elif item.get("tipo") == "runAsNonRoot" and item.get("valor") is True:
            if effective_user in {None, ""}:
                effective_user = "non-root-policy"
                effective_source = item.get("archivo")

    explicit_root = str(effective_user or "").strip().lower() in {
        "0", "0:0", "root", "root:root",
    }
    explicit_non_root = effective_user not in {None, ""} and not explicit_root

    dangerous: list[dict[str, Any]] = []
    for item in [*compose, *kubernetes]:
        if item.get("tipo") in {
            "privileged", "docker_socket", "network_mode", "pid", "capability",
        }:
            dangerous.append(item)
        if item.get("tipo") == "runAsNonRoot" and item.get("valor") is False:
            dangerous.append(item)

    if explicit_root or dangerous:
        state = "confirmado_root_o_privilegios"
        confidence = "alta"
        vulnerable = True
    elif explicit_non_root:
        state = "confirmado_non_root"
        confidence = "alta"
        vulnerable = False
    elif docker:
        state = "probable_root"
        confidence = "media"
        vulnerable = False
    else:
        state = "no_aplica"
        confidence = "alta"
        vulnerable = False

    return {
        "estado_runtime": state,
        "confianza": confidence,
        "vulnerable_confirmado": vulnerable,
        "usuario_efectivo": effective_user,
        "fuente_usuario_efectivo": effective_source,
        "dockerfile": docker,
        "compose": compose,
        "kubernetes": kubernetes,
        "configuraciones_peligrosas": dangerous,
    }


def _discover_container(
    root: Path,
) -> tuple[list[dict[str, Any]], list[Pilar2Candidate]]:
    has_container = any(
        (root / name).exists()
        for name in (
            "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
            "compose.yml", "compose.yaml",
        )
    )
    if not has_container:
        has_container = any(
            path.suffix.lower() in {".yml", ".yaml"}
            and "securitycontext" in text.lower()
            for path, _relative, text in _iter_text_files(root, max_files=1500)
        )
    if not has_container:
        return [], []

    analysis = analyze_container_security(root)
    fp = _stable_digest("CONTAINER", "runtime", "privilegios_contenedor")
    candidate = _candidate(
        family="CONTAINER",
        root_cause="privilegios_contenedor",
        motive=(
            "Se detectó configuración de contenedor. Debe resolverse el "
            "usuario y los privilegios efectivos del runtime final."
        ),
        confidence=str(analysis.get("confianza") or "media"),
        state=(
            "prueba_preparada"
            if analysis.get("estado_runtime") != "no_aplica"
            else "candidato"
        ),
        component="container-runtime",
        file="Dockerfile" if (root / "Dockerfile").exists() else None,
        evidence=[{"tipo": "configuracion_runtime", **analysis}],
        test={
            "tipo": "container_security",
            "no_destructiva": True,
        },
        remediation={
            "problema": "privilegios de contenedor",
            "estrategia": (
                "Resolver el usuario efectivo, crear/utilizar un usuario no "
                "privilegiado, asignar solo los permisos requeridos y eliminar "
                "privilegios, capabilities y mounts innecesarios."
            ),
            "verificacion": (
                "La aplicación debe iniciar con el usuario no privilegiado y "
                "sin privilegios excesivos conservando sus smoke tests."
            ),
        },
        fingerprint=fp,
    )
    check = {
        "id_control": f"P2-AUTO-CONTAINER-{fp[:10].upper()}",
        "nombre": "El runtime del contenedor debe usar privilegios mínimos",
        "tipo": "container_security",
        "familia": "CONTAINER",
        "archivo": "Dockerfile" if (root / "Dockerfile").exists() else None,
        "componente": "container-runtime",
        "confianza": str(analysis.get("confianza") or "media"),
        "causa_raiz": "privilegios_contenedor",
        "fingerprint": fp,
        "autogenerado": True,
        "archivos_fuente": list(
            dict.fromkeys(
                [
                    value
                    for value in [
                        "Dockerfile" if (root / "Dockerfile").exists() else None,
                        *[
                            item.get("archivo")
                            for item in analysis.get("compose") or []
                        ],
                        *[
                            item.get("archivo")
                            for item in analysis.get("kubernetes") or []
                        ],
                    ]
                    if value
                ]
            )
        ),
        "pistas_codigo": [
            "usuario efectivo del runtime",
            "privileged/capabilities/mounts/host modes",
        ],
        "metadata": {
            "estado_runtime_inicial": analysis.get("estado_runtime"),
        },
    }
    return [check], [candidate]


def _discover_simple_config(
    root: Path,
) -> tuple[list[dict[str, Any]], list[Pilar2Candidate]]:
    checks: list[dict[str, Any]] = []
    candidates: list[Pilar2Candidate] = []
    debug_patterns = (
        r"\bapp\.run\s*\([^)]{0,500}\bdebug\s*=\s*True\b",
        r"(?m)^\s*DEBUG\s*=\s*True\s*$",
        r"(?m)^\s*FLASK_DEBUG\s*=\s*1\s*$",
        r"(?m)^\s*debug\s*[:=]\s*true\s*$",
        r"""(?im)["']debug["']\s*:\s*true""",
    )
    cookie_patterns = (
        r"(?im)^\s*SESSION_COOKIE_SECURE\s*=\s*False\s*$",
        r"""(?is)(?:cookie|session).{0,180}\bsecure\s*[:=]\s*false\b""",
    )

    found_debug = False
    found_cookie = False
    for _path, relative, text in _iter_text_files(root):
        if _source_kind(relative) in {"documentacion", "test", "ejemplo"}:
            continue
        if not found_debug:
            for pattern in debug_patterns:
                match = re.search(pattern, text, re.I | re.M | re.S)
                if not match:
                    continue
                fp = _stable_digest("DEBUG", relative, "configuracion_debug")
                checks.append(
                    {
                        "id_control": f"P2-AUTO-DEBUG-{fp[:10].upper()}",
                        "nombre": (
                            "La configuración desplegable no debe habilitar debug"
                        ),
                        "tipo": "source_regex",
                        "familia": "DEBUG",
                        "archivo": relative,
                        "patron_inseguro": pattern,
                        "componente": relative,
                        "confianza": "media-alta",
                        "causa_raiz": "configuracion_debug",
                        "fingerprint": fp,
                        "autogenerado": True,
                        "archivos_fuente": [relative],
                        "pistas_codigo": ["debug habilitado explícitamente"],
                    }
                )
                candidates.append(
                    _candidate(
                        family="DEBUG",
                        root_cause="configuracion_debug",
                        motive="Debug explícito en configuración desplegable.",
                        confidence="media-alta",
                        state="prueba_preparada",
                        component=relative,
                        file=relative,
                        line=_line_number(text, match.start()),
                        fingerprint=fp,
                    )
                )
                found_debug = True
                break

        if not found_cookie:
            for pattern in cookie_patterns:
                match = re.search(pattern, text, re.I | re.M | re.S)
                if not match:
                    continue
                fp = _stable_digest("SESSION", relative, "configuracion_sesion")
                checks.append(
                    {
                        "id_control": f"P2-AUTO-SESSION-{fp[:10].upper()}",
                        "nombre": (
                            "Las cookies de sesión desplegables deben usar Secure"
                        ),
                        "tipo": "source_regex",
                        "familia": "SESSION",
                        "archivo": relative,
                        "patron_inseguro": pattern,
                        "componente": relative,
                        "confianza": "media-alta",
                        "causa_raiz": "configuracion_sesion",
                        "fingerprint": fp,
                        "autogenerado": True,
                        "archivos_fuente": [relative],
                        "pistas_codigo": ["cookie/session Secure=false"],
                    }
                )
                candidates.append(
                    _candidate(
                        family="SESSION",
                        root_cause="configuracion_sesion",
                        motive=(
                            "Cookie de sesión desplegable declara Secure=false."
                        ),
                        confidence="media-alta",
                        state="prueba_preparada",
                        component=relative,
                        file=relative,
                        line=_line_number(text, match.start()),
                        fingerprint=fp,
                    )
                )
                found_cookie = True
                break
        if found_debug and found_cookie:
            break

    return checks, candidates


def discover_pilar2_profile(
    root: str | Path,
    endpoint_inventory: list[dict[str, Any]],
    *,
    languages: list[str] | None = None,
    frameworks: list[str] | None = None,
) -> dict[str, Any]:
    """Descubre candidatos y controles P2 sin memorizar una aplicación.

    Los candidatos ambiguos se conservan para revisión/prueba posterior.
    Solamente se materializan controles ejecutables cuando Aegis dispone de
    una prueba no destructiva o de contexto estático suficientemente fuerte.
    """
    target = Path(root).resolve()
    checks: list[dict[str, Any]] = []
    candidates: list[Pilar2Candidate] = []

    cors_checks, cors_candidates = _discover_cors(target, endpoint_inventory)
    checks.extend(cors_checks)
    candidates.extend(cors_candidates)

    secret_checks, secret_candidates = _discover_secrets(target)
    checks.extend(secret_checks)
    candidates.extend(secret_candidates)

    candidates.extend(_discover_limit_bypass(target, endpoint_inventory))

    container_checks, container_candidates = _discover_container(target)
    checks.extend(container_checks)
    candidates.extend(container_candidates)

    simple_checks, simple_candidates = _discover_simple_config(target)
    checks.extend(simple_checks)
    candidates.extend(simple_candidates)

    unique_checks: list[dict[str, Any]] = []
    seen_checks: set[str] = set()
    for check in checks:
        control_id = str(check.get("id_control") or "")
        if not control_id or control_id in seen_checks:
            continue
        seen_checks.add(control_id)
        unique_checks.append(check)

    unique_candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for candidate in candidates:
        item = candidate.as_dict()
        candidate_id = item["candidate_id"]
        if candidate_id in seen_candidates:
            continue
        seen_candidates.add(candidate_id)
        unique_candidates.append(item)

    return {
        "version_motor": 4,
        "modo": "descubrimiento-correlacion-prueba-evidencia",
        "checks": unique_checks,
        "candidates": unique_candidates,
        "familias_detectadas": sorted(
            {
                str(item.get("familia") or "")
                for item in [*unique_checks, *unique_candidates]
                if item.get("familia")
            }
        ),
        "lenguajes": list(languages or []),
        "frameworks": list(frameworks or []),
        "principios": [
            "control != hallazgo",
            "candidato estático != vulnerabilidad confirmada",
            "pruebas preferentemente no destructivas",
            "deduplicación por causa raíz y fingerprint semántico",
            "corrección contextual y reverificación obligatoria",
        ],
    }