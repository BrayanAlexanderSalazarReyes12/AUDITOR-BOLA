"""Detección genérica de proyectos y construcción de perfiles borrador."""

from __future__ import annotations

import ast
import csv
import json
import re
import shutil
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .security_semantics import (
    id_key_score,
    infer_object_identity,
    normalize_key,
    owner_key_score,
    route_parameter_name,
)


from .security_model import enrich_profile
from .pilar2_engine import discover_pilar2
from .seed_data import seed_records


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


def _route_mounts(root: Path) -> dict[tuple[str, str], str]:
    """Resuelve imports locales y prefijos de Blueprint/Express."""
    mounts = {}
    for path, relative in _iter_source_files(root):
        text = _read_text(path)
        if path.suffix == ".py":
            imports = {}
            for match in re.finditer(r"from\s+([\w.]+)\s+import\s+(\w+)(?:\s+as\s+(\w+))?", text):
                module, symbol, alias = match.groups()
                if module.startswith("."):
                    levels = len(module) - len(module.lstrip("."))
                    parent = path.parent
                    for _ in range(levels - 1):
                        parent = parent.parent
                    target = parent / module.lstrip(".").replace(".", "/")
                else:
                    target = root / module.replace(".", "/")
                target = target.with_suffix(".py")
                if target.is_file():
                    imports[alias or symbol] = (target.relative_to(root).as_posix(), symbol)
            for match in re.finditer(
                r"\.register_blueprint\(\s*(\w+)\s*,\s*url_prefix\s*=\s*['\"]([^'\"]*)['\"]", text
            ):
                if match[1] in imports:
                    mounts[imports[match[1]]] = match[2]
        elif path.suffix in {".js", ".ts", ".cjs", ".mjs"}:
            imports = {}
            for match in re.finditer(r"(?:const|let|var)\s+(\w+)\s*=\s*require\(['\"](\.[^'\"]+)['\"]\)", text):
                target = (path.parent / match[2]).resolve()
                if not target.suffix:
                    target = target.with_suffix(path.suffix)
                if target.is_file() and target.is_relative_to(root):
                    imports[match[1]] = target.relative_to(root).as_posix()
            for match in re.finditer(r"\.use\(\s*['\"]([^'\"]*)['\"]\s*,\s*(\w+)\s*\)", text):
                if match[2] in imports:
                    mounts[(imports[match[2]], "*")] = match[1]
    return mounts


def _extract_routes(root: Path) -> list[DetectedRoute]:
    """Inventaría rutas declaradas estáticamente en todo el proyecto.

    No impone un máximo de archivos ni de endpoints. Deduplica por método,
    ruta y archivo y conserva el framework/origen que permitió detectarlos.
    """

    found: dict[tuple[str, str, str], DetectedRoute] = {}
    mounts = _route_mounts(root)

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

        # Flask / FastAPI / Starlette. Para Blueprint conservamos
        # url_prefix, porque una ruta "/<id>" no es ejecutable sin su prefijo.
        blueprint_prefixes = {receiver: prefix for (file, receiver), prefix in mounts.items() if file == source}
        for bp_match in re.finditer(
            r"(?m)^\s*(\w+)\s*=\s*Blueprint\s*\("
            r".{0,800}?\burl_prefix\s*=\s*['\"]([^'\"]+)['\"]",
            text,
            re.I | re.S,
        ):
            blueprint_prefixes[bp_match.group(1)] = bp_match.group(2)

        for match in re.finditer(
            r"@(app|router|bp|blueprint|\w+)"
            r"\.(get|post|put|patch|delete|options|head)"
            r"\(\s*['\"]([^'\"]*)['\"]",
            text,
            re.I,
        ):
            receiver = match.group(1)
            route = match.group(3)
            if receiver in blueprint_prefixes:
                route = _join_route_paths(
                    blueprint_prefixes[receiver],
                    route,
                )
            add(
                match.group(2),
                route,
                source,
                "python-router",
            )

        for match in re.finditer(
            r"@(app|router|bp|blueprint|\w+)\.route"
            r"\(\s*['\"]([^'\"]*)['\"]([^)]*)\)",
            text,
            re.I | re.S,
        ):
            receiver = match.group(1)
            route = match.group(2)
            if receiver in blueprint_prefixes:
                route = _join_route_paths(
                    blueprint_prefixes[receiver],
                    route,
                )
            methods = _literal_methods(match.group(3)) or ["GET"]
            for method in methods:
                add(
                    method,
                    route,
                    source,
                    "python-route",
                )

        # Express / Fastify / generic JS routers. No ejecutar este
        # detector sobre Python: decoradores Flask como bp.get(...) tenían
        # la misma forma textual y generaban rutas duplicadas sin url_prefix.
        if suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
            for match in re.finditer(
                r"\b(?:app|router|server|fastify|\w+)"
                r"\.(get|post|put|patch|delete|options|head|all)"
                r"\(\s*['\"](/[^'\"]*)['\"]",
                text,
                re.I,
            ):
                method = match.group(1).upper()
                add(
                    "ANY" if method == "ALL" else method,
                    _join_route_paths(mounts.get((source, "*"), ""), match.group(2)),
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
            servlet_methods = [
                method.upper()
                for method in re.findall(
                    r"\bdo(Get|Post|Put|Patch|Delete|Options|Head)\s*\(",
                    text,
                    re.I,
                )
            ]
            for route in urls:
                for method in dict.fromkeys(servlet_methods or ["ANY"]):
                    add(method, route, source, "servlet")

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


def _detect_compose_published_port(path: Path) -> int | None:
    """Extrae el primer puerto TCP publicado en sintaxis Compose común."""
    text = _read_text(path)
    if not text:
        return None

    # Sintaxis corta: "8080:5000", "127.0.0.1:8080:5000", 8080:5000.
    short = re.compile(
        r"""(?mx)
        ^\s*-\s*["']?
        (?:(?:127\.0\.0\.1|0\.0\.0\.0|localhost):)?
        (?P<published>\d{2,5})
        :
        (?P<target>\d{2,5})
        (?:/tcp)?
        ["']?\s*(?:\#.*)?$
        """
    )
    for match in short.finditer(text):
        port = int(match.group("published"))
        if 1 <= port <= 65535:
            return port

    # Sintaxis larga:
    # - target: 5000
    #   published: 8080
    long_match = re.search(
        r"(?ms)^\s*-\s*target\s*:\s*\d+\s*$"
        r".{0,250}?"
        r"""^\s*published\s*:\s*["']?(\d{2,5})["']?\s*$""",
        text,
    )
    if long_match:
        port = int(long_match.group(1))
        if 1 <= port <= 65535:
            return port

    return None


def _detect_project_http_base_url(root: Path) -> str | None:
    """Busca una URL local explícita fuera de Docker.

    Se usa como evidencia para el runtime nativo cuando el launcher no tiene
    un port=N literal. Priorizamos launchers/configuración y luego
    documentación operativa. No se toma el mapeo de Docker como autoridad.
    """
    preferred_names = (
        "run.py",
        ".env",
        ".env.local",
        ".env.development",
        "config.py",
        "settings.py",
        "application.properties",
        "application.yml",
        "application.yaml",
        "README.md",
        "README.txt",
    )
    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()

    def scan(path: Path, score: int) -> None:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        if relative in seen:
            return
        seen.add(relative)
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            return

        for match in re.finditer(
            r"https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0)"
            r"(?::(\d{2,5}))?",
            text,
            re.I,
        ):
            port = match.group(1)
            url = (
                f"http://127.0.0.1:{port}"
                if port
                else "http://127.0.0.1"
            )
            candidates.append((score, url))

        for match in re.finditer(
            r"(?im)^\s*(?:PORT|APP_PORT|HTTP_PORT|SERVER_PORT)"
            r"""\s*[=:]\s*["']?(\d{2,5})["']?\s*$""",
            text,
        ):
            port = int(match.group(1))
            if 1 <= port <= 65535:
                candidates.append(
                    (score - 2, f"http://127.0.0.1:{port}")
                )

    for name in preferred_names:
        path = root / name
        if path.is_file():
            scan(path, 100 if name == "run.py" else 90)

    for path, relative in _iter_source_files(root, max_files=1500):
        if relative.as_posix() in seen:
            continue
        lower = relative.as_posix().lower()
        if (
            lower.startswith("docs/")
            or "operacion" in lower
            or "operation" in lower
            or path.suffix.lower() in {".env", ".ini", ".cfg", ".conf"}
        ):
            scan(path, 70)

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _detect_python_run_port(path: Path) -> int | None:
    """Detecta app.run(... port=N) en launchers Flask sencillos."""
    text = _read_text(path)
    match = re.search(
        r"\b(?:app\s*\.\s*)?run\s*\([^)]*?"
        r"\bport\s*=\s*(\d{2,5})",
        text,
        re.I | re.S,
    )
    if not match:
        return None
    port = int(match.group(1))
    return port if 1 <= port <= 65535 else None


def _runtime_template(
    *,
    name: str,
    origin: str,
    base_url: str,
) -> dict[str, Any]:
    return {
        "modo": "process",
        "nombre": name,
        "origen": origin,
        "preferencia_arranque": "auto",
        "permitir_fallback_local": True,
        "descripcion_ejecucion": "",
        "comando_inicio": [],
        "comando_detener": [],
        "comando_reinicio": [],
        "preparar_automaticamente": False,
        "comandos_preparacion": [],
        "directorio_trabajo": ".",
        "espera_inicio": 2.0,
        "variables": {},
        "base_url": base_url,
        "alternativas": [],
    }


def _detect_native_runtime(
    root: Path,
    languages: list[str],
    frameworks: list[str],
) -> tuple[dict[str, Any], str]:
    if "moodle" in frameworks:
        base = _runtime_template(
            name="Servidor externo PHP/Moodle",
            origin="framework:moodle",
            base_url="http://127.0.0.1/moodle",
        )
        base["modo"] = "external"
        return base, base["base_url"]

    if "javascript" in languages or "typescript" in languages:
        base = _runtime_template(
            name="Node.js",
            origin="package.json",
            base_url="http://127.0.0.1:3000",
        )

        package_manager = "npm"
        if (root / "pnpm-lock.yaml").exists():
            package_manager = "pnpm"
        elif (root / "yarn.lock").exists():
            package_manager = "yarn"

        try:
            package_data = json.loads(_read_text(root / "package.json"))
        except (json.JSONDecodeError, TypeError):
            package_data = {}

        scripts = (
            package_data.get("scripts")
            if isinstance(package_data, dict)
            else {}
        ) or {}

        if "start" in scripts:
            start_command = [package_manager, "start"]
        elif "dev" in scripts:
            start_command = [package_manager, "run", "dev"]
        elif "serve" in scripts:
            start_command = [package_manager, "run", "serve"]
        else:
            main_file = (
                package_data.get("main")
                if isinstance(package_data, dict)
                else None
            )
            if isinstance(main_file, str) and (root / main_file).is_file():
                start_command = ["node", main_file]
            else:
                base["modo"] = "external"
                return base, base["base_url"]

        base["nombre"] = f"Node.js ({package_manager})"
        base["descripcion_ejecucion"] = (
            "Ejecución local con Node.js usando el script del package.json."
        )
        base["comando_inicio"] = start_command
        base["preparar_automaticamente"] = True
        if package_manager == "npm":
            base["comandos_preparacion"] = [
                ["npm", "install", "--no-audit", "--no-fund"]
            ]
        else:
            base["comandos_preparacion"] = [[package_manager, "install"]]

        return base, base["base_url"]

    if "python" in languages:
        # No asumir 5000 para Flask. Muchos proyectos toman el puerto de
        # config/.env/variables o código indirecto. Si run.py no contiene un
        # literal verificable, Aegis descubrirá el listener real después de
        # lanzar Python.
        base = _runtime_template(
            name="Python",
            origin="python-project",
            base_url="",
        )
        base["preparar_automaticamente"] = True
        base["descripcion_ejecucion"] = (
            "Ejecución local con Python; Aegis prioriza .venv/venv/env "
            "del proyecto y luego Python del sistema."
        )

        if (root / "requirements.txt").exists():
            base["comandos_preparacion"] = [
                [
                    "python",
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    "requirements.txt",
                ]
            ]

        if (root / "run.py").exists():
            base["comando_inicio"] = ["python", "run.py"]
            explicit_port = _detect_python_run_port(root / "run.py")
            if explicit_port:
                base["base_url"] = (
                    f"http://127.0.0.1:{explicit_port}"
                )
            else:
                detected_url = _detect_project_http_base_url(root)
                if detected_url:
                    base["base_url"] = detected_url
        elif (root / "manage.py").exists():
            base["comando_inicio"] = [
                "python",
                "manage.py",
                "runserver",
                "127.0.0.1:8000",
            ]
            base["base_url"] = "http://127.0.0.1:8000"
        elif "fastapi" in frameworks:
            base["comando_inicio"] = [
                "python",
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ]
            base["base_url"] = "http://127.0.0.1:8000"
        else:
            base["modo"] = "external"

        return base, base["base_url"]

    if "java" in languages:
        base = _runtime_template(
            name="Java",
            origin="java-project",
            base_url="http://127.0.0.1:8080",
        )

        pom_text = _read_text(root / "pom.xml")
        if "spring-boot" not in frameworks and re.search(r"<packaging>\s*war\s*</packaging>", pom_text):
            final_name = re.search(r"<finalName>\s*([^<]+)\s*</finalName>", pom_text)
            context = final_name[1].strip() if final_name else root.name
            base.update({
                "modo": "external", "nombre": "Servlet WAR (Tomcat)",
                "base_url": "http://127.0.0.1:8080/" + context,
                "descripcion_ejecucion": "Compile con Maven y despliegue el WAR en un contenedor Servlet compatible; indique su URL con contexto.",
            })
            return base, base["base_url"]

        if (root / "mvnw.cmd").exists() or (root / "mvnw").exists():
            base["nombre"] = "Maven Wrapper"
            base["origen"] = "mvnw"
            base["comando_inicio_por_so"] = {
                "windows": ["mvnw.cmd", "spring-boot:run"],
                "linux": ["mvnw", "spring-boot:run"],
                "macos": ["mvnw", "spring-boot:run"],
            }
        elif (root / "gradlew.bat").exists() or (root / "gradlew").exists():
            base["nombre"] = "Gradle Wrapper"
            base["origen"] = "gradlew"
            base["comando_inicio_por_so"] = {
                "windows": ["gradlew.bat", "bootRun"],
                "linux": ["gradlew", "bootRun"],
                "macos": ["gradlew", "bootRun"],
            }
        elif "spring-boot" in frameworks and (root / "pom.xml").exists():
            base["nombre"] = "Maven"
            base["origen"] = "pom.xml"
            base["comando_inicio"] = ["mvn", "spring-boot:run"]
        elif (
            "spring-boot" in frameworks
            and (
                (root / "build.gradle").exists()
                or (root / "build.gradle.kts").exists()
            )
        ):
            base["nombre"] = "Gradle"
            base["origen"] = "build.gradle"
            base["comando_inicio"] = ["gradle", "bootRun"]
        else:
            base["modo"] = "external"

        return base, base["base_url"]

    if "dotnet" in frameworks or "csharp" in languages:
        base = _runtime_template(
            name=".NET",
            origin="csproj",
            base_url="http://127.0.0.1:5000",
        )
        base["comando_inicio"] = ["dotnet", "run"]
        base["preparar_automaticamente"] = True
        base["comandos_preparacion"] = [["dotnet", "restore"]]
        return base, base["base_url"]

    if "php" in languages:
        base = _runtime_template(
            name="PHP",
            origin="php-project",
            base_url="http://127.0.0.1:8000",
        )
        if "laravel" in frameworks and (root / "artisan").exists():
            base["nombre"] = "Laravel"
            base["origen"] = "artisan"
            base["comando_inicio"] = [
                "php",
                "artisan",
                "serve",
                "--host=127.0.0.1",
                "--port=8000",
            ]
            if (root / "composer.json").exists():
                base["preparar_automaticamente"] = True
                base["comandos_preparacion"] = [["composer", "install"]]
            return base, base["base_url"]

        base["modo"] = "external"
        return base, base["base_url"]

    if "ruby" in languages:
        base = _runtime_template(
            name="Ruby",
            origin="Gemfile",
            base_url="http://127.0.0.1:4567",
        )
        if "rails" in frameworks:
            base["nombre"] = "Ruby on Rails"
            base["comando_inicio"] = [
                "bundle",
                "exec",
                "rails",
                "server",
            ]
            base["preparar_automaticamente"] = True
            base["comandos_preparacion"] = [["bundle", "install"]]
            base["base_url"] = "http://127.0.0.1:3000"
            return base, base["base_url"]

        base["modo"] = "external"
        return base, base["base_url"]

    if "go" in languages:
        base = _runtime_template(
            name="Go",
            origin="go.mod",
            base_url="http://127.0.0.1:8080",
        )
        base["comando_inicio"] = ["go", "run", "."]
        return base, base["base_url"]

    if "rust" in languages:
        base = _runtime_template(
            name="Rust/Cargo",
            origin="Cargo.toml",
            base_url="http://127.0.0.1:8000",
        )
        base["comando_inicio"] = ["cargo", "run"]
        base["preparar_automaticamente"] = True
        base["comandos_preparacion"] = [["cargo", "build"]]
        return base, base["base_url"]

    base = _runtime_template(
        name="Runtime externo",
        origin="sin-launcher-inferible",
        base_url="http://127.0.0.1:8000",
    )
    base["modo"] = "external"
    return base, base["base_url"]


def _docker_available_on_host() -> bool:
    """Indica si Docker CLI está instalado en el equipo que genera el perfil."""
    return shutil.which("docker") is not None


def _runtime_has_local_launcher(runtime: dict[str, Any]) -> bool:
    mode = str(runtime.get("modo") or "process").strip().lower()
    if mode == "external":
        return False
    return bool(
        runtime.get("comando_inicio")
        or runtime.get("comando_inicio_por_so")
    )


def _detect_runtime(
    root: Path,
    languages: list[str],
    frameworks: list[str],
    descriptor: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    from_descriptor = _runtime_from_descriptor(descriptor)
    if from_descriptor:
        from_descriptor.setdefault("nombre", "Runtime declarado")
        from_descriptor.setdefault("origen", "auditor-package.json")
        from_descriptor.setdefault(
            "base_url",
            _detect_native_runtime(root, languages, frameworks)[1] or "http://127.0.0.1:8000",
        )
        from_descriptor.setdefault("alternativas", [])
        return from_descriptor, from_descriptor["base_url"]

    native_runtime, native_url = _detect_native_runtime(
        root,
        languages,
        frameworks,
    )

    compose = next(
        (
            name
            for name in (
                "compose.yml",
                "compose.yaml",
                "docker-compose.yml",
                "docker-compose.yaml",
            )
            if (root / name).exists()
        ),
        None,
    )

    if not compose:
        return native_runtime, native_url

    published_port = _detect_compose_published_port(root / compose)
    docker_base_url = (
        f"http://127.0.0.1:{published_port}"
        if published_port
        else native_url
    )
    docker_runtime = _runtime_template(
        name="Docker Compose",
        origin=compose,
        base_url=docker_base_url,
    )
    docker_runtime["modo"] = "service"
    docker_runtime["descripcion_ejecucion"] = (
        "Docker Compose si está disponible; si Docker falta o el servicio "
        "no abre el puerto esperado, Aegis intenta la alternativa local."
    )
    docker_runtime["comando_inicio"] = [
        "docker",
        "compose",
        "-f",
        compose,
        "up",
        "-d",
    ]
    docker_runtime["comando_detener"] = [
        "docker",
        "compose",
        "-f",
        compose,
        "down",
    ]
    docker_runtime["comando_reinicio"] = [
        "docker",
        "compose",
        "-f",
        compose,
        "restart",
    ]
    docker_runtime["espera_inicio"] = 2.0
    docker_runtime["timeout_inicio"] = 45.0

    native_launchable = _runtime_has_local_launcher(
        native_runtime
    )
    docker_available = _docker_available_on_host()

    # El JSON se arma para el equipo donde se está ejecutando Aegis.
    # Si Docker no existe en ese PC, no tiene sentido dejar Docker como
    # runtime principal solamente porque el repositorio contenga compose.yml.
    if not docker_available and native_launchable:
        native_runtime["preferencia_arranque"] = "local"
        native_runtime["descripcion_ejecucion"] = (
            str(native_runtime.get("descripcion_ejecucion") or "").strip()
            + (
                " Docker Compose existe en el proyecto, pero Docker no fue "
                "detectado en este equipo al generar el perfil; por eso Aegis "
                "seleccionó el runtime local como estrategia principal."
            )
        ).strip()
        # Docker queda como alternativa para que el mismo JSON siga siendo
        # útil si el equipo instala Docker más adelante.
        native_runtime["alternativas"] = [docker_runtime]
        return native_runtime, str(
            native_runtime.get("base_url") or native_url or ""
        )

    # Con Docker disponible se conserva como estrategia principal y el
    # runtime local queda como fallback.
    docker_runtime["preferencia_arranque"] = "contenedor"
    if native_launchable:
        docker_runtime["alternativas"] = [native_runtime]

    return docker_runtime, docker_runtime["base_url"]


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
    "coordinator", "coordinador", "supervisor",
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
            for key in sorted(_USERNAME_KEYS, key=lambda key: (key != "username", key in {"email", "correo"}, key))
            if key in lowered and _clean_literal(lowered[key])
        ),
        None,
    )
    if not username:
        return None

    # Evita falsos positivos extraídos de prosa/código como "usuario,".
    # Los usernames reales pueden incluir letras, números, punto, guion,
    # guion bajo, @ y +, pero no deben terminar en puntuación de frase.
    if (
        len(username) > 160
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._@+\-]{0,159}",
            username,
        )
    ):
        return None

    password = next(
        (
            _clean_literal(lowered[key])
            for key in sorted(_PASSWORD_KEYS, key=lambda key: (key != "password", key))
            if key in lowered and _clean_literal(lowered[key])
        ),
        None,
    )
    role = next(
        (
            _clean_literal(lowered[key])
            for key in sorted(_ROLE_KEYS, key=lambda key: (key != "role", key))
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
    identity_aliases: list[str] = []
    for key, raw_value in lowered.items():
        if key in _PASSWORD_KEYS or key in _ROLE_KEYS:
            continue
        value = _clean_literal(raw_value)
        if not value or value == username:
            continue
        if id_key_score(key) >= 70 and value not in identity_aliases:
            identity_aliases.append(value)

    evidence = {
        "username": username,
        "role": role,
        "archivo": source,
        "tipo_fuente": _source_kind(source),
        "confianza": confidence,
        "password_literal": bool(password),
        "identity_aliases": identity_aliases,
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

    for record in seed_records(text):
        candidate = _account_from_mapping(record, source=source, confidence="alta")
        if candidate:
            found.append(candidate)

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

    # Configuración/código con constantes explícitas de versión.
    for path, relative in _iter_source_files(root, max_files=None):
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue

        source = relative.as_posix()
        patterns = (
            (
                r"(?im)^\s*(?:__version__|APP_VERSION|APPLICATION_VERSION|"
                r"PROJECT_VERSION|VERSION_NAME|BUILD_VERSION)"
                r"\s*[:=]\s*['\"]?([vV]?\d[0-9A-Za-z.+_-]*)",
                "version-constant",
                76,
            ),
            (
                r"(?im)^\s*(?:app\.version|application\.version|"
                r"project\.version|build\.version|info\.app\.version)"
                r"\s*[:=]\s*['\"]?([vV]?\d[0-9A-Za-z.+_-]*)",
                "version-config-key",
                76,
            ),
            (
                r"(?i)<meta\s+[^>]*name\s*=\s*['\"]"
                r"(?:app-?version|application-?version|version)['\"]"
                r"[^>]*content\s*=\s*['\"]([^'\"]+)['\"]",
                "version-html-meta",
                72,
            ),
        )

        for pattern, detector, score in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            add(
                match.group(1),
                source,
                detector,
                score,
                "media",
            )
            break

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


def detect_runtime_profile(
    root: str | Path,
) -> tuple[dict[str, Any], str]:
    """Detecta únicamente estrategias de runtime para un proyecto.

    Se usa para complementar perfiles antiguos sin repetir el escaneo
    completo de cuentas y endpoints.
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise FileNotFoundError(root_path)

    descriptor = _load_package_descriptor(root_path)
    languages, frameworks, _manifests = _detect_stack(
        root_path
    )

    if descriptor:
        language = descriptor.get("language")
        if language and str(language) not in languages:
            languages.append(str(language))
        for framework in descriptor.get("framework") or []:
            if str(framework) not in frameworks:
                frameworks.append(str(framework))

    return _detect_runtime(
        root_path,
        sorted(set(languages)),
        sorted(set(frameworks)),
        descriptor,
    )


def _configure_detected_auth(detection: ProjectDetection) -> None:
    for route in detection.routes:
        if route.method != "POST":
            continue
        text = _read_text(detection.root / route.source)
        if not all(word in text for word in ("username", "password")):
            continue
        login = {"ruta": route.path, "campo_usuario": "username", "campo_password": "password"}
        if "request.form" in text and re.search(r"session\[", text):
            auth_type = "session"
            login.update(formato="form", codigos_exito=[200, 201, 204])
        elif "getSession(" in text and "getParameter(" in text:
            auth_type = "session"
            login.update(formato="form", codigos_exito=[302, 303])
        elif re.search(r"\btoken\s*:", text) and "req.body" in text:
            auth_type = "login_bearer"
            login.update(formato="json", token_json_path="token", codigos_exito=[200, 201])
        else:
            continue
        for account in detection.accounts:
            if account.get("password"):
                account.update(auth_type=auth_type, login=dict(login))
        return


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
    (
        detected_version,
        version_source,
        version_confidence,
        version_candidates,
    ) = _detect_project_version(
        root_path,
        descriptor,
    )

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
        version=detected_version,
        version_source=version_source,
        version_confidence=version_confidence,
        version_candidates=version_candidates,
        accounts=accounts,
        account_sources=account_sources,
    )
    detection.notes.append(f"Base URL sugerida: {base_url}")
    _configure_detected_auth(detection)
    detection.notes.append(
        f"Cuentas candidatas detectadas: {len(accounts)}"
    )
    detection.notes.append(
        "Versión detectada: "
        + (
            f"{detected_version} ({version_source})"
            if detected_version
            else "no encontrada"
        )
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


def _infer_p1_candidates(
    detection: ProjectDetection,
    endpoint_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detecta candidatos de Pilar 1 sin inventar la política de acceso.

    BOLA/RBAC dependen de semántica que el código por sí solo no siempre
    permite afirmar (propietario real, rol permitido, objeto de prueba).
    Por eso estos elementos quedan como candidatos confirmables y no como
    hallazgos ejecutables hasta completar sus campos de seguridad.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    sensitive_tokens = (
        "admin", "administr", "audit", "auditoria", "auditoría",
        "role", "rol", "permission", "permiso", "priorizar",
        "priorit", "manage", "gestion", "gestión", "config",
    )
    auth_source_tokens = (
        "authorize", "authorized", "authorization", "authenticated",
        "login_required", "current_user", "has_role", "has_permission",
        "permission", "permiso", "role", "rol", "policy", "guard",
        "principal", "securitycontext", "[authorize", "@preauthorize",
        "@secured", "is_authenticated", "request.user",
    )
    agent_tokens = (
        "assistant", "asistente", "agent", "agente", "chat",
        "herramienta", "tool", "copilot", "function_call",
    )
    source_cache: dict[str, str] = {}

    def source_texts(files: list[str]) -> str:
        chunks: list[str] = []
        for source in files:
            if source not in source_cache:
                source_cache[source] = _read_text(
                    detection.root / source,
                    limit=MAX_TEXT_SCAN_BYTES,
                ).lower()
            if source_cache[source]:
                chunks.append(source_cache[source])
        return "\n".join(chunks)

    for item in endpoint_inventory:
        method = str(item.get("metodo") or "").upper()
        route = str(item.get("ruta") or "")
        source_files = list(item.get("archivos") or [])
        lower_route = route.lower()
        lower_source = source_texts(source_files)

        has_object_parameter = (
            "<" in route
            or "{" in route
            or re.search(
                r"/(?::|\$\{)?(?:id|\w+_id)(?:\}|$|/)",
                lower_route,
            )
            is not None
        )
        if has_object_parameter and method in {
            "GET", "PATCH", "PUT", "DELETE"
        }:
            key = ("bola", method, route)
            if key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "familia": "BOLA",
                        "tipo_control": "bola",
                        "metodo": method,
                        "ruta_detectada": route,
                        "archivos_fuente": source_files,
                        "requiere_confirmacion": [
                            "ruta_ejecutable",
                            "id_prueba",
                            "propietario_esperado",
                        ],
                        "motivo": (
                            "Endpoint orientado a objeto con identificador "
                            "en la ruta."
                        ),
                    }
                )

        # IDOR/BOLA por parámetro de consulta. Algunos frameworks
        # mantienen la ruta literal (/profile) y reciben el identificador
        # mediante ?id=..., req.query, request.args o getParameter.
        query_id = re.search(
            r"(?:getparameter\s*\(|args\.get\s*\(|query\.(?:id|\w+_id)|query\[['\"](?:id|\w+_id)['\"]\])",
            lower_source,
        )
        if query_id and method in {"GET", "PATCH", "PUT", "DELETE"}:
            key = ("bola-query", method, route)
            if key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "familia": "BOLA",
                        "tipo_control": "bola",
                        "metodo": method,
                        "ruta_detectada": route,
                        "parametro_objeto": "id",
                        "archivos_fuente": source_files,
                        "requiere_confirmacion": [
                            "ruta_ejecutable",
                            "id_prueba",
                            "propietario_esperado",
                            "parametro_objeto",
                        ],
                        "motivo": (
                            "El endpoint obtiene un identificador de objeto "
                            "desde un parámetro de consulta."
                        ),
                    }
                )

        if (
            any(token in lower_route for token in sensitive_tokens)
            or any(token in lower_source for token in auth_source_tokens)
        ):
            key = ("rbac", method, route)
            if key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "familia": "RBAC_ABAC",
                        "tipo_control": "acceso",
                        "metodo": method,
                        "ruta_detectada": route,
                        "archivos_fuente": source_files,
                        "requiere_confirmacion": [
                            "cuenta",
                            "acceso_esperado",
                        ],
                        "motivo": (
                            "Ruta con semántica administrativa, de auditoría "
                            "o de operación privilegiada."
                        ),
                    }
                )

        if (
            any(token in lower_route for token in agent_tokens)
            or any(token in lower_source for token in agent_tokens)
        ):
            key = ("scope", method, route)
            if key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "familia": "AGENT_SCOPE",
                        "tipo_control": "alcance_agente",
                        "metodo": method,
                        "ruta_detectada": route,
                        "archivos_fuente": source_files,
                        "requiere_confirmacion": [
                            "cuenta",
                            "direct_ruta",
                            "agent_cuerpo",
                            "campos_json",
                        ],
                        "motivo": (
                            "Endpoint asociado a asistente/agente/herramienta "
                            "que puede ampliar el alcance de la identidad."
                        ),
                    }
                )

    return candidates


def _is_p1_evidence_source(relative: Path) -> bool:
    parts = {part.lower() for part in relative.parts}
    name = relative.name.lower()
    stem = relative.stem.lower()
    tokens = {
        "test", "tests", "spec", "specs", "fixture", "fixtures",
        "seed", "seeds", "sample", "samples", "support", "mock",
        "mocks", "data", "datos",
    }
    return (
        bool(parts & tokens)
        or any(token in stem for token in tokens)
        or name.startswith(("test_", "spec_"))
        or name.endswith(("_test.py", ".spec.js", ".test.js"))
    )


def _parameter_to_profile_route(route: str) -> str:
    value = str(route or "").strip()
    value = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", "{id}", value)
    value = re.sub(r"\{[^{}]+\}", "{id}", value)
    value = re.sub(r":(?:id|\w+_id)(?=/|$)", "{id}", value, flags=re.I)
    return _normalize_route_path(value)


def _route_matches_literal(
    parameterized: str,
    literal: str,
    object_id: str,
) -> bool:
    normalized = _parameter_to_profile_route(parameterized)
    expected = normalized.replace("{id}", str(object_id))
    return _normalize_route_path(literal) == expected


def _extract_owner_samples(
    detection: ProjectDetection,
) -> list[dict[str, Any]]:
    """Extrae pares objeto-propietario desde tests/fixtures/seeds.

    Primero usa estructuras JSON reales con inferencia semántica genérica.
    Después aplica un fallback textual para Python/YAML/SQL. No depende de un
    nombre de dominio concreto como "solicitud" ni exige la palabra exacta
    "propietario".
    """
    usernames = {
        str(item.get("username") or "").strip()
        for item in detection.accounts
        if str(item.get("username") or "").strip()
    }
    if not usernames:
        return []

    identity_aliases: dict[str, str] = {}
    for account_evidence in detection.account_sources:
        username = str(account_evidence.get("username") or "").strip()
        if username not in usernames:
            continue
        for alias in account_evidence.get("identity_aliases") or []:
            alias_text = str(alias).strip()
            if alias_text and alias_text not in usernames:
                identity_aliases[alias_text] = username

    samples: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_sample(
        evidence: dict[str, Any],
        source: str,
        detector: str,
        context: str,
    ) -> None:
        object_id = str(evidence.get("id_prueba") or "").strip()
        owner = str(
            evidence.get("propietario_esperado") or ""
        ).strip()
        if not object_id or owner not in usernames:
            return
        key = (object_id, owner, source)
        if key in seen:
            return
        seen.add(key)
        samples.append(
            {
                "id_prueba": object_id,
                "propietario_esperado": owner,
                "archivo": source,
                "confianza": evidence.get("confianza") or "alta",
                "detector": detector,
                "campo_id": evidence.get("campo_id"),
                "campo_propietario": evidence.get(
                    "campo_propietario"
                ),
                "contexto": context.lower(),
            }
        )

    def walk_json(value: Any, source: str) -> None:
        if isinstance(value, dict):
            evidence = infer_object_identity(
                value,
                usernames,
                identity_aliases=identity_aliases,
            )
            if evidence:
                add_sample(
                    evidence,
                    source,
                    "structured-fixture-owner",
                    json.dumps(
                        value,
                        ensure_ascii=False,
                    )[:1600],
                )
            for nested in value.values():
                walk_json(nested, source)
        elif isinstance(value, list):
            for nested in value:
                walk_json(nested, source)

    for path, relative in _iter_source_files(
        detection.root,
        max_files=None,
    ):
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue
        source = relative.as_posix()

        # Las semillas de propiedad también suelen vivir en db.py/db.js o
        # inicializadores Java. Son evidencia P1 válida cuando contienen datos
        # de objetos, aunque no estén dentro de tests/fixtures/seeds.
        evidence_source = _is_p1_evidence_source(relative)
        has_seed_data = bool(
            re.search(
                r"(?is)INSERT\s+INTO|executemany\s*\(|"
                r"VALUES\s*\(|"
                r"\b(?:users|tickets|orders|products|records|registros)\b.{0,180}\b"
                r"(?:owner|owned_by|created_by|propietario|user_id|usuario_id)\b",
                text,
            )
        )
        if not evidence_source and not has_seed_data:
            continue

        for record in seed_records(text):
            evidence = infer_object_identity(record, usernames, identity_aliases=identity_aliases)
            # El perfil de una cuenta pertenece a la identidad de esa fila.
            username = str(record.get("username") or "")
            if not evidence and username in usernames and record.get("id") is not None:
                evidence = {
                    "id_prueba": str(record["id"]),
                    "propietario_esperado": username,
                    "campo_id": "id", "campo_propietario": "username",
                    "confianza": "alta",
                }
            if evidence:
                add_sample(evidence, source, "literal-seed-owner", json.dumps(record, ensure_ascii=False))

        # Evidencia estructurada: soporta aliases como codigo/creador,
        # author/record_id, created_by/uuid, etc.
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if payload is not None:
                walk_json(payload, source)

        # Fallback textual genérico: descubre el nombre del campo que contiene
        # una cuenta conocida y lo puntúa por semántica de propiedad.
        identity_values = {
            username: username for username in usernames
        }
        identity_values.update(identity_aliases)
        for identity_value, username in identity_values.items():
            user_re = re.escape(identity_value)
            for owner_match in re.finditer(
                rf"""(?ix)
                ["']?([A-Za-z_][A-Za-z0-9_.-]{{1,100}})["']?
                \s*[:=]\s*["']{user_re}["']
                """,
                text,
            ):
                owner_field = owner_match.group(1)
                owner_score = owner_key_score(owner_field)
                if owner_score <= 0:
                    continue

                start_window = max(0, owner_match.start() - 900)
                end_window = min(len(text), owner_match.end() + 900)
                window = text[start_window:end_window]
                id_candidates: list[
                    tuple[int, str, str]
                ] = []

                for id_match in re.finditer(
                    r"""(?ix)
                    ["']?([A-Za-z_][A-Za-z0-9_.-]{0,100})["']?
                    \s*[:=]\s*
                    ["']?([A-Za-z0-9._:-]{1,160})["']?
                    """,
                    window,
                ):
                    field = id_match.group(1)
                    value = id_match.group(2)
                    score = id_key_score(field)
                    if score > 0:
                        id_candidates.append(
                            (score, field, value)
                        )

                if not id_candidates:
                    continue
                id_candidates.sort(reverse=True)
                score, id_field, object_id = id_candidates[0]
                add_sample(
                    {
                        "id_prueba": object_id,
                        "propietario_esperado": username,
                        "campo_id": id_field,
                        "campo_propietario": owner_field,
                        "confianza": (
                            "alta"
                            if owner_score >= 80 and score >= 85
                            else "media"
                        ),
                    },
                    source,
                    "text-semantic-owner",
                    window,
                )

        # Seeds SQL: transforma cada fila en un mapping y usa el mismo motor
        # semántico que JSON en vez de una lista fija de columnas.
        for match in re.finditer(
            r"INSERT\s+INTO\s+[\w.\"-]+\s*"
            r"\(([^)]+)\)\s*VALUES\s*\(([^;]+?)\)",
            text,
            re.I | re.S,
        ):
            columns = [
                column.strip().strip('"').strip("'")
                for column in match.group(1).split(",")
            ]
            values = _split_sql_values(match.group(2))
            if len(columns) != len(values):
                continue

            mapping = {
                column: _clean_literal(value)
                for column, value in zip(columns, values)
            }
            evidence = infer_object_identity(
                mapping,
                usernames,
                identity_aliases=identity_aliases,
            )
            if evidence:
                add_sample(
                    evidence,
                    source,
                    "seed-sql-semantic-owner",
                    match.group(0),
                )


    # SQL posicional sin lista de columnas:
    # INSERT INTO USERS VALUES (1,'admin',...). En Java/H2 y otros proyectos
    # pequeños es una fuente común de evidencia de propiedad.
    schema_by_table: dict[str, list[str]] = {}
    for path, relative in _iter_source_files(
        detection.root,
        max_files=None,
    ):
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue
        for create in re.finditer(
            r"(?is)CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"([A-Za-z0-9_.\"-]+)\s*\((.*?)\)",
            text,
        ):
            table = create.group(1).split(".")[-1].strip('"').lower()
            columns: list[str] = []
            for definition in _split_sql_values(create.group(2)):
                match = re.match(
                    r"\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s+",
                    definition,
                )
                if match:
                    columns.append(match.group(1))
            if columns:
                schema_by_table[table] = columns

        for insert_match in re.finditer(
            r"(?is)INSERT\s+INTO\s+([A-Za-z0-9_.\"-]+)\s+VALUES\s*\(([^;]+?)\)",
            text,
        ):
            table = insert_match.group(1).split(".")[-1].strip('"').lower()
            columns = schema_by_table.get(table)
            if not columns:
                continue
            values = _split_sql_values(insert_match.group(2))
            if len(values) != len(columns):
                continue
            mapping = {
                column: _clean_literal(value)
                for column, value in zip(columns, values)
            }
            evidence = infer_object_identity(
                mapping,
                usernames,
                identity_aliases=identity_aliases,
            )
            if evidence:
                add_sample(
                    evidence,
                    relative.as_posix(),
                    "positional-sql-owner",
                    insert_match.group(0),
                )

    return samples


def _safe_literal_dict(value: str) -> dict[str, Any] | None:
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _safe_js_object_dict(value: str) -> dict[str, Any] | None:
    """Convierte objetos literales simples JS/TS usados en tests."""
    text = str(value or "").strip()
    if not text.startswith("{") or not text.endswith("}"):
        return None
    text = re.sub(
        r"(?m)([{,]\s*)([A-Za-z_$][A-Za-z0-9_$-]*)\s*:",
        r"\1'\2':",
        text,
    )
    text = re.sub(r"\btrue\b", "True", text, flags=re.I)
    text = re.sub(r"\bfalse\b", "False", text, flags=re.I)
    text = re.sub(r"\bnull\b", "None", text, flags=re.I)
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_http_test_contracts(
    detection: ProjectDetection,
) -> list[dict[str, Any]]:
    """Obtiene contratos HTTP expresados por tests Python y JS/TS.

    La salida es independiente del framework de tests: método, ruta, cuenta,
    status esperado, cuerpo de prueba y variable de respuesta.
    """
    usernames = [
        str(item.get("username") or "")
        for item in detection.accounts
        if item.get("username")
    ]
    contracts: list[dict[str, Any]] = []

    python_request_re = re.compile(
        r"""(?ix)
        \b(?P<var>[A-Za-z_]\w*)\s*=\s*
        [A-Za-z_][\w.]*\.
        (?P<method>get|post|put|patch|delete)\s*\(
        \s*["'](?P<route>/[^"']+)["']
        """
    )
    js_request_re = re.compile(
        r"""(?ix)
        (?:const|let|var)\s+(?P<var>[A-Za-z_$][\w$]*)\s*=\s*
        (?:await\s+)?
        (?:request\s*\([^)]*\)|[A-Za-z_$][\w$]*)
        \s*\.\s*
        (?P<method>get|post|put|patch|delete)\s*\(
        \s*["'`](?P<route>/[^"'`]+)["'`]
        """
    )

    security_name_tokens = (
        "access", "acceso", "auth", "authorization", "autoriz",
        "role", "rol", "rbac", "abac", "forbid", "denied", "deny",
        "unauthor", "permiso", "permission", "admin", "audit",
        "auditoria", "coordin", "supervisor", "prioriz", "bola",
        "owner", "propiet", "scope", "alcance", "escalada",
        "identity", "identidad", "agent", "agente", "asistente",
        "security", "seguridad", "privilege", "privilegio",
    )

    for path, relative in _iter_source_files(
        detection.root,
        max_files=None,
    ):
        if not _is_p1_evidence_source(relative):
            continue
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue
        source = relative.as_posix()
        suffix = path.suffix.lower()

        patterns = [python_request_re]
        if suffix in {
            ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"
        }:
            patterns.append(js_request_re)

        seen_matches: set[tuple[int, str, str]] = set()
        for request_re in patterns:
            for match in request_re.finditer(text):
                method = match.group("method").upper()
                route = match.group("route")
                match_key = (match.start(), method, route)
                if match_key in seen_matches:
                    continue
                seen_matches.add(match_key)

                start_window = max(0, match.start() - 1200)
                end_window = min(len(text), match.start() + 2600)
                window = text[start_window:end_window]
                before = text[
                    max(0, match.start() - 1600):match.start()
                ]

                test_name = ""
                python_names = list(
                    re.finditer(
                        r"(?im)^\s*(?:def|async\s+def)\s+"
                        r"(test_[A-Za-z0-9_]+)\s*\(",
                        before,
                    )
                )
                if python_names:
                    test_name = python_names[-1].group(1)
                else:
                    js_names = list(
                        re.finditer(
                            r"""(?is)
                            \b(?:it|test)\s*\(\s*
                            ["'`]([^"'`]{1,180})["'`]
                            """,
                            before,
                        )
                    )
                    if js_names:
                        test_name = js_names[-1].group(1)

                security_intent = any(
                    token in (
                        test_name + " " + window[:700]
                    ).lower()
                    for token in security_name_tokens
                )

                username = next(
                    (
                        item
                        for item in usernames
                        if item and item in window
                    ),
                    None,
                )

                var_name = match.group("var")
                var = re.escape(var_name)
                status: int | None = None
                status_patterns = (
                    rf"\b{var}\.status_code\s*==\s*(\d{{3}})",
                    rf"\bassert\s+(\d{{3}})\s*==\s*{var}\.status_code",
                    rf"\b{var}\.status(?:_code)?\s*==\s*(\d{{3}})",
                    rf"expect\s*\(\s*{var}\.(?:status|statusCode)\s*\)"
                    rf"\s*\.\s*(?:toBe|toEqual)\s*\(\s*(\d{{3}})\s*\)",
                )
                for pattern in status_patterns:
                    status_match = re.search(
                        pattern,
                        window,
                        re.I,
                    )
                    if status_match:
                        status = int(status_match.group(1))
                        break
                if status is None:
                    chain_status = re.search(
                        r"\.expect\s*\(\s*(\d{3})\s*\)",
                        window,
                        re.I,
                    )
                    if chain_status:
                        status = int(chain_status.group(1))

                body = None
                body_match = re.search(
                    r"\bjson\s*=\s*(\{.{0,1200}?\})",
                    window,
                    re.S,
                )
                if body_match:
                    body = _safe_literal_dict(body_match.group(1))
                if body is None:
                    send_match = re.search(
                        r"\.send\s*\(\s*(\{.{0,1200}?\})\s*\)",
                        window,
                        re.S,
                    )
                    if send_match:
                        body = _safe_js_object_dict(
                            send_match.group(1)
                        )

                contracts.append(
                    {
                        "metodo": method,
                        "ruta": route,
                        "cuenta": username,
                        "http_esperado": status,
                        "cuerpo": body,
                        "archivo": source,
                        "test": test_name,
                        "variable": var_name,
                        "intencion_seguridad": security_intent,
                    }
                )

    return contracts


def _infer_agent_scope_checks(
    detection: ProjectDetection,
    endpoint_inventory: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruye controles de alcance de agente desde contratos de tests.

    No exige vocabulario de una aplicación concreta. Identifica una petición
    directa y una petición hacia agente/asistente en el mismo test, y deriva
    los campos de pasos/herramienta/conteo desde las aserciones observadas.
    """
    checks: list[dict[str, Any]] = []
    agent_tokens = (
        "agent", "agente", "assistant", "asistente",
        "copilot", "chat", "tool", "herramienta",
    )
    step_tokens = (
        "step", "steps", "paso", "pasos", "actions", "acciones",
        "calls", "invocations", "invocaciones", "trace", "traza",
    )
    tool_tokens = (
        "tool", "herramienta", "function", "funcion",
        "action", "accion", "name", "nombre",
    )
    count_tokens = (
        "count", "total", "returned", "devueltas", "devueltos",
        "result_count", "items_count", "cantidad",
    )

    get_routes = {
        str(item.get("ruta") or "")
        for item in endpoint_inventory
        if str(item.get("metodo") or "").upper() == "GET"
    }

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for contract in contracts:
        source = str(contract.get("archivo") or "")
        test_name = str(contract.get("test") or "")
        grouped.setdefault((source, test_name), []).append(contract)

    def fields_near_variable(
        source_text: str,
        variable: str,
    ) -> list[str]:
        if not variable:
            return []
        var = re.escape(variable)
        fields: list[str] = []

        # Python: response.json['steps'][0]['tool'],
        # response.get_json()['steps']... y aliases:
        # payload = response.get_json(); payload['steps']...
        python_accessors = (
            rf"\b{var}\.(?:json|body)(?:\(\))?",
            rf"\b{var}\.get_json\s*\(\s*\)",
        )
        for accessor in python_accessors:
            for match in re.finditer(
                rf"""(?ix)
                {accessor}
                ((?:\s*\[\s*["'][^"']+["']\s*\]
                  |\s*\[\s*\d+\s*\]){{1,8}})
                """,
                source_text,
            ):
                fields.extend(
                    re.findall(
                        r"""\[\s*["']([^"']+)["']\s*\]""",
                        match.group(1),
                    )
                )

        alias_names = re.findall(
            rf"""(?imx)^\s*([A-Za-z_]\w*)\s*=\s*
            {var}\.get_json\s*\(\s*\)\s*$""",
            source_text,
        )
        for alias in alias_names:
            escaped_alias = re.escape(alias)
            for match in re.finditer(
                rf"""(?ix)
                \b{escaped_alias}
                ((?:\s*\[\s*["'][^"']+["']\s*\]
                  |\s*\[\s*\d+\s*\]){{1,8}})
                """,
                source_text,
            ):
                fields.extend(
                    re.findall(
                        r"""\[\s*["']([^"']+)["']\s*\]""",
                        match.group(1),
                    )
                )

        # JS/TS: response.body.steps[0].tool
        for match in re.finditer(
            rf"""(?ix)
            \b{var}\.(?:body|json)
            ((?:\.[A-Za-z_$][\w$]*|\[\d+\]){{1,8}})
            """,
            source_text,
        ):
            fields.extend(
                re.findall(
                    r"\.([A-Za-z_$][\w$]*)",
                    match.group(1),
                )
            )

        return fields

    def choose_field(
        fields: list[str],
        tokens: tuple[str, ...],
    ) -> str | None:
        for field in fields:
            normalized = normalize_key(field)
            if any(token in normalized for token in tokens):
                return field
        return None

    index = 1
    for (source, _test_name), items in grouped.items():
        if not source:
            continue
        source_text = _read_text(
            detection.root / source,
            limit=MAX_TEXT_SCAN_BYTES,
        )
        if not source_text:
            continue

        agents = [
            item
            for item in items
            if item.get("metodo") == "POST"
            and (
                any(
                    token in str(item.get("ruta") or "").lower()
                    for token in agent_tokens
                )
                or any(
                    token in str(item.get("test") or "").lower()
                    for token in ("scope", "alcance", "identity", "identidad")
                )
            )
            and item.get("cuenta")
            and isinstance(item.get("cuerpo"), dict)
        ]
        if not agents:
            continue

        for agent in agents:
            direct_candidates = [
                item
                for item in items
                if item.get("metodo") == "GET"
                and item.get("ruta") in get_routes
                and item.get("ruta") != agent.get("ruta")
            ]
            if not direct_candidates:
                continue

            direct = direct_candidates[0]
            variable = str(agent.get("variable") or "")
            fields = fields_near_variable(source_text, variable)
            steps_field = choose_field(fields, step_tokens)
            tool_field = choose_field(fields, tool_tokens)
            count_field = choose_field(fields, count_tokens)

            if not steps_field or not tool_field or not count_field:
                continue

            tool_name = ""
            tool_patterns = (
                rf"""(?ix)
                ["']{re.escape(tool_field)}["']
                \s*\]\s*(?:==|!=)\s*["']([^"']+)["']
                """,
                rf"""(?ix)
                \.{re.escape(tool_field)}
                \s*\)*
                \s*\.\s*(?:toBe|toEqual)\s*\(\s*
                ["']([^"']+)["']
                """,
                rf"""(?ix)
                ["']?{re.escape(tool_field)}["']?
                .{{0,80}}?
                (?:==|toBe\s*\(|toEqual\s*\()
                \s*["']([^"']+)["']
                """,
            )
            for pattern in tool_patterns:
                tool_match = re.search(pattern, source_text)
                if tool_match:
                    tool_name = tool_match.group(1)
                    break
            if not tool_name:
                # Sin herramienta concreta no podemos filtrar la invocación
                # correcta con suficiente confianza.
                continue

            checks.append(
                {
                    "tipo": "alcance_agente",
                    "id_control": f"P1-AUTO-SCOPE-{index:03d}",
                    "nombre": (
                        "El agente conserva el alcance de la "
                        "identidad solicitante"
                    ),
                    "cuenta": agent["cuenta"],
                    "direct_metodo": "GET",
                    "direct_ruta": direct["ruta"],
                    "agent_ruta": agent["ruta"],
                    "agent_cuerpo": dict(agent["cuerpo"]),
                    "direct_json_path": "$",
                    "steps_json_path": f"$.{steps_field}",
                    "tool_name": tool_name,
                    "tool_field": tool_field,
                    "count_field": count_field,
                    "id_field": "id",
                    "archivos_fuente": [source],
                    "pistas_codigo": [
                        f"steps={steps_field}",
                        f"tool={tool_field}",
                        f"count={count_field}",
                    ],
                    "autogenerado": True,
                    "confianza": "alta",
                    "fuentes_evidencia": [source],
                }
            )
            index += 1

    return checks


def _infer_automatic_p1_checks(
    detection: ProjectDetection,
    endpoint_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruye controles P1 desde rutas + tests/fixtures/seeds."""
    checks: list[dict[str, Any]] = []
    owner_samples = _extract_owner_samples(detection)
    contracts = _extract_http_test_contracts(detection)

    privileged_roles = {
        str(account.get("role") or "").lower()
        for account in detection.accounts
        if str(account.get("role") or "").lower()
        in _PRIVILEGED_ROLES
    }
    usernames = {
        str(account.get("username") or "")
        for account in detection.accounts
    }

    # BOLA: requiere una relación objeto -> propietario explícita.
    bola_index = 1

    # Materializa IDOR/BOLA con ?id=... cuando el framework no expresa el
    # identificador en la ruta. La propiedad se obtiene de la misma evidencia
    # de datos que alimenta los controles /{id}.
    for item in endpoint_inventory:
        method = str(item.get("metodo") or "").upper()
        raw_route = str(item.get("ruta") or "")
        if method not in {"GET", "PATCH", "PUT", "DELETE"}:
            continue
        source_files = list(item.get("archivos") or [])
        source_text = "\n".join(
            _read_text(
                detection.root / source,
                limit=MAX_TEXT_SCAN_BYTES,
            )
            for source in source_files
            if source
        ).lower()
        param_match = re.search(
            r"(?:(?:getparameter|args\.get)\s*\(\s*['\"](?P<call>id|\w+_id)['\"]|"
            r"query\.(?P<attr>id|\w+_id)\b|query\[['\"](?P<index>id|\w+_id)['\"]\])",
            source_text,
            re.I,
        )
        if not param_match:
            continue

        parameter = next(value for value in param_match.groupdict().values() if value)

        route_tokens = [
            token.lower()
            for token in re.findall(r"[A-Za-zÀ-ÿ_]+", raw_route)
            if len(token) >= 3
        ]
        eligible_samples = [
            evidence
            for evidence in owner_samples
            if evidence.get("propietario_esperado") in usernames
        ]
        ranked_samples = sorted(
            eligible_samples,
            key=lambda evidence: sum(
                1
                for token in route_tokens
                if token in (
                    str(evidence.get("archivo") or "")
                    + " "
                    + str(evidence.get("contexto") or "")
                ).lower()
            ),
            reverse=True,
        )
        if not ranked_samples:
            continue
        sample = ranked_samples[0]
        object_id = str(sample.get("id_prueba") or "").strip()
        owner = str(sample.get("propietario_esperado") or "").strip()
        if not object_id or owner not in usernames:
            continue

        separator = "&" if "?" in raw_route else "?"
        profile_route = (
            raw_route
            + separator
            + f"{parameter}={{id}}"
        )
        control_id = f"P1-AUTO-BOLA-{bola_index:03d}"
        bola_index += 1
        checks.append(
            {
                "tipo": "bola",
                "id_control": control_id,
                "nombre": f"Control de propiedad sobre {method} {profile_route}",
                "descripcion": (
                    "El acceso al objeto identificado por parámetro debe "
                    "respetar propietario o rol privilegiado."
                ),
                "metodo": method,
                "ruta": profile_route,
                "id_prueba": object_id,
                "propietario_esperado": owner,
                "cuerpo_prueba": None,
                "codigos_permitidos": [200, 201, 204],
                "archivos_fuente": source_files,
                "pistas_codigo": [
                    f"parámetro de objeto: {parameter}",
                    "propietario",
                    "owner",
                    "autorización por objeto",
                ],
                "autogenerado": True,
                "confianza": "alta",
                "fuentes_evidencia": list(
                    dict.fromkeys(
                        source_files
                        + [str(sample.get("archivo") or "")]
                    )
                ),
            }
        )
    for item in endpoint_inventory:
        method = str(item.get("metodo") or "").upper()
        raw_route = str(item.get("ruta") or "")
        if method not in {"GET", "PATCH", "PUT", "DELETE"}:
            continue
        if not any(token in raw_route for token in ("<", "{")) and not re.search(
            r":(?:id|\w+_id)(?=/|$)",
            raw_route,
            re.I,
        ):
            continue

        profile_route = _parameter_to_profile_route(raw_route)
        if "{id}" not in profile_route:
            continue

        route_tokens = [
            token.lower()
            for token in re.findall(r"[A-Za-zÀ-ÿ_]+", profile_route)
            if token.lower() not in {
                "api", "id", "int", "string", "uuid",
            }
            and len(token) >= 3
        ]
        source_text = "\n".join(_read_text(detection.root / source) for source in item.get("archivos", []))
        # Un SELECT sobre cuentas vincula su id al username en las semillas,
        # aunque la ruta se llame /profile y el archivo de datos db.py.
        if re.search(r"\bSELECT\b.{0,180}\busername\b", source_text, re.I | re.S):
            route_tokens.append("username")
        eligible_samples = [
            evidence
            for evidence in owner_samples
            if evidence.get("propietario_esperado") in usernames
        ]
        ranked_samples = sorted(
            eligible_samples,
            key=lambda evidence: sum(
                1
                for token in route_tokens
                if token in (
                    str(evidence.get("archivo") or "")
                    + " "
                    + str(evidence.get("contexto") or "")
                ).lower()
            ),
            reverse=True,
        )
        if not ranked_samples:
            continue
        best_score = sum(
            1
            for token in route_tokens
            if token in (
                str(ranked_samples[0].get("archivo") or "")
                + " "
                + str(ranked_samples[0].get("contexto") or "")
            ).lower()
        )
        if best_score == 0 and len(eligible_samples) > 1:
            # Con varias semillas de entidades distintas no asociamos la
            # primera arbitrariamente a cualquier endpoint.
            continue
        sample = ranked_samples[0]

        object_id = str(sample["id_prueba"])
        matching_contract = next(
            (
                contract
                for contract in contracts
                if contract.get("metodo") == method
                and _route_matches_literal(
                    profile_route,
                    str(contract.get("ruta") or ""),
                    object_id,
                )
            ),
            None,
        )
        body = (
            matching_contract.get("cuerpo")
            if matching_contract
            else None
        )
        # Escrituras sin cuerpo de prueba verificable suelen producir 400 y
        # esconder un BOLA real. En ese caso se conserva como candidato.
        if method in {"PATCH", "PUT"} and body is None:
            continue

        control_id = f"P1-AUTO-BOLA-{bola_index:03d}"
        bola_index += 1
        route_sources = list(item.get("archivos") or [])
        evidence_sources = list(
            dict.fromkeys(
                route_sources
                + [str(sample["archivo"])]
                + (
                    [str(matching_contract["archivo"])]
                    if matching_contract
                    else []
                )
            )
        )
        checks.append(
            {
                "tipo": "bola",
                "id_control": control_id,
                "nombre": (
                    f"Control de propiedad sobre {method} {profile_route}"
                ),
                "descripcion": (
                    "El acceso al objeto debe respetar propietario o "
                    "rol privilegiado."
                ),
                "metodo": method,
                "ruta": profile_route,
                "id_prueba": object_id,
                "propietario_esperado": sample[
                    "propietario_esperado"
                ],
                "cuerpo_prueba": body,
                "codigos_permitidos": [200, 201, 204],
                "archivos_fuente": route_sources,
                "pistas_codigo": [
                    "propietario",
                    "owner",
                    "autorización por objeto",
                ],
                "autogenerado": True,
                "confianza": "alta",
                "fuentes_evidencia": evidence_sources,
            }
        )

    # RBAC/ABAC: un test con intención explícita de seguridad, identidad
    # conocida y status esperado ya expresa la política, aunque la ruta no
    # contenga palabras como "admin" o "audit".
    access_index = 1
    seen_access: set[tuple[str, str, str]] = set()
    for contract in contracts:
        route = str(contract.get("ruta") or "")
        username = str(contract.get("cuenta") or "")
        status = contract.get("http_esperado")
        method = str(contract.get("metodo") or "").upper()
        if (
            not contract.get("intencion_seguridad")
            or not username
            or username not in usernames
            or not isinstance(status, int)
        ):
            continue
        if status in {401, 403}:
            expected = False
        elif 200 <= status < 300:
            expected = True
        else:
            continue

        key = (username, method, route)
        if key in seen_access:
            continue
        seen_access.add(key)
        control_id = f"P1-AUTO-ACCESS-{access_index:03d}"
        access_index += 1
        checks.append(
            {
                "tipo": "acceso",
                "id_control": control_id,
                "nombre": (
                    f"Política de acceso {method} {route} para {username}"
                ),
                "cuenta": username,
                "metodo": method,
                "ruta": route,
                "acceso_esperado": expected,
                "cuerpo": contract.get("cuerpo"),
                "codigos_permitidos": [200, 201, 204],
                "archivos_fuente": [contract["archivo"]],
                "pistas_codigo": [
                    "rol",
                    "permiso",
                    "status esperado en test",
                ],
                "autogenerado": True,
                "confianza": "alta",
                "fuentes_evidencia": [contract["archivo"]],
            }
        )

    # Fallback de RBAC: cuando no hay contrato explícito para una ruta
    # fuertemente privilegiada, usamos la separación de roles detectada para
    # crear únicamente una prueba negativa de bajo privilegio. Se calcula
    # contra los controles realmente creados y no contra un set auxiliar, para
    # evitar perder rutas por deduplicaciones intermedias.
    strong_sensitive_tokens = (
        "/admin", "admin/", "audit", "auditoria", "auditoría",
        "prioriz", "priorit", "priority", "manage", "management",
        "gestion", "gestión",
        "roles", "permissions", "permisos", "privileged",
        "approve", "approval", "authorize", "authorization",
    )
    role_names = {
        str(account.get("role") or "").strip().lower()
        for account in detection.accounts
        if str(account.get("role") or "").strip()
    }
    high_role_accounts = [
        account
        for account in detection.accounts
        if str(account.get("username") or "")
        and str(account.get("role") or "").lower()
        in privileged_roles
    ]
    low_accounts = [
        account
        for account in detection.accounts
        if str(account.get("username") or "")
        and (
            str(account.get("role") or "").lower()
            not in privileged_roles
        )
    ]

    # Si un proyecto usa nombres de rol no incluidos en el diccionario común,
    # conservamos el fallback solamente cuando hay una separación clara de
    # roles y al menos una cuenta cuyo rol coincide con una señal de privilegio.
    if not high_role_accounts and len(role_names) >= 2:
        privilege_role_tokens = (
            "admin", "root", "manager", "gerente", "coord",
            "supervisor", "owner", "security", "operator",
        )
        high_role_accounts = [
            account
            for account in detection.accounts
            if any(
                token in str(account.get("role") or "").lower()
                for token in privilege_role_tokens
            )
        ]
        high_usernames = {
            str(account.get("username") or "")
            for account in high_role_accounts
        }
        if high_usernames:
            low_accounts = [
                account
                for account in detection.accounts
                if str(account.get("username") or "")
                and str(account.get("username") or "")
                not in high_usernames
            ]

    if high_role_accounts and low_accounts:
        existing_access_keys = {
            (
                str(item.get("cuenta") or ""),
                str(item.get("metodo") or "").upper(),
                str(item.get("ruta") or ""),
            )
            for item in checks
            if str(item.get("tipo") or "").lower() == "acceso"
        }

        strong_routes = [
            item
            for item in endpoint_inventory
            if str(item.get("metodo") or "").upper()
            in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            and any(
                token in str(item.get("ruta") or "").lower()
                for token in strong_sensitive_tokens
            )
        ]

        for item in strong_routes:
            route = str(item.get("ruta") or "")
            method = str(item.get("metodo") or "").upper()
            sources = list(item.get("archivos") or [])

            for account in low_accounts[:3]:
                username = str(account.get("username") or "")
                key = (username, method, route)
                if key in existing_access_keys:
                    continue

                checks.append(
                    {
                        "tipo": "acceso",
                        "id_control": (
                            f"P1-AUTO-ACCESS-{access_index:03d}"
                        ),
                        "nombre": (
                            "La operación privilegiada debe rechazar "
                            f"{method} {route} para {username}"
                        ),
                        "cuenta": username,
                        "metodo": method,
                        "ruta": route,
                        "acceso_esperado": False,
                        "cuerpo": {},
                        "codigos_permitidos": [200, 201, 204],
                        "archivos_fuente": sources,
                        "pistas_codigo": [
                            "ruta con semántica privilegiada",
                            "separación de roles detectada",
                        ],
                        "autogenerado": True,
                        "confianza": "media-alta",
                        "fuentes_evidencia": sources,
                    }
                )
                existing_access_keys.add(key)
                access_index += 1

    checks.extend(
        _infer_agent_scope_checks(
            detection,
            endpoint_inventory,
            contracts,
        )
    )

    return checks


def _materialize_p1_registry(
    registry: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    endpoints: list[dict[str, Any]] = []
    access: list[dict[str, Any]] = []
    agent: list[dict[str, Any]] = []

    for raw in registry:
        tipo = str(raw.get("tipo") or "").lower()
        if tipo == "bola":
            endpoint = {
                key: raw[key]
                for key in (
                    "metodo", "ruta", "id_prueba",
                    "propietario_esperado", "cuerpo_prueba",
                    "codigos_permitidos", "id_control",
                    "descripcion", "archivos_fuente", "pistas_codigo",
                )
                if key in raw
            }
            endpoints.append(endpoint)
        elif tipo == "acceso":
            item = {
                key: raw[key]
                for key in (
                    "id_control", "nombre", "cuenta", "metodo", "ruta",
                    "acceso_esperado", "cuerpo", "codigos_permitidos",
                    "archivos_fuente", "pistas_codigo",
                )
                if key in raw
            }
            access.append(item)
        elif tipo == "alcance_agente":
            item = {
                key: raw[key]
                for key in (
                    "nombre", "cuenta", "direct_metodo", "direct_ruta",
                    "agent_ruta", "agent_cuerpo", "direct_json_path",
                    "steps_json_path", "tool_name", "tool_field",
                    "count_field", "id_field", "agent_items_json_path",
                    "id_control", "archivos_fuente", "pistas_codigo",
                )
                if key in raw
            }
            agent.append(item)

    return endpoints, access, agent


def _infer_automatic_p2_checks(
    detection: ProjectDetection,
    endpoint_inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Genera controles P2 de alta confianza desde código/configuración.

    Los detectores están orientados a conceptos, no a una aplicación:
    CORS reflejado, secretos con fallback, debug explícito, cookies de sesión
    inseguras, bypass de límites sin guardia de autorización y contenedores
    root. Las coincidencias ambiguas no se activan automáticamente.
    """
    root = detection.root
    checks: list[dict[str, Any]] = []

    get_routes = [
        str(item.get("ruta") or "")
        for item in endpoint_inventory
        if str(item.get("metodo") or "").upper() == "GET"
        and "<" not in str(item.get("ruta") or "")
        and "{" not in str(item.get("ruta") or "")
    ]
    cors_route = next(
        (route for route in get_routes if route == "/health"),
        next(
            (route for route in get_routes if route.startswith("/api/")),
            next(iter(get_routes), "/"),
        ),
    )

    cors_source: str | None = None
    secret_match: tuple[str, str] | None = None
    debug_match: tuple[str, str] | None = None
    cookie_match: tuple[str, str] | None = None
    bypass_matches: list[tuple[str, str, list[str]]] = []

    python_secret = re.compile(
        r"""(?imx)
        ^\s*[^\n#]*
        (?:SECRET(?:_KEY)?|TOKEN|API_KEY|PASSWORD|JWT(?:_SECRET)?)
        \s*=\s*
        os\.(?:getenv|environ\.get)\(
        [^,\n]+,\s*
        (?:
            (["'])(?!none\1|null\1)[^"'\n]{3,}\1
            |
            [A-Za-z_][A-Za-z0-9_]*
        )
        \)
        """
    )
    js_secret = re.compile(
        r"""(?imx)
        (?:secret|token|api[_-]?key|password|jwt)
        [A-Za-z0-9_$.\[\]"']{0,120}
        process\.env(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])
        \s*(?:\|\||\?\?)\s*
        (["'])([^"'\n]{3,})\1
        """
    )
    properties_secret = re.compile(
        r"""(?imx)
        ^\s*
        (?:[A-Za-z0-9_.-]*)
        (?:secret|token|api[-_.]?key|password|jwt)
        (?:[A-Za-z0-9_.-]*)
        \s*[:=]\s*
        (?:changeme|change_me|secret|defaultsecret|dev-secret|development)
        \s*$
        """
    )

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

    bypass_tokens = (
        "bypass",
        "skip_limit",
        "skip_limits",
        "ignore_limit",
        "ignore_limits",
        "no_limit",
        "unlimited",
        "override_limit",
        "force",
        "forced",
        "urgent",
        "urgente",
        "exempt",
        "exento",
    )
    limit_tokens = (
        "limit",
        "limite",
        "límite",
        "quota",
        "cuota",
        "budget",
        "presupuesto",
        "rate",
        "throttle",
        "max_",
        "maximum",
        "size",
        "length",
        "longitud",
        "topes",
        "tope",
    )
    guard_tokens = (
        "role",
        "rol",
        "permission",
        "permiso",
        "authorize",
        "authorized",
        "autoriz",
        "is_admin",
        "admin",
        "coordinator",
        "coordinador",
        "supervisor",
        "has_permission",
        "can_",
        "policy",
        "guard",
    )

    allowed_suffixes = {
        ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx",
        ".java", ".kt", ".php", ".cs", ".rb", ".go",
        ".properties", ".env", ".cfg", ".conf", ".ini",
        ".yaml", ".yml", ".toml", ".json",
    }

    for path, relative in _iter_source_files(root, max_files=5000):
        if path.suffix.lower() not in allowed_suffixes:
            continue
        text = _read_text(path, limit=MAX_TEXT_SCAN_BYTES)
        if not text:
            continue

        source = relative.as_posix()
        lower = text.lower()

        if (
            cors_source is None
            and "access-control-allow-origin" in lower
            and "origin" in lower
            and "access-control-allow-credentials" in lower
        ):
            cors_source = source

        if secret_match is None:
            for pattern in (
                python_secret,
                js_secret,
                properties_secret,
            ):
                match = pattern.search(text)
                if match:
                    literal = match.group(0).strip()
                    # Si el fallback es un identificador simbólico, solo lo
                    # consideramos inseguro cuando su nombre comunica valor
                    # por defecto/desarrollo/secreto reutilizable.
                    fallback_match = re.search(
                        r",\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$",
                        literal,
                        re.I,
                    )
                    if fallback_match:
                        fallback_name = fallback_match.group(1).lower()
                        suspicious = (
                            "default", "defecto", "dev", "secret",
                            "secreto", "token", "password", "passwd",
                            "clave", "key",
                        )
                        if not any(
                            token in fallback_name
                            for token in suspicious
                        ):
                            continue
                    secret_match = (
                        source,
                        literal,
                    )
                    break

        if debug_match is None:
            for pattern in debug_patterns:
                if re.search(pattern, text, re.I | re.M | re.S):
                    debug_match = (source, pattern)
                    break

        if cookie_match is None:
            for pattern in cookie_patterns:
                if re.search(pattern, text, re.I | re.M | re.S):
                    cookie_match = (source, pattern)
                    break

        # Busca una rama de escape de límites y exige que en la misma
        # vecindad no exista una guardia de rol/permisos.
        for token in bypass_tokens:
            for match in re.finditer(
                rf"\b{re.escape(token)}\b",
                lower,
                re.I,
            ):
                window_start = max(0, match.start() - 900)
                window_end = min(len(text), match.end() + 1500)
                window = text[window_start:window_end]
                window_lower = window.lower()

                if not any(
                    limit_token in window_lower
                    for limit_token in limit_tokens
                ):
                    continue
                # Una mención de "admin/coordinator/role" muy lejos
                # de la rama no demuestra que el bypass esté protegido. La
                # guardia debe aparecer cerca de la condición que habilita la
                # excepción.
                guard_start = max(0, match.start() - 320)
                guard_end = min(len(text), match.end() + 420)
                guard_window = text[guard_start:guard_end].lower()
                if any(
                    guard in guard_window
                    for guard in guard_tokens
                ):
                    continue

                # Debe existir además alguna señal de control de flujo o
                # lectura de input; una mención en comentario/documentación
                # no basta.
                code_signals = (
                    "if ",
                    "if(",
                    "get(",
                    "[",
                    "request",
                    "body",
                    "payload",
                    "data.",
                )
                if not any(signal in window_lower for signal in code_signals):
                    continue

                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end < 0:
                    line_end = len(text)
                literal = text[line_start:line_end].strip()
                if not literal or literal.startswith(("#", "//", "*")):
                    continue

                evidence = [
                    f"bypass={token}",
                    "limit/quota/budget en ventana cercana",
                    "sin guardia de rol/permisos en ventana cercana",
                ]
                key = (source, literal)
                if not any(
                    existing[0] == source
                    and existing[1] == literal
                    for existing in bypass_matches
                ):
                    bypass_matches.append(
                        (source, literal, evidence)
                    )
                break

    if cors_source:
        checks.append(
            {
                "id_control": "P2-AUTO-CORS-001",
                "nombre": (
                    "CORS no debe reflejar orígenes arbitrarios "
                    "con credenciales"
                ),
                "tipo": "cors_reflection",
                "metodo": "GET",
                "ruta": cors_route,
                "headers": {
                    "Origin": "https://origen-no-autorizado.example"
                },
                "archivos_fuente": [cors_source],
                "pistas_codigo": [
                    "Access-Control-Allow-Origin",
                    "Access-Control-Allow-Credentials",
                ],
            }
        )

    if secret_match:
        relative, literal = secret_match
        checks.append(
            {
                "id_control": "P2-AUTO-SECRET-001",
                "nombre": (
                    "El secreto de aplicación no debe usar "
                    "un valor por defecto inseguro"
                ),
                "tipo": "source_contains",
                "archivo": relative,
                "patron_inseguro": literal,
                "patron_seguro": None,
                "archivos_fuente": [relative],
                "pistas_codigo": [
                    "secreto/token/credencial",
                    "fallback literal",
                ],
            }
        )

    if debug_match:
        relative, pattern = debug_match
        checks.append(
            {
                "id_control": "P2-AUTO-DEBUG-001",
                "nombre": (
                    "La configuración desplegable no debe habilitar "
                    "debug de forma explícita"
                ),
                "tipo": "source_regex",
                "archivo": relative,
                "patron_inseguro": pattern,
                "patron_seguro": None,
                "archivos_fuente": [relative],
                "pistas_codigo": ["debug=true/True"],
            }
        )

    if cookie_match:
        relative, pattern = cookie_match
        checks.append(
            {
                "id_control": "P2-AUTO-COOKIE-001",
                "nombre": (
                    "Las cookies de sesión no deben declarar "
                    "Secure=false"
                ),
                "tipo": "source_regex",
                "archivo": relative,
                "patron_inseguro": pattern,
                "patron_seguro": None,
                "archivos_fuente": [relative],
                "pistas_codigo": ["cookie/session", "secure=false"],
            }
        )

    for index, (relative, literal, evidence) in enumerate(
        bypass_matches[:12],
        start=1,
    ):
        checks.append(
            {
                "id_control": f"P2-AUTO-BYPASS-{index:03d}",
                "nombre": (
                    "Una vía de excepción no debe omitir límites "
                    "sin autorización"
                ),
                "tipo": "source_contains",
                "archivo": relative,
                "patron_inseguro": literal,
                "patron_seguro": None,
                "archivos_fuente": [relative],
                "pistas_codigo": evidence,
            }
        )

    dockerfile = root / "Dockerfile"
    if dockerfile.exists():
        checks.append(
            {
                "id_control": "P2-AUTO-DOCKER-001",
                "nombre": (
                    "El contenedor debe ejecutar con usuario "
                    "no privilegiado"
                ),
                "tipo": "docker_non_root",
                "archivo": "Dockerfile",
                "archivos_fuente": ["Dockerfile"],
                "pistas_codigo": ["USER"],
            }
        )

    return checks


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
    inferred_p1_candidates = _infer_p1_candidates(
        detection,
        endpoint_inventory,
    )
    inferred_p1_checks = _infer_automatic_p1_checks(
        detection,
        endpoint_inventory,
    )
    (
        inferred_endpoints,
        inferred_access_checks,
        inferred_agent_checks,
    ) = _materialize_p1_registry(inferred_p1_checks)
    p2_discovery = discover_pilar2(
        detection.root,
        endpoint_inventory,
    )
    inferred_p2_checks = list(p2_discovery["controles"])
    inferred_p2_candidates = list(p2_discovery["candidatos"])

    profile = {
        "sistema": _slug(name),
        "version_objetivo": (
            _normalize_version_candidate(version)
            if version is not None
            else detection.version
        ) or "desconocida",
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
        "chequeos_pilar1": inferred_p1_checks,
        "endpoints": inferred_endpoints,
        "endpoints_detectados": endpoint_inventory,
        "probar_todos_endpoints_con_todos_usuarios": True,
        "candidatos_pilar1": inferred_p1_candidates,
        "chequeos_agente": inferred_agent_checks,
        "chequeos_acceso": inferred_access_checks,
        "chequeos_pilar2": inferred_p2_checks,
        "candidatos_pilar2": inferred_p2_candidates,
        "estrategias_correccion_pilar2": list(
            p2_discovery["estrategias_correccion"]
        ),
        "correcciones": [],
        "metadata_detectada": {
            "nombre_proyecto": detection.name,
            "version_detectada": detection.version,
            "version_fuente": detection.version_source,
            "version_confianza": detection.version_confidence,
            "version_candidatas": list(detection.version_candidates),
            "lenguajes": detection.languages,
            "frameworks": detection.frameworks,
            "manifiestos": detection.manifests,
            "raices_codigo": detection.source_roots,
            "endpoints_candidatos": [
                route.as_dict() for route in detection.routes
            ],
            "total_endpoints_detectados": len(endpoint_inventory),
            "matriz_endpoint_usuario": {
                "habilitada": True,
                "combinaciones_previstas": (
                    len(endpoint_inventory) * len(detection.accounts)
                ),
                "politica_mutaciones": (
                    "GET/HEAD/OPTIONS directos; POST/PUT/PATCH con cuerpo "
                    "vacio; DELETE omitido para evitar perdida de datos"
                ),
            },
            "total_coincidencias_endpoint": len(detection.routes),
            "cuentas_candidatas": list(detection.account_sources),
            "archivos_cuentas_escaneados": True,
            "perfil_generado_automaticamente": True,
            "motor_evidencia": {
                "version": 2,
                "modo": "semantico-generico",
                "fuentes": [
                    "codigo",
                    "configuracion",
                    "documentacion",
                    "tests",
                    "fixtures",
                    "seeds",
                    "runtime-vivo-solo-lectura",
                ],
                "capacidades_pilar1": [
                    "BOLA/IDOR por propiedad",
                    "RBAC/ABAC desde contratos de seguridad",
                    "alcance de agente desde API directa vs agente",
                ],
                "capacidades_pilar2": [
                    "CORS estatico + GET/OPTIONS dinamico",
                    "secretos/fallbacks con contexto de entorno",
                    "bypass de limites como candidato diferencial",
                    "contenedor multi-stage + overrides runtime",
                    "debug y sesion extensibles por familia",
                    "deduplicacion hallazgo != caso de prueba",
                ],
                "politica_confianza": (
                    "solo activar controles cuando la evidencia es "
                    "ejecutable; lo ambiguo permanece como candidato"
                ),
            },
            "candidatos_pilar1": inferred_p1_candidates,
            "total_candidatos_pilar1": len(inferred_p1_candidates),
            "controles_pilar1_inferidos_automaticamente": [
                {
                    "id_control": item.get("id_control"),
                    "nombre": item.get("nombre"),
                    "tipo": item.get("tipo"),
                    "confianza": item.get("confianza"),
                    "fuentes_evidencia": item.get(
                        "fuentes_evidencia",
                        [],
                    ),
                }
                for item in inferred_p1_checks
            ],
            "total_controles_pilar1_activos": len(inferred_p1_checks),
            "controles_inferidos_automaticamente": [
                {
                    "id_control": item.get("id_control"),
                    "nombre": item.get("nombre"),
                    "tipo": item.get("tipo"),
                }
                for item in inferred_p2_checks
            ],
            "candidatos_pilar2": inferred_p2_candidates,
            "total_candidatos_pilar2": len(inferred_p2_candidates),
            "descubrimiento_pilar2": dict(p2_discovery["estadisticas"]),
            "estrategias_correccion_pilar2": list(
                p2_discovery["estrategias_correccion"]
            ),
            "total_controles_pilar2_activos": len(inferred_p2_checks),
            "total_controles_activos": (
                len(inferred_p1_checks)
                + len(inferred_p2_checks)
            ),
            "entorno_ejecucion": {
                "docker_instalado": _docker_available_on_host(),
                "runtime_principal": detection.runtime.get("nombre"),
                "runtime_modo": detection.runtime.get("modo"),
                "runtime_origen": detection.runtime.get("origen"),
                "preferencia_arranque": detection.runtime.get(
                    "preferencia_arranque"
                ),
                "comando_inicio": detection.runtime.get(
                    "comando_inicio"
                ),
                "comando_inicio_por_so": detection.runtime.get(
                    "comando_inicio_por_so"
                ),
                "base_url": detection.runtime.get("base_url"),
            },
            "plan_ejecucion": {
                "preferencia": str(
                    detection.runtime.get("preferencia_arranque") or "auto"
                ),
                "fallback_local": bool(
                    detection.runtime.get("permitir_fallback_local", True)
                ),
                "principal": {
                    "nombre": detection.runtime.get("nombre"),
                    "modo": detection.runtime.get("modo"),
                    "origen": detection.runtime.get("origen"),
                    "comando_inicio": detection.runtime.get(
                        "comando_inicio"
                    ),
                    "comando_inicio_por_so": detection.runtime.get(
                        "comando_inicio_por_so"
                    ),
                    "directorio_trabajo": detection.runtime.get(
                        "directorio_trabajo"
                    ),
                    "base_url": detection.runtime.get("base_url"),
                },
                "alternativas": [
                    {
                        "nombre": item.get("nombre"),
                        "modo": item.get("modo"),
                        "origen": item.get("origen"),
                        "comando_inicio": item.get("comando_inicio"),
                        "comando_inicio_por_so": item.get(
                            "comando_inicio_por_so"
                        ),
                        "directorio_trabajo": item.get(
                            "directorio_trabajo"
                        ),
                        "base_url": item.get("base_url"),
                    }
                    for item in (
                        detection.runtime.get("alternativas") or []
                    )
                    if isinstance(item, dict)
                ],
            },
        },
    }

    return enrich_profile(profile)


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
