"""Detección genérica de proyectos y construcción de perfiles borrador."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
    ".java", ".kt", ".kts", ".php", ".cs", ".go", ".rb", ".rs",
    ".scala", ".swift", ".dart", ".ex", ".exs", ".vue", ".svelte",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".jsp", ".html", ".htm", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".properties", ".gradle", ".sh", ".ps1", ".bat", ".cmd",
    ".sql", ".env", ".ini", ".conf", ".cfg", ".txt", ".csv",
    ".md", ".markdown", ".mdown", ".rst", ".adoc", ".asciidoc",
    ".http", ".rest", ".graphql", ".gql", ".proto", ".wsdl", ".xsd",
    ".log", ".out", ".cnf", ".config", ".prefs",
}

DOCUMENT_EXTENSIONS = {
    ".md", ".markdown", ".mdown", ".rst", ".adoc", ".asciidoc",
    ".txt", ".http", ".rest",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
    ".pdf", ".zip", ".7z", ".rar", ".gz", ".tar", ".tgz",
    ".jar", ".war", ".ear", ".class", ".pyc", ".pyo",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav",
}

MAX_TEXT_SCAN_BYTES = 5_000_000

IGNORE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    "node_modules", "target", "build", "dist", ".venv", "venv",
    "vendor", "bin", "obj", "coverage", ".next", ".nuxt",
}


@dataclass
class DetectedRoute:
    method: str
    path: str
    source: str
    framework: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "metodo": self.method,
            "ruta": self.path,
            "archivo": self.source,
            "framework": self.framework,
            "tipo_fuente": _source_kind(self.source),
        }


@dataclass
class ProjectDetection:
    root: Path
    name: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    source_roots: list[str] = field(default_factory=list)
    routes: list[DetectedRoute] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    package_descriptor: dict[str, Any] | None = None
    version: str | None = None
    version_source: str | None = None
    version_confidence: str | None = None
    version_candidates: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    account_sources: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "name": self.name,
            "languages": list(self.languages),
            "frameworks": list(self.frameworks),
            "manifests": list(self.manifests),
            "source_roots": list(self.source_roots),
            "routes": [route.as_dict() for route in self.routes],
            "runtime": self.runtime,
            "package_descriptor": self.package_descriptor,
            "version": self.version,
            "version_source": self.version_source,
            "version_confidence": self.version_confidence,
            "version_candidates": list(self.version_candidates),
            "accounts": list(self.accounts),
            "account_sources": list(self.account_sources),
            "notes": list(self.notes),
        }


def _read_text(path: Path, limit: int = 500_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _looks_like_text_file(path: Path) -> bool:
    """Acepta archivos desconocidos si su contenido parece texto."""
    try:
        size = path.stat().st_size
        if size == 0:
            return True
        if size > MAX_TEXT_SCAN_BYTES:
            return False
        if path.suffix.lower() in BINARY_EXTENSIONS:
            return False
        sample = path.read_bytes()[:8192]
    except OSError:
        return False

    if b"\x00" in sample:
        return False
    if not sample:
        return True

    printable = sum(
        1
        for byte in sample
        if byte in b"\t\n\r"
        or 32 <= byte <= 126
        or byte >= 128
    )
    return printable / len(sample) >= 0.85

def _source_kind(source: str) -> str:
    path = Path(source)
    suffix = path.suffix.lower()
    name = path.name.lower()
    lower_parts = {part.lower() for part in path.parts}

    if (
        suffix in DOCUMENT_EXTENSIONS
        or name.startswith("readme")
        or "manual" in name
        or "guide" in name
        or "guia" in name
        or "document" in name
        or "docs" in lower_parts
        or "documentation" in lower_parts
    ):
        return "documentacion"

    if suffix in {
        ".env", ".ini", ".conf", ".cfg", ".cnf", ".config",
        ".properties", ".yaml", ".yml", ".toml", ".json",
        ".xml", ".sql", ".csv",
    }:
        return "configuracion"

    if suffix in {
        ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
        ".java", ".kt", ".kts", ".php", ".cs", ".go", ".rb",
        ".rs", ".scala", ".swift", ".dart", ".ex", ".exs",
        ".jsp", ".html", ".htm", ".vue", ".svelte",
    }:
        return "codigo"

    return "texto"


def _iter_source_files(
    root: Path,
    max_files: int | None = 4000,
):
    count = 0
    for path in root.rglob("*"):
        if max_files is not None and count >= max_files:
            break
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in IGNORE_DIRS for part in relative.parts):
            continue
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        name = path.name.lower()
        special_text_name = (
            name == ".env"
            or name.startswith(".env.")
            or name.startswith("readme")
            or name.startswith("manual")
            or name.startswith("guide")
            or name.startswith("guia")
            or name in {
                "passwd", "users", "accounts", "usuarios",
                "seed", "seeds", "dockerfile", "makefile", "procfile",
            }
        )
        if (
            suffix not in TEXT_EXTENSIONS
            and not special_text_name
            and not _looks_like_text_file(path)
        ):
            continue
        count += 1
        yield path, relative


def _load_package_descriptor(root: Path) -> dict[str, Any] | None:
    path = root / "auditor-package.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _detect_stack(root: Path) -> tuple[list[str], list[str], list[str]]:
    languages: set[str] = set()
    frameworks: set[str] = set()
    manifests: list[str] = []

    manifest_names = {
        "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
        "pom.xml", "build.gradle", "build.gradle.kts", "composer.json",
        "Gemfile", "go.mod", "Cargo.toml", "Dockerfile",
        "pubspec.yaml", "Package.swift", "mix.exs", "build.sbt",
        "CMakeLists.txt", "Makefile", "yarn.lock", "pnpm-lock.yaml",
        "package-lock.json", "docker-compose.yml", "docker-compose.yaml",
        "compose.yml", "compose.yaml",
    }

    for name in manifest_names:
        if (root / name).exists():
            manifests.append(name)

    package = root / "package.json"
    if package.exists():
        languages.add("javascript")
        text = _read_text(package)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        deps = {
            **(data.get("dependencies") or {}),
            **(data.get("devDependencies") or {}),
        }
        for key, label in (
            ("express", "express"),
            ("next", "nextjs"),
            ("@nestjs/core", "nestjs"),
            ("koa", "koa"),
            ("fastify", "fastify"),
        ):
            if key in deps:
                frameworks.add(label)
        if any((root / p).exists() for p in ("tsconfig.json",)):
            languages.add("typescript")

    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        languages.add("python")
        text = _read_text(root / "requirements.txt") + _read_text(root / "pyproject.toml")
        lower = text.lower()
        for token, label in (
            ("flask", "flask"),
            ("django", "django"),
            ("fastapi", "fastapi"),
        ):
            if token in lower:
                frameworks.add(label)

    if (root / "pom.xml").exists() or (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        languages.add("java")
        text = (
            _read_text(root / "pom.xml")
            + _read_text(root / "build.gradle")
            + _read_text(root / "build.gradle.kts")
        ).lower()
        if "spring-boot" in text:
            frameworks.add("spring-boot")
        if "servlet" in text or (root / "src" / "main" / "webapp").exists():
            frameworks.add("servlet")

    if (root / "composer.json").exists():
        languages.add("php")
        text = _read_text(root / "composer.json").lower()
        if "laravel/framework" in text:
            frameworks.add("laravel")
        if "moodle" in text or (root / "version.php").exists():
            frameworks.add("moodle")

    if (root / "version.php").exists() and (root / "config-dist.php").exists():
        languages.add("php")
        frameworks.add("moodle")

    if any(root.glob("*.csproj")) or any(root.rglob("*.csproj")):
        languages.add("csharp")
        frameworks.add("dotnet")

    if (root / "go.mod").exists():
        languages.add("go")
        text = _read_text(root / "go.mod").lower()
        for token, label in (
            ("github.com/gin-gonic/gin", "gin"),
            ("github.com/gofiber/fiber", "fiber"),
            ("github.com/labstack/echo", "echo"),
        ):
            if token in text:
                frameworks.add(label)

    if (root / "Gemfile").exists():
        languages.add("ruby")
        text = _read_text(root / "Gemfile").lower()
        if "rails" in text:
            frameworks.add("rails")
        if "sinatra" in text:
            frameworks.add("sinatra")

    if (root / "Cargo.toml").exists():
        languages.add("rust")
        text = _read_text(root / "Cargo.toml").lower()
        for token, label in (
            ("actix-web", "actix-web"),
            ("axum", "axum"),
            ("rocket", "rocket"),
        ):
            if token in text:
                frameworks.add(label)

    if (root / "pubspec.yaml").exists():
        languages.add("dart")
        text = _read_text(root / "pubspec.yaml").lower()
        if "flutter:" in text:
            frameworks.add("flutter")

    if (root / "Package.swift").exists():
        languages.add("swift")
        frameworks.add("swift-package")

    if (root / "mix.exs").exists():
        languages.add("elixir")
        text = _read_text(root / "mix.exs").lower()
        if "phoenix" in text:
            frameworks.add("phoenix")

    if (root / "build.sbt").exists():
        languages.add("scala")
        text = _read_text(root / "build.sbt").lower()
        if "play" in text:
            frameworks.add("play")

    if (root / "composer.json").exists():
        text = _read_text(root / "composer.json").lower()
        if "symfony/" in text:
            frameworks.add("symfony")

    if (root / "wp-config-sample.php").exists() or (root / "wp-includes").exists():
        languages.add("php")
        frameworks.add("wordpress")

    for csproj in list(root.glob("*.csproj")) + list(root.rglob("*.csproj"))[:20]:
        text = _read_text(csproj).lower()
        if "microsoft.net.sdk.web" in text:
            frameworks.add("aspnet-core")
            break

    # Inferencia por extensiones como fallback para proyectos sin manifiesto.
    extension_languages = {
        ".java": "java",
        ".kt": "kotlin",
        ".kts": "kotlin",
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".php": "php",
        ".cs": "csharp",
        ".go": "go",
        ".rb": "ruby",
        ".rs": "rust",
        ".scala": "scala",
        ".swift": "swift",
        ".dart": "dart",
        ".ex": "elixir",
        ".exs": "elixir",
        ".c": "c",
        ".cc": "cpp",
        ".cpp": "cpp",
    }
    extension_counts: dict[str, int] = {}
    for path, _relative in _iter_source_files(root, max_files=800):
        language = extension_languages.get(path.suffix.lower())
        if language:
            extension_counts[language] = extension_counts.get(language, 0) + 1
    for language, count in extension_counts.items():
        if count >= 1:
            languages.add(language)

    return sorted(languages), sorted(frameworks), sorted(manifests)


def _detect_source_roots(root: Path) -> list[str]:
    candidates = [
        "src", "app", "server", "backend", "api", "lib", "cmd",
        "internal", "pkg", "web", "public", "vulndesk",
        "src/main/java", "src/main/kotlin", "src/main/webapp",
        "routes", "controllers",
    ]
    roots = [candidate for candidate in candidates if (root / candidate).exists()]
    return roots or ["."]


def _normalize_route_path(value: str) -> str:
    route = str(value or "").strip()
    if not route:
        return "/"
    route = route.replace("\\/", "/")
    route = re.sub(r"https?://[^/]+", "", route)
    route = route.split("?", 1)[0]
    route = re.sub(r"/{2,}", "/", route)
    if not route.startswith("/"):
        route = "/" + route
    if len(route) > 1 and route.endswith("/"):
        route = route[:-1]
    return route or "/"


def _join_route_paths(prefix: str, route: str) -> str:
    left = _normalize_route_path(prefix)
    right = _normalize_route_path(route)
    if left == "/":
        return right
    if right == "/":
        return left
    return _normalize_route_path(
        left.rstrip("/") + "/" + right.lstrip("/")
    )


def _literal_methods(text: str) -> list[str]:
    methods = re.findall(
        r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b",
        text or "",
        re.I,
    )
    return [method.upper() for method in methods]


def _extract_routes(root: Path) -> list[DetectedRoute]:
    """Inventaría rutas declaradas estáticamente en todo el proyecto.

    No impone un máximo de archivos ni de endpoints. Deduplica por método,
    ruta y archivo y conserva el framework/origen que permitió detectarlos.
    """

    found: dict[tuple[str, str, str], DetectedRoute] = {}

    def add(
        method: str,
        route: str,
        source: str,
        framework: str,
    ) -> None:
        method = (method or "ANY").upper().strip()
        route = _normalize_route_path(route)
        if not route:
            return
        lower_route = route.lower()
        if re.search(
            r"\.(?:css|js|mjs|map|png|jpg|jpeg|gif|svg|ico|woff2?|ttf|eot)(?:$|/)",
            lower_route,
        ):
            return
        key = (method, route, source)
        found[key] = DetectedRoute(
            method=method,
            path=route,
            source=source,
            framework=framework,
        )

    def scan_json_endpoint_refs(
        value: Any,
        *,
        source: str,
    ) -> None:
        if isinstance(value, dict):
            method_value = value.get("method") or value.get("metodo")
            url_value = (
                value.get("url")
                or value.get("endpoint")
                or value.get("route")
                or value.get("ruta")
            )

            if isinstance(url_value, dict):
                raw = url_value.get("raw")
                path_parts = url_value.get("path")
                if raw:
                    url_value = raw
                elif isinstance(path_parts, list):
                    url_value = "/" + "/".join(
                        str(part).strip("/")
                        for part in path_parts
                    )

            if (
                isinstance(method_value, str)
                and isinstance(url_value, str)
                and method_value.upper()
                in {
                    "GET", "POST", "PUT", "PATCH",
                    "DELETE", "OPTIONS", "HEAD",
                }
                and (
                    url_value.startswith("/")
                    or url_value.startswith("http://")
                    or url_value.startswith("https://")
                )
            ):
                add(
                    method_value,
                    url_value,
                    source,
                    "json-endpoint-reference",
                )

            for nested in value.values():
                scan_json_endpoint_refs(
                    nested,
                    source=source,
                )

        elif isinstance(value, list):
            for nested in value:
                scan_json_endpoint_refs(
                    nested,
                    source=source,
                )

    for path, relative in _iter_source_files(
        root,
        max_files=None,
    ):
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue

        source = relative.as_posix()
        suffix = path.suffix.lower()
        name = path.name.lower()

        # Flask / FastAPI / Starlette.
        for match in re.finditer(
            r"@(?:app|router|bp|blueprint|\w+)"
            r"\.(get|post|put|patch|delete|options|head)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            add(
                match.group(1),
                match.group(2),
                source,
                "python-router",
            )

        for match in re.finditer(
            r"@(?:app|router|bp|blueprint|\w+)\.route"
            r"\(\s*['\"]([^'\"]+)['\"]([^)]*)\)",
            text,
            re.I | re.S,
        ):
            methods = _literal_methods(match.group(2)) or ["GET"]
            for method in methods:
                add(
                    method,
                    match.group(1),
                    source,
                    "python-route",
                )

        # Express / Fastify / generic JS routers.
        for match in re.finditer(
            r"\b(?:app|router|server|fastify|\w+)"
            r"\.(get|post|put|patch|delete|options|head|all)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            method = match.group(1).upper()
            add(
                "ANY" if method == "ALL" else method,
                match.group(2),
                source,
                "javascript-router",
            )

        # Fastify object form.
        for match in re.finditer(
            r"\.route\s*\(\s*\{(.{0,1600}?)\}\s*\)",
            text,
            re.I | re.S,
        ):
            block = match.group(1)
            url_match = re.search(
                r"\b(?:url|path)\s*:\s*['\"]([^'\"]+)['\"]",
                block,
                re.I,
            )
            method_match = re.search(
                r"\bmethod\s*:\s*['\"]([^'\"]+)['\"]",
                block,
                re.I,
            )
            if url_match:
                methods = (
                    _literal_methods(method_match.group(1))
                    if method_match
                    else ["ANY"]
                )
                for method in methods or ["ANY"]:
                    add(
                        method,
                        url_match.group(1),
                        source,
                        "fastify",
                    )

        # NestJS: combina prefijo Controller + decoradores de método.
        controller_match = re.search(
            r"@Controller\(\s*['\"]([^'\"]*)['\"]\s*\)",
            text,
            re.I,
        )
        nest_prefix = (
            controller_match.group(1)
            if controller_match
            else ""
        )
        for match in re.finditer(
            r"@(Get|Post|Put|Patch|Delete|Options|Head)"
            r"\(\s*(?:['\"]([^'\"]*)['\"])?\s*\)",
            text,
            re.I,
        ):
            add(
                match.group(1),
                _join_route_paths(
                    nest_prefix,
                    match.group(2) or "/",
                ),
                source,
                "nestjs",
            )

        # Spring MVC/WebFlux.
        spring_prefix = ""
        class_pos = re.search(
            r"\b(?:class|interface)\s+\w+",
            text,
        )
        if class_pos:
            before_class = text[:class_pos.start()]
            mappings = list(
                re.finditer(
                    r"@RequestMapping\(\s*"
                    r"(?:value\s*=\s*|path\s*=\s*)?"
                    r"['\"]([^'\"]+)['\"]",
                    before_class,
                    re.I,
                )
            )
            if mappings:
                spring_prefix = mappings[-1].group(1)

        for match in re.finditer(
            r"@(Get|Post|Put|Patch|Delete)Mapping"
            r"\(\s*(?:value\s*=\s*|path\s*=\s*)?"
            r"['\"]([^'\"]*)['\"]",
            text,
            re.I,
        ):
            add(
                match.group(1),
                _join_route_paths(
                    spring_prefix,
                    match.group(2) or "/",
                ),
                source,
                "spring",
            )

        for match in re.finditer(
            r"@(Get|Post|Put|Patch|Delete)Mapping\b(?!\s*\()",
            text,
            re.I,
        ):
            add(
                match.group(1),
                spring_prefix or "/",
                source,
                "spring",
            )

        for match in re.finditer(
            r"@RequestMapping\((.{0,1200}?)\)",
            text,
            re.I | re.S,
        ):
            block = match.group(1)
            route_match = re.search(
                r"(?:value|path)\s*=\s*['\"]([^'\"]+)['\"]",
                block,
                re.I,
            )
            if not route_match:
                route_match = re.search(
                    r"^\s*['\"]([^'\"]+)['\"]",
                    block,
                )
            if not route_match:
                continue
            methods = re.findall(
                r"RequestMethod\.(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)",
                block,
                re.I,
            ) or ["ANY"]
            for method in methods:
                add(
                    method,
                    _join_route_paths(
                        spring_prefix,
                        route_match.group(1),
                    ),
                    source,
                    "spring-request-mapping",
                )

        # Servlet annotations.
        for match in re.finditer(
            r"@WebServlet\s*\((.{0,1200}?)\)",
            text,
            re.I | re.S,
        ):
            block = match.group(1)
            urls = re.findall(
                r"['\"](/[^'\"]+)['\"]",
                block,
            )
            for route in urls:
                add("ANY", route, source, "servlet")

        # JAX-RS.
        class_path_match = re.search(
            r"@Path\(\s*['\"]([^'\"]+)['\"]\s*\)"
            r".{0,1000}?\bclass\b",
            text,
            re.I | re.S,
        )
        jax_prefix = (
            class_path_match.group(1)
            if class_path_match
            else ""
        )
        for match in re.finditer(
            r"@(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b"
            r"(.{0,500}?)(?=@(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b|\bpublic\b|\bprivate\b|\bprotected\b|$)",
            text,
            re.I | re.S,
        ):
            path_match = re.search(
                r"@Path\(\s*['\"]([^'\"]+)['\"]\s*\)",
                match.group(2),
                re.I,
            )
            add(
                match.group(1),
                _join_route_paths(
                    jax_prefix,
                    path_match.group(1)
                    if path_match
                    else "/",
                ),
                source,
                "jax-rs",
            )

        # web.xml.
        if name == "web.xml" or suffix == ".xml":
            for match in re.finditer(
                r"<servlet-mapping\b[^>]*>.*?"
                r"<url-pattern>\s*([^<]+)\s*</url-pattern>.*?"
                r"</servlet-mapping>",
                text,
                re.I | re.S,
            ):
                add(
                    "ANY",
                    match.group(1),
                    source,
                    "web.xml",
                )

        # Django.
        if name == "urls.py" or suffix == ".py":
            for match in re.finditer(
                r"\b(?:path|re_path)\(\s*[rRuUfF]*['\"]([^'\"]+)['\"]",
                text,
            ):
                add(
                    "ANY",
                    "/" + match.group(1).lstrip("^/"),
                    source,
                    "django",
                )

        # Laravel / Symfony.
        for match in re.finditer(
            r"Route::(get|post|put|patch|delete|options|any)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            method = match.group(1).upper()
            add(
                "ANY" if method == "ANY" else method,
                match.group(2),
                source,
                "laravel",
            )

        for match in re.finditer(
            r"Route::match\(\s*\[([^\]]+)\]\s*,\s*"
            r"['\"]([^'\"]+)['\"]",
            text,
            re.I | re.S,
        ):
            for method in _literal_methods(match.group(1)) or ["ANY"]:
                add(
                    method,
                    match.group(2),
                    source,
                    "laravel",
                )

        for match in re.finditer(
            r"(?:#\[Route|@Route)\(\s*['\"]([^'\"]+)['\"]"
            r"([^)]*)\)",
            text,
            re.I | re.S,
        ):
            methods = _literal_methods(match.group(2)) or ["ANY"]
            for method in methods:
                add(
                    method,
                    match.group(1),
                    source,
                    "symfony",
                )

        # ASP.NET attributes and Minimal APIs.
        asp_route = re.search(
            r"\[Route\(\s*['\"]([^'\"]+)['\"]\s*\)\]",
            text,
            re.I,
        )
        asp_prefix = asp_route.group(1) if asp_route else ""
        controller_name = re.search(
            r"\bclass\s+(\w+)Controller\b",
            text,
        )
        if controller_name:
            asp_prefix = re.sub(
                r"\[controller\]",
                controller_name.group(1),
                asp_prefix,
                flags=re.I,
            )

        for match in re.finditer(
            r"\[Http(Get|Post|Put|Patch|Delete|Options|Head)"
            r"(?:\(\s*['\"]([^'\"]*)['\"]\s*\))?\]",
            text,
            re.I,
        ):
            add(
                match.group(1),
                _join_route_paths(
                    asp_prefix,
                    match.group(2) or "/",
                ),
                source,
                "aspnet-core",
            )

        for match in re.finditer(
            r"\bapp\.Map(Get|Post|Put|Patch|Delete|Methods)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            add(
                match.group(1)
                if match.group(1).lower() != "methods"
                else "ANY",
                match.group(2),
                source,
                "aspnet-minimal",
            )

        # Go routers and net/http.
        for match in re.finditer(
            r"\.(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|Any)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
        ):
            method = match.group(1).upper()
            add(
                "ANY" if method == "ANY" else method,
                match.group(2),
                source,
                "go-router",
            )

        for match in re.finditer(
            r"\b(?:http\.)?HandleFunc\(\s*['\"]([^'\"]+)['\"]",
            text,
        ):
            add(
                "ANY",
                match.group(1),
                source,
                "go-net-http",
            )

        # Rails / Sinatra / Phoenix.
        for match in re.finditer(
            r"^\s*(get|post|put|patch|delete|options)\s+"
            r"['\"]([^'\"]+)['\"]",
            text,
            re.I | re.M,
        ):
            add(
                match.group(1),
                match.group(2),
                source,
                "ruby-or-phoenix",
            )

        for match in re.finditer(
            r"^\s*resources\s+:(\w+)",
            text,
            re.M,
        ):
            resource = "/" + match.group(1)
            add("GET", resource, source, "rails-resources")
            add("POST", resource, source, "rails-resources")
            add("GET", resource + "/:id", source, "rails-resources")
            add("PUT", resource + "/:id", source, "rails-resources")
            add("PATCH", resource + "/:id", source, "rails-resources")
            add("DELETE", resource + "/:id", source, "rails-resources")

        # Rust.
        for match in re.finditer(
            r"#\[(get|post|put|patch|delete|head|options)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            add(
                match.group(1),
                match.group(2),
                source,
                "rust-route",
            )

        for match in re.finditer(
            r"\.route\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
            r"(.{0,800}?)\)",
            text,
            re.I | re.S,
        ):
            methods = re.findall(
                r"\b(get|post|put|patch|delete|head|options)\s*\(",
                match.group(2),
                re.I,
            ) or ["ANY"]
            for method in methods:
                add(
                    method,
                    match.group(1),
                    source,
                    "axum",
                )

        # Play Framework route files.
        if name == "routes" or name.endswith(".routes"):
            for match in re.finditer(
                r"^\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+"
                r"(/\S+)",
                text,
                re.M,
            ):
                add(
                    match.group(1),
                    match.group(2),
                    source,
                    "play",
                )

        # OpenAPI/Swagger, Postman, Insomnia y JSON de configuración.
        if suffix == ".json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}

            if isinstance(payload, dict):
                paths = payload.get("paths")
                if isinstance(paths, dict):
                    for route, operations in paths.items():
                        if not isinstance(operations, dict):
                            add("ANY", route, source, "openapi")
                            continue
                        for method in operations:
                            if method.upper() in {
                                "GET", "POST", "PUT", "PATCH",
                                "DELETE", "OPTIONS", "HEAD",
                            }:
                                add(
                                    method,
                                    route,
                                    source,
                                    "openapi",
                                )

                scan_json_endpoint_refs(
                    payload,
                    source=source,
                )

        # Documentación, manuales y archivos REST:
        # GET /api/users
        # POST https://host/api/login
        # curl -X PATCH https://host/api/profile
        for match in re.finditer(
            r"(?im)(?:^|[|>\s])"
            r"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)"
            r"\s*(?:\||:|-)?\s*"
            r"(https?://[^\s|<>()]+|"
            r"/[A-Za-z0-9_~!$&'()*+,;=:@%{}./?\-]+)",
            text,
        ):
            add(
                match.group(1),
                match.group(2),
                source,
                "documentation-reference",
            )

        for match in re.finditer(
            r"(?is)\bcurl\b(.{0,1000}?)(https?://[^\s'\"<>]+)",
            text,
        ):
            options = match.group(1)
            method_match = re.search(
                r"(?:-X|--request)\s+"
                r"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)",
                options,
                re.I,
            )
            add(
                method_match.group(1) if method_match else "GET",
                match.group(2),
                source,
                "documentation-curl",
            )

        for match in re.finditer(
            r"(?im)^\s*(?:[-*+]\s*)?"
            r"(?:api[_\s-]?endpoint|endpoint(?:_url)?|"
            r"service[_\s-]?url|api[_\s-]?url|route|ruta)"
            r"\s*[:=]\s*['\"]?"
            r"(https?://[^\s'\"|]+|"
            r"/[A-Za-z0-9_~!$&'()*+,;=:@%{}./?\-]+)",
            text,
            re.I,
        ):
            add(
                "ANY",
                match.group(1),
                source,
                "configuration-reference",
            )

        # Referencias de cliente: ayudan a descubrir rutas usadas por
        # JSP/HTML/JS cuando la declaración del servidor no es visible.
        for match in re.finditer(
            r"<form\b([^>]*?)\baction\s*=\s*['\"]([^'\"]+)['\"]([^>]*)>",
            text,
            re.I | re.S,
        ):
            attrs = match.group(1) + match.group(3)
            method_match = re.search(
                r"\bmethod\s*=\s*['\"](get|post)['\"]",
                attrs,
                re.I,
            )
            add(
                method_match.group(1) if method_match else "GET",
                match.group(2),
                source,
                "client-form-reference",
            )

        for match in re.finditer(
            r"\bfetch\(\s*['\"]([^'\"]+)['\"]\s*"
            r"(?:,\s*\{(.{0,1200}?)\})?",
            text,
            re.I | re.S,
        ):
            options = match.group(2) or ""
            method_match = re.search(
                r"\bmethod\s*:\s*['\"]"
                r"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)['\"]",
                options,
                re.I,
            )
            add(
                method_match.group(1) if method_match else "GET",
                match.group(1),
                source,
                "client-fetch-reference",
            )

        for match in re.finditer(
            r"\baxios\.(get|post|put|patch|delete|options|head)"
            r"\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            add(
                match.group(1),
                match.group(2),
                source,
                "client-axios-reference",
            )

        for match in re.finditer(
            r"\$\.(get|post)\(\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        ):
            add(
                match.group(1),
                match.group(2),
                source,
                "client-jquery-reference",
            )

        # OpenAPI/Swagger YAML inventories.
        if suffix in {".yaml", ".yml"} and (
            "openapi:" in text.lower()
            or "swagger:" in text.lower()
            or re.search(r"(?m)^\s*paths\s*:\s*$", text)
        ):
            current_openapi_path: str | None = None
            in_paths = False
            paths_indent = 0
            for line in text.splitlines():
                if re.match(r"^\s*paths\s*:\s*$", line):
                    in_paths = True
                    paths_indent = len(line) - len(line.lstrip())
                    current_openapi_path = None
                    continue
                if not in_paths:
                    continue
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                if stripped and indent <= paths_indent:
                    in_paths = False
                    current_openapi_path = None
                    continue
                route_match = re.match(
                    r"^\s*(/[^:]+)\s*:\s*$",
                    line,
                )
                if route_match:
                    current_openapi_path = route_match.group(1)
                    continue
                if current_openapi_path:
                    method_match = re.match(
                        r"^\s*(get|post|put|patch|delete|options|head)\s*:\s*$",
                        line,
                        re.I,
                    )
                    if method_match:
                        add(
                            method_match.group(1),
                            current_openapi_path,
                            source,
                            "openapi",
                        )

        # Next.js API file-system routes.
        relative_posix = relative.as_posix()
        next_match = re.search(
            r"(?:^|/)pages/api/(.+)\.(?:js|jsx|ts|tsx)$",
            relative_posix,
            re.I,
        )
        if next_match:
            route = "/api/" + next_match.group(1)
            route = re.sub(
                r"/index$",
                "",
                route,
                flags=re.I,
            )
            route = re.sub(
                r"\[([^\]]+)\]",
                r":\1",
                route,
            )
            methods = _literal_methods(text) or ["ANY"]
            for method in methods:
                add(method, route, source, "nextjs-pages")

        app_api_match = re.search(
            r"(?:^|/)app/api/(.+)/route\.(?:js|ts)$",
            relative_posix,
            re.I,
        )
        if app_api_match:
            route = "/api/" + app_api_match.group(1)
            route = re.sub(
                r"\[([^\]]+)\]",
                r":\1",
                route,
            )
            exported = re.findall(
                r"\b(?:export\s+)?(?:async\s+)?function\s+"
                r"(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b",
                text,
                re.I,
            ) or ["ANY"]
            for method in exported:
                add(method, route, source, "nextjs-app")

    return sorted(
        found.values(),
        key=lambda item: (
            item.path,
            item.method,
            item.source,
        ),
    )


def _build_endpoint_inventory(
    routes: list[DetectedRoute],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for route in routes:
        key = (route.method.upper(), route.path)
        item = grouped.setdefault(
            key,
            {
                "metodo": route.method.upper(),
                "ruta": route.path,
                "archivo": route.source,
                "framework": route.framework,
                "archivos": [],
                "frameworks": [],
                "tipos_fuente": [],
            },
        )
        if route.source and route.source not in item["archivos"]:
            item["archivos"].append(route.source)
        if (
            route.framework
            and route.framework not in item["frameworks"]
        ):
            item["frameworks"].append(route.framework)

        source_kind = _source_kind(route.source)
        if source_kind not in item["tipos_fuente"]:
            item["tipos_fuente"].append(source_kind)

    return sorted(
        grouped.values(),
        key=lambda item: (
            item["ruta"],
            item["metodo"],
        ),
    )


def _runtime_from_descriptor(descriptor: dict[str, Any] | None) -> dict[str, Any] | None:
    if not descriptor:
        return None
    build = descriptor.get("build")
    if not isinstance(build, dict):
        return None

    runtime: dict[str, Any] = {
        "modo": "process",
        "directorio_trabajo": ".",
        "espera_inicio": 2.0,
        "variables": {},
    }

    start = build.get("start")
    install = build.get("install")
    if isinstance(start, str) and start.strip():
        runtime["comando_inicio"] = start.strip().split()
    if isinstance(install, str) and install.strip():
        runtime["preparar_automaticamente"] = True
        runtime["comandos_preparacion"] = [install.strip().split()]

    return runtime if runtime.get("comando_inicio") else None


def _detect_runtime(
    root: Path,
    languages: list[str],
    frameworks: list[str],
    descriptor: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    from_descriptor = _runtime_from_descriptor(descriptor)
    if from_descriptor:
        return from_descriptor, "http://127.0.0.1:8000"

    base = {
        "modo": "process",
        "comando_inicio": [],
        "comando_detener": [],
        "comando_reinicio": [],
        "preparar_automaticamente": False,
        "comandos_preparacion": [],
        "directorio_trabajo": ".",
        "espera_inicio": 2.0,
        "variables": {},
    }

    compose = next(
        (
            name
            for name in (
                "compose.yml", "compose.yaml",
                "docker-compose.yml", "docker-compose.yaml",
            )
            if (root / name).exists()
        ),
        None,
    )
    if compose:
        base["modo"] = "service"
        base["comando_inicio"] = ["docker", "compose", "-f", compose, "up", "-d"]
        base["comando_detener"] = ["docker", "compose", "-f", compose, "down"]
        base["comando_reinicio"] = ["docker", "compose", "-f", compose, "restart"]
        base["espera_inicio"] = 8.0
        return base, "http://127.0.0.1:8080"

    if "moodle" in frameworks:
        base["modo"] = "external"
        return base, "http://127.0.0.1/moodle"

    if "javascript" in languages or "typescript" in languages:
        package_manager = "npm"
        if (root / "pnpm-lock.yaml").exists():
            package_manager = "pnpm"
        elif (root / "yarn.lock").exists():
            package_manager = "yarn"

        start_command = [package_manager, "start"]
        try:
            package_data = json.loads(_read_text(root / "package.json"))
        except (json.JSONDecodeError, TypeError):
            package_data = {}
        scripts = package_data.get("scripts") or {}
        if "start" not in scripts and "dev" in scripts:
            start_command = [package_manager, "run", "dev"]

        base["comando_inicio"] = start_command
        base["preparar_automaticamente"] = True
        if package_manager == "npm":
            base["comandos_preparacion"] = [
                ["npm", "install", "--no-audit", "--no-fund"]
            ]
        else:
            base["comandos_preparacion"] = [[package_manager, "install"]]
        return base, "http://127.0.0.1:3000"

    if "python" in languages:
        base["preparar_automaticamente"] = True
        if (root / "requirements.txt").exists():
            base["comandos_preparacion"] = [
                ["python", "-m", "pip", "install", "-r", "requirements.txt"]
            ]
        if (root / "run.py").exists():
            base["comando_inicio"] = ["python", "run.py"]
        elif (root / "manage.py").exists():
            base["comando_inicio"] = ["python", "manage.py", "runserver", "127.0.0.1:8000"]
        elif "fastapi" in frameworks:
            base["comando_inicio"] = ["python", "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"]
        return base, "http://127.0.0.1:5000" if "flask" in frameworks else "http://127.0.0.1:8000"

    if "java" in languages:
        if (root / "mvnw.cmd").exists() or (root / "mvnw").exists():
            base["comando_inicio_por_so"] = {
                "windows": ["mvnw.cmd", "spring-boot:run"],
                "linux": ["mvnw", "spring-boot:run"],
                "macos": ["mvnw", "spring-boot:run"],
            }
        elif "spring-boot" in frameworks:
            base["comando_inicio"] = ["mvn", "spring-boot:run"]
        else:
            base["modo"] = "external"
        return base, "http://127.0.0.1:8080"

    if "dotnet" in frameworks or "csharp" in languages:
        base["comando_inicio"] = ["dotnet", "run"]
        base["preparar_automaticamente"] = True
        base["comandos_preparacion"] = [["dotnet", "restore"]]
        return base, "http://127.0.0.1:5000"

    if "php" in languages:
        if "laravel" in frameworks and (root / "artisan").exists():
            base["comando_inicio"] = [
                "php", "artisan", "serve",
                "--host=127.0.0.1", "--port=8000",
            ]
            if (root / "composer.json").exists():
                base["preparar_automaticamente"] = True
                base["comandos_preparacion"] = [["composer", "install"]]
            return base, "http://127.0.0.1:8000"
        # Moodle, WordPress, Symfony y PHP servidos por Apache/Nginx suelen
        # depender del entorno; evitar inventar un launcher.
        base["modo"] = "external"
        return base, "http://127.0.0.1:8000"

    if "ruby" in languages:
        if "rails" in frameworks:
            base["comando_inicio"] = ["bundle", "exec", "rails", "server"]
            base["preparar_automaticamente"] = True
            base["comandos_preparacion"] = [["bundle", "install"]]
            return base, "http://127.0.0.1:3000"
        base["modo"] = "external"
        return base, "http://127.0.0.1:4567"

    if "go" in languages:
        base["comando_inicio"] = ["go", "run", "."]
        return base, "http://127.0.0.1:8080"

    if "rust" in languages:
        base["comando_inicio"] = ["cargo", "run"]
        base["preparar_automaticamente"] = True
        base["comandos_preparacion"] = [["cargo", "build"]]
        return base, "http://127.0.0.1:8000"

    # Para stacks donde el launcher web no puede inferirse de forma fiable
    # (Flutter, Swift, Elixir, Scala, C/C++ u otros), conservar el proyecto y
    # generar el perfil, pero requerir confirmación humana del runtime.
    base["modo"] = "external"
    return base, "http://127.0.0.1:8000"


_USERNAME_KEYS = {
    "username", "user", "usuario", "login", "email", "correo",
    "nombre_usuario", "user_name",
}
_PASSWORD_KEYS = {
    "password", "pass", "passwd", "clave", "contrasena",
    "contraseña", "pwd",
}
_ROLE_KEYS = {
    "role", "rol", "perfil", "authority", "authorities",
    "tipo_usuario", "user_role",
}
_PRIVILEGED_ROLES = {
    "admin", "administrator", "administrador", "root",
    "superadmin", "super_admin", "manager", "gerente",
}


def _clean_literal(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("'").strip('"')
    text = text.strip(chr(96)).strip()
    text = re.sub(r"\s*\|\s*$", "", text).strip()
    if not text:
        return None
    lower = text.lower()
    if (
        lower in {"none", "null", "undefined", "username", "password"}
        or "$" "{" in text
        or "{{" in text
        or "process.env" in lower
        or "os.getenv" in lower
    ):
        return None
    return text


def _account_from_mapping(
    item: dict[str, Any],
    *,
    source: str,
    confidence: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    lowered = {str(key).lower(): value for key, value in item.items()}

    username = next(
        (
            _clean_literal(lowered[key])
            for key in _USERNAME_KEYS
            if key in lowered and _clean_literal(lowered[key])
        ),
        None,
    )
    if not username:
        return None

    password = next(
        (
            _clean_literal(lowered[key])
            for key in _PASSWORD_KEYS
            if key in lowered and _clean_literal(lowered[key])
        ),
        None,
    )
    role = next(
        (
            _clean_literal(lowered[key])
            for key in _ROLE_KEYS
            if key in lowered and _clean_literal(lowered[key])
        ),
        None,
    ) or "USER"

    account = {
        "username": username,
        "password": password,
        "role": role,
        "auth_type": "basic" if password else "none",
        "token": None,
        "headers": {},
    }
    evidence = {
        "username": username,
        "role": role,
        "archivo": source,
        "tipo_fuente": _source_kind(source),
        "confianza": confidence,
        "password_literal": bool(password),
    }
    return account, evidence


def _walk_json_accounts(
    value: Any,
    *,
    source: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if isinstance(value, dict):
        candidate = _account_from_mapping(
            value,
            source=source,
            confidence="alta",
        )
        if candidate:
            found.append(candidate)
        for nested in value.values():
            found.extend(_walk_json_accounts(nested, source=source))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_walk_json_accounts(nested, source=source))
    return found


def _split_sql_values(text: str) -> list[str]:
    return [
        part.strip().strip("'").strip('"')
        for part in re.split(
            r",(?=(?:[^']*'[^']*')*[^']*$)",
            text,
        )
    ]


def _extract_table_accounts(
    text: str,
    *,
    source: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    lines = text.splitlines()

    for index, line in enumerate(lines):
        if "|" not in line:
            continue

        headers = [
            cell.strip().strip(chr(96)).strip("*").lower()
            for cell in line.strip().strip("|").split("|")
        ]
        username_index = next(
            (
                idx
                for idx, header in enumerate(headers)
                if header in _USERNAME_KEYS
            ),
            None,
        )
        if username_index is None:
            continue

        password_index = next(
            (
                idx
                for idx, header in enumerate(headers)
                if header in _PASSWORD_KEYS
            ),
            None,
        )
        role_index = next(
            (
                idx
                for idx, header in enumerate(headers)
                if header in _ROLE_KEYS
            ),
            None,
        )

        row_index = index + 1
        if row_index < len(lines) and re.match(
            r"^\s*\|?\s*:?-{2,}",
            lines[row_index],
        ):
            row_index += 1

        while row_index < len(lines):
            row_line = lines[row_index]
            if "|" not in row_line or not row_line.strip():
                break

            cells = [
                _clean_literal(cell)
                for cell in row_line.strip().strip("|").split("|")
            ]
            if username_index >= len(cells):
                break

            username = cells[username_index]
            if not username:
                row_index += 1
                continue

            password = (
                cells[password_index]
                if password_index is not None
                and password_index < len(cells)
                else None
            )
            role = (
                cells[role_index]
                if role_index is not None
                and role_index < len(cells)
                else "USER"
            )

            candidate = _account_from_mapping(
                {
                    "username": username,
                    "password": password,
                    "role": role or "USER",
                },
                source=source,
                confidence="media",
            )
            if candidate:
                found.append(candidate)

            row_index += 1

    return found

def _extract_accounts_from_text(
    text: str,
    *,
    source: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    found: list[tuple[dict[str, Any], dict[str, Any]]] = []

    found.extend(
        _extract_table_accounts(
            text,
            source=source,
        )
    )

    insert_pattern = re.compile(
        r"INSERT\s+INTO\s+[\w.\"\-]+\s*"
        r"\(([^)]+)\)\s*VALUES\s*\(([^;]+?)\)",
        re.I | re.S,
    )
    for match in insert_pattern.finditer(text):
        columns = [
            column.strip().strip('"').lower()
            for column in match.group(1).split(",")
        ]
        values = _split_sql_values(match.group(2))
        if len(columns) != len(values):
            continue
        candidate = _account_from_mapping(
            dict(zip(columns, values)),
            source=source,
            confidence="alta",
        )
        if candidate:
            found.append(candidate)

    username_pattern = re.compile(
        r"(?i)\b("
        + "|".join(re.escape(key) for key in sorted(_USERNAME_KEYS))
        + r")\b\s*[=:]\s*['\"]([^'\"\r\n]{1,160})['\"]"
    )
    password_pattern = re.compile(
        r"(?i)\b("
        + "|".join(re.escape(key) for key in sorted(_PASSWORD_KEYS))
        + r")\b\s*[=:]\s*['\"]([^'\"\r\n]{1,220})['\"]"
    )
    role_pattern = re.compile(
        r"(?i)\b("
        + "|".join(re.escape(key) for key in sorted(_ROLE_KEYS))
        + r")\b\s*[=:]\s*['\"]([^'\"\r\n]{1,120})['\"]"
    )

    for user_match in username_pattern.finditer(text):
        start = max(0, user_match.start() - 500)
        end = min(len(text), user_match.end() + 900)
        window = text[start:end]
        pass_match = password_pattern.search(window)
        role_match = role_pattern.search(window)
        candidate = _account_from_mapping(
            {
                "username": user_match.group(2),
                "password": pass_match.group(2) if pass_match else None,
                "role": role_match.group(2) if role_match else "USER",
            },
            source=source,
            confidence="alta" if pass_match else "media",
        )
        if candidate:
            found.append(candidate)

    # Pares sin comillas, comunes en README, manuales, .env y YAML.
    loose_user_pattern = re.compile(
        r"(?im)^\s*(?:[-*+]\s*)?(?:\*\*)?"
        r"(?:username|user|usuario|login|email|correo|nombre_usuario|user_name)"
        r"(?:\s*[:=]\s*\*\*|\*\*\s*[:=]\s*|[:=]\s*)"
        r"(.+?)\s*$"
    )
    loose_password_pattern = re.compile(
        r"(?im)^\s*(?:[-*+]\s*)?(?:\*\*)?"
        r"(?:password|pass|passwd|clave|contrasena|contraseña|pwd)"
        r"(?:\s*[:=]\s*\*\*|\*\*\s*[:=]\s*|[:=]\s*)"
        r"(.+?)\s*$"
    )
    loose_role_pattern = re.compile(
        r"(?im)^\s*(?:[-*+]\s*)?(?:\*\*)?"
        r"(?:role|rol|perfil|authority|authorities|tipo_usuario|user_role)"
        r"(?:\s*[:=]\s*\*\*|\*\*\s*[:=]\s*|[:=]\s*)"
        r"(.+?)\s*$"
    )

    for user_match in loose_user_pattern.finditer(text):
        start = max(0, user_match.start() - 800)
        end = min(len(text), user_match.end() + 1400)
        window = text[start:end]
        pass_match = loose_password_pattern.search(window)
        role_match = loose_role_pattern.search(window)
        candidate = _account_from_mapping(
            {
                "username": _clean_literal(user_match.group(1)),
                "password": (
                    _clean_literal(pass_match.group(1))
                    if pass_match
                    else None
                ),
                "role": (
                    _clean_literal(role_match.group(1))
                    if role_match
                    else "USER"
                ),
            },
            source=source,
            confidence=(
                "alta"
                if _source_kind(source) == "configuracion"
                and pass_match
                else "media"
            ),
        )
        if candidate:
            found.append(candidate)

    # Credenciales Basic embebidas en URLs de manuales/configuración.
    for match in re.finditer(
        r"https?://([^/\s:@]+):([^@\s/]+)@[^/\s]+",
        text,
        re.I,
    ):
        candidate = _account_from_mapping(
            {
                "username": match.group(1),
                "password": match.group(2),
                "role": "USER",
            },
            source=source,
            confidence="media",
        )
        if candidate:
            found.append(candidate)

    spring_pattern = re.compile(
        r"withUser\(\s*['\"]([^'\"]+)['\"]\s*\)"
        r".{0,500}?password\(\s*['\"]([^'\"]+)['\"]\s*\)"
        r".{0,500}?(?:roles?|authorities)\(\s*['\"]([^'\"]+)['\"]",
        re.I | re.S,
    )
    for match in spring_pattern.finditer(text):
        candidate = _account_from_mapping(
            {
                "username": match.group(1),
                "password": match.group(2),
                "role": match.group(3),
            },
            source=source,
            confidence="alta",
        )
        if candidate:
            found.append(candidate)

    return found


def _extract_accounts(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accounts: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}

    for path, relative in _iter_source_files(root, max_files=None):
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue

        candidates: list[
            tuple[dict[str, Any], dict[str, Any]]
        ] = []

        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if payload is not None:
                candidates.extend(
                    _walk_json_accounts(
                        payload,
                        source=relative.as_posix(),
                    )
                )

        if path.suffix.lower() == ".csv":
            try:
                rows = list(csv.DictReader(text.splitlines()))
            except Exception:
                rows = []
            for row in rows:
                candidate = _account_from_mapping(
                    row,
                    source=relative.as_posix(),
                    confidence="alta",
                )
                if candidate:
                    candidates.append(candidate)

        candidates.extend(
            _extract_accounts_from_text(
                text,
                source=relative.as_posix(),
            )
        )

        for account, evidence in candidates:
            username = account["username"]
            current = accounts.get(username)
            if current is None or (
                not current.get("password")
                and account.get("password")
            ):
                accounts[username] = account
                sources[username] = evidence

    ordered = sorted(
        accounts.values(),
        key=lambda item: item["username"].lower(),
    )
    evidence = [
        sources[item["username"]]
        for item in ordered
        if item["username"] in sources
    ]
    return ordered, evidence


def _normalize_version_candidate(value: Any) -> str | None:
    if value is None:
        return None
    version = str(value).strip().strip("'").strip('"').strip()
    version = version.strip(chr(96)).strip()
    if not version or len(version) > 96:
        return None
    if version.lower() in {
        "unknown", "desconocida", "desconocido", "none",
        "null", "undefined", "snapshot", "latest",
    }:
        return None
    if "$" "{" in version or "#{" in version or "{{" in version:
        return None
    if version.startswith("$") or not re.search(r"\d", version):
        return None
    if len(version.split()) > 3:
        return None
    if re.match(r"^[vV]\d", version):
        version = version[1:]
    return version


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_xml_child(
    root: ET.Element,
    name: str,
) -> ET.Element | None:
    for child in list(root):
        if _xml_local_name(child.tag).lower() == name.lower():
            return child
    return None


def _xml_child_text(
    root: ET.Element,
    name: str,
) -> str | None:
    child = _direct_xml_child(root, name)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _resolve_maven_property(
    pom_root: ET.Element,
    value: str | None,
) -> str | None:
    if not value:
        return value
    match = re.fullmatch(
        r"\$" + r"\{([^}]+)\}",
        value.strip(),
    )
    if not match:
        return value
    key = match.group(1)
    properties = _direct_xml_child(pom_root, "properties")
    if properties is None:
        return None
    for child in list(properties):
        if _xml_local_name(child.tag) == key and child.text:
            return child.text.strip()
    return None


def _section_version(
    text: str,
    sections: set[str],
) -> str | None:
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        section_match = re.match(r"^\[([^\]]+)\]\s*$", line)
        if section_match:
            current = section_match.group(1).strip().lower()
            continue
        if current not in sections:
            continue
        match = re.match(
            r"^version\s*[=:]\s*['\"]?([^'\"#;]+)",
            line,
            re.I,
        )
        if match:
            return match.group(1).strip()
    return None


def _detect_project_version(
    root: Path,
    descriptor: dict[str, Any] | None,
) -> tuple[
    str | None,
    str | None,
    str | None,
    list[dict[str, Any]],
]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        value: Any,
        source: str,
        detector: str,
        score: int,
        confidence: str,
    ) -> None:
        version = _normalize_version_candidate(value)
        if not version:
            return
        key = (version, source)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "version": version,
                "archivo": source,
                "tipo_fuente": _source_kind(source),
                "detector": detector,
                "confianza": confidence,
                "prioridad": score,
            }
        )

    if descriptor:
        for key in (
            "version",
            "app_version",
            "application_version",
            "version_objetivo",
        ):
            if descriptor.get(key):
                add(
                    descriptor.get(key),
                    "auditor-package.json",
                    "descriptor:" + key,
                    120,
                    "alta",
                )
                break

    for name in ("VERSION", "VERSION.txt", "version.txt", ".version"):
        path = root / name
        if path.is_file():
            text = _read_text(path, limit=20_000)
            first_line = next(
                (line.strip() for line in text.splitlines() if line.strip()),
                "",
            )
            add(first_line, name, "version-file", 115, "alta")

    for name, detector_name in (
        ("package.json", "npm"),
        ("composer.json", "composer"),
    ):
        path = root / name
        if path.is_file():
            try:
                payload = json.loads(_read_text(path))
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                add(
                    payload.get("version"),
                    name,
                    detector_name,
                    110,
                    "alta",
                )

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        add(
            _section_version(
                _read_text(pyproject),
                {"project", "tool.poetry"},
            ),
            "pyproject.toml",
            "python-project",
            110,
            "alta",
        )

    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        add(
            _section_version(_read_text(setup_cfg), {"metadata"}),
            "setup.cfg",
            "python-setup-cfg",
            105,
            "alta",
        )

    cargo = root / "Cargo.toml"
    if cargo.is_file():
        add(
            _section_version(_read_text(cargo), {"package"}),
            "Cargo.toml",
            "cargo",
            110,
            "alta",
        )

    pubspec = root / "pubspec.yaml"
    if pubspec.is_file():
        match = re.search(
            r"(?m)^\s*version\s*:\s*['\"]?([^#'\"]+)",
            _read_text(pubspec),
        )
        add(
            match.group(1).strip() if match else None,
            "pubspec.yaml",
            "pubspec",
            110,
            "alta",
        )

    pom = root / "pom.xml"
    if pom.is_file():
        try:
            pom_root = ET.fromstring(_read_text(pom))
        except ET.ParseError:
            pom_root = None
        if pom_root is not None:
            project_version = _resolve_maven_property(
                pom_root,
                _xml_child_text(pom_root, "version"),
            )
            add(
                project_version,
                "pom.xml",
                "maven-project-version",
                112,
                "alta",
            )
            if not project_version:
                parent = _direct_xml_child(pom_root, "parent")
                if parent is not None:
                    add(
                        _xml_child_text(parent, "version"),
                        "pom.xml",
                        "maven-parent-version",
                        82,
                        "media",
                    )

    for gradle_name in ("build.gradle", "build.gradle.kts"):
        path = root / gradle_name
        if path.is_file():
            match = re.search(
                r"(?m)^\s*version\s*(?:=|\s)\s*['\"]([^'\"]+)['\"]",
                _read_text(path),
            )
            add(
                match.group(1) if match else None,
                gradle_name,
                "gradle",
                108,
                "alta",
            )

    gradle_props = root / "gradle.properties"
    if gradle_props.is_file():
        match = re.search(
            r"(?im)^\s*(?:version|appVersion|applicationVersion)"
            r"\s*=\s*(.+?)\s*$",
            _read_text(gradle_props),
        )
        add(
            match.group(1) if match else None,
            "gradle.properties",
            "gradle-properties",
            106,
            "alta",
        )

    setup_py = root / "setup.py"
    if setup_py.is_file():
        match = re.search(
            r"\bversion\s*=\s*['\"]([^'\"]+)['\"]",
            _read_text(setup_py),
            re.I,
        )
        add(
            match.group(1) if match else None,
            "setup.py",
            "python-setup",
            100,
            "media",
        )

    csproj_paths = sorted(root.glob("*.csproj"))
    if not csproj_paths:
        csproj_paths = sorted(root.glob("*/*.csproj"))[:10]
    for csproj in csproj_paths:
        try:
            xml_root = ET.fromstring(_read_text(csproj))
        except ET.ParseError:
            continue
        value = None
        detector = "dotnet"
        for tag_name in (
            "Version",
            "VersionPrefix",
            "AssemblyVersion",
            "FileVersion",
        ):
            for element in xml_root.iter():
                if (
                    _xml_local_name(element.tag) == tag_name
                    and element.text
                ):
                    value = element.text.strip()
                    detector = "dotnet:" + tag_name
                    break
            if value:
                break
        add(
            value,
            csproj.relative_to(root).as_posix(),
            detector,
            108,
            "alta",
        )

    mix = root / "mix.exs"
    if mix.is_file():
        match = re.search(
            r"\bversion\s*:\s*['\"]([^'\"]+)['\"]",
            _read_text(mix),
        )
        add(
            match.group(1) if match else None,
            "mix.exs",
            "mix",
            105,
            "alta",
        )

    version_php = root / "version.php"
    if version_php.is_file():
        text = _read_text(version_php)
        release_match = re.search(
            r"\$(?:release|plugin->release)\s*=\s*['\"]([^'\"]+)['\"]",
            text,
            re.I,
        )
        add(
            release_match.group(1) if release_match else None,
            "version.php",
            "php-release",
            108,
            "alta",
        )
        if not release_match:
            numeric_match = re.search(
                r"\$(?:version|plugin->version)\s*=\s*"
                r"['\"]?([0-9][0-9A-Za-z.+_-]*)",
                text,
                re.I,
            )
            add(
                numeric_match.group(1) if numeric_match else None,
                "version.php",
                "php-version",
                88,
                "media",
            )

    manifest_candidates = (
        root / "META-INF" / "MANIFEST.MF",
        root / "src" / "main" / "resources" / "META-INF" / "MANIFEST.MF",
    )
    for manifest in manifest_candidates:
        if not manifest.is_file():
            continue
        match = re.search(
            r"(?im)^(?:Implementation-Version|Bundle-Version|Specification-Version)"
            r"\s*:\s*(.+?)\s*$",
            _read_text(manifest),
        )
        add(
            match.group(1) if match else None,
            manifest.relative_to(root).as_posix(),
            "java-manifest",
            100,
            "alta",
        )

    for path, relative in _iter_source_files(root, max_files=None):
        name = path.name.lower()
        if not (
            path.suffix.lower() in DOCUMENT_EXTENSIONS
            or name.startswith(("readme", "manual", "guide", "guia"))
            or "changelog" in name
            or "release" in name
        ):
            continue
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue
        patterns = (
            (
                r"(?im)^\s*(?:[-*#>]\s*)?"
                r"(?:versi[oó]n\s+(?:actual|de\s+la\s+aplicaci[oó]n|del\s+sistema)"
                r"|current\s+version|application\s+version|app\s+version)"
                r"\s*[:= -]\s*([vV]?\d[0-9A-Za-z.+_-]*)",
                78,
                "media",
                "documentation-explicit-version",
            ),
            (
                r"(?im)^\s*(?:[-*#>]\s*)?"
                r"(?:versi[oó]n|version)"
                r"\s*[:= -]\s*([vV]?\d[0-9A-Za-z.+_-]*)",
                58,
                "baja",
                "documentation-version",
            ),
        )
        for pattern, score, confidence, detector in patterns:
            match = re.search(pattern, text)
            if match:
                add(
                    match.group(1),
                    relative.as_posix(),
                    detector,
                    score,
                    confidence,
                )
                break

    candidates.sort(
        key=lambda item: (
            -int(item["prioridad"]),
            len(Path(item["archivo"]).parts),
            item["archivo"].lower(),
        )
    )
    if not candidates:
        return None, None, None, []

    best = candidates[0]
    return (
        best["version"],
        best["archivo"],
        best["confianza"],
        candidates,
    )


def detect_project(root: str | Path) -> ProjectDetection:
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(root_path)

    descriptor = _load_package_descriptor(root_path)
    languages, frameworks, manifests = _detect_stack(root_path)

    if descriptor:
        language = descriptor.get("language")
        if language and language not in languages:
            languages.append(str(language))
        for framework in descriptor.get("framework") or []:
            if str(framework) not in frameworks:
                frameworks.append(str(framework))

    runtime, base_url = _detect_runtime(
        root_path,
        sorted(set(languages)),
        sorted(set(frameworks)),
        descriptor,
    )
    accounts, account_sources = _extract_accounts(root_path)

    detection = ProjectDetection(
        root=root_path,
        name=(
            str(descriptor.get("name"))
            if descriptor and descriptor.get("name")
            else root_path.name
        ),
        languages=sorted(set(languages)),
        frameworks=sorted(set(frameworks)),
        manifests=manifests,
        source_roots=_detect_source_roots(root_path),
        routes=_extract_routes(root_path),
        runtime=runtime,
        package_descriptor=descriptor,
        accounts=accounts,
        account_sources=account_sources,
    )
    detection.notes.append(f"Base URL sugerida: {base_url}")
    detection.notes.append(
        f"Cuentas candidatas detectadas: {len(accounts)}"
    )
    return detection


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "-",
        ascii_value.lower(),
    )
    return ascii_value.strip("-._") or "aplicacion"


def build_profile_draft(
    detection: ProjectDetection,
    *,
    system_name: str | None = None,
    version: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    name = (system_name or detection.name).strip() or detection.name
    suggested_url = next(
        (
            note.split(":", 1)[1].strip()
            for note in detection.notes
            if note.startswith("Base URL sugerida:")
        ),
        "http://127.0.0.1:8000",
    )

    endpoint_inventory = _build_endpoint_inventory(
        detection.routes
    )

    profile = {
        "sistema": _slug(name),
        "version_objetivo": version or "1.0.0",
        "base_url": (base_url or suggested_url).rstrip("/"),
        "cuentas": list(detection.accounts),
        "roles_privilegiados": sorted(
            {
                str(account.get("role") or "")
                for account in detection.accounts
                if str(account.get("role") or "").lower()
                in _PRIVILEGED_ROLES
            }
        ),
        "runtime": detection.runtime,
        "endpoints": [],
        "endpoints_detectados": endpoint_inventory,
        "chequeos_agente": [],
        "chequeos_acceso": [],
        "chequeos_pilar2": [],
        "correcciones": [],
        "metadata_detectada": {
            "nombre_proyecto": detection.name,
            "lenguajes": detection.languages,
            "frameworks": detection.frameworks,
            "manifiestos": detection.manifests,
            "raices_codigo": detection.source_roots,
            "endpoints_candidatos": [
                route.as_dict() for route in detection.routes
            ],
            "total_endpoints_detectados": len(endpoint_inventory),
            "total_coincidencias_endpoint": len(detection.routes),
            "cuentas_candidatas": list(detection.account_sources),
            "archivos_cuentas_escaneados": True,
            "perfil_generado_automaticamente": True,
        },
    }

    return profile


def save_profile_draft(
    profile: dict[str, Any],
    destination: str | Path,
) -> Path:
    path = Path(destination).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
