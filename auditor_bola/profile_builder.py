"""Detección genérica de proyectos y construcción de perfiles borrador."""

from __future__ import annotations

import json
import re
import unicodedata
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
}

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
            "notes": list(self.notes),
        }


def _read_text(path: Path, limit: int = 500_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _iter_source_files(root: Path, max_files: int = 4000):
    count = 0
    for path in root.rglob("*"):
        if count >= max_files:
            break
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in IGNORE_DIRS for part in relative.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
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


def _extract_routes(root: Path) -> list[DetectedRoute]:
    found: dict[tuple[str, str, str], DetectedRoute] = {}

    patterns = [
        (
            "flask",
            re.compile(
                r"@(?:app|bp|\w+)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",
                re.I,
            ),
            lambda m: (m.group(1).upper(), m.group(2)),
        ),
        (
            "flask",
            re.compile(
                r"@(?:app|bp|\w+)\.route\(\s*['\"]([^'\"]+)['\"](?:\s*,\s*methods\s*=\s*\[([^\]]+)\])?",
                re.I,
            ),
            lambda m: (
                (re.search(r"['\"]([A-Z]+)['\"]", m.group(2) or "") or [None, "GET"])[1],
                m.group(1),
            ),
        ),
        (
            "express",
            re.compile(
                r"(?:app|router)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",
                re.I,
            ),
            lambda m: (m.group(1).upper(), m.group(2)),
        ),
        (
            "servlet",
            re.compile(r"@WebServlet\(\s*['\"]([^'\"]+)['\"]"),
            lambda m: ("ANY", m.group(1)),
        ),
        (
            "spring",
            re.compile(
                r"@(Get|Post|Put|Patch|Delete)Mapping\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"]",
                re.I,
            ),
            lambda m: (m.group(1).upper(), m.group(2)),
        ),
        (
            "django",
            re.compile(r"path\(\s*['\"]([^'\"]+)['\"]"),
            lambda m: ("ANY", "/" + m.group(1).lstrip("/")),
        ),
        (
            "laravel",
            re.compile(
                r"Route::(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]",
                re.I,
            ),
            lambda m: (m.group(1).upper(), m.group(2)),
        ),
        (
            "aspnet-core",
            re.compile(
                r"\[Http(Get|Post|Put|Patch|Delete)(?:\(\s*['\"]([^'\"]*)['\"]\s*\))?\]",
                re.I,
            ),
            lambda m: (m.group(1).upper(), m.group(2) or "/"),
        ),
        (
            "nestjs",
            re.compile(
                r"@(Get|Post|Put|Patch|Delete)\(\s*['\"]([^'\"]*)['\"]\s*\)",
                re.I,
            ),
            lambda m: (m.group(1).upper(), m.group(2) or "/"),
        ),
        (
            "go-router",
            re.compile(
                r"\.(GET|POST|PUT|PATCH|DELETE)\(\s*['\"]([^'\"]+)['\"]",
            ),
            lambda m: (m.group(1).upper(), m.group(2)),
        ),
        (
            "rails",
            re.compile(
                r"^\s*(get|post|put|patch|delete)\s+['\"]([^'\"]+)['\"]",
                re.I | re.M,
            ),
            lambda m: (m.group(1).upper(), m.group(2)),
        ),
    ]

    for path, relative in _iter_source_files(root):
        text = _read_text(path)
        if not text:
            continue
        source = relative.as_posix()
        for framework, pattern, mapper in patterns:
            for match in pattern.finditer(text):
                try:
                    method, route = mapper(match)
                except Exception:
                    continue
                route = str(route).strip()
                if not route.startswith("/"):
                    route = "/" + route
                key = (method.upper(), route, source)
                found[key] = DetectedRoute(
                    method=method.upper(),
                    path=route,
                    source=source,
                    framework=framework,
                )

    return sorted(
        found.values(),
        key=lambda item: (item.path, item.method, item.source),
    )[:300]


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
    )
    detection.notes.append(f"Base URL sugerida: {base_url}")
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

    profile = {
        "sistema": _slug(name),
        "version_objetivo": version or "1.0.0",
        "base_url": (base_url or suggested_url).rstrip("/"),
        "cuentas": [],
        "roles_privilegiados": [],
        "runtime": detection.runtime,
        "endpoints": [],
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
