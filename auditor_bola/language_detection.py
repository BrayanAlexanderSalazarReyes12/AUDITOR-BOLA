"""Detección ligera de lenguaje/framework para remediación contextual.

No intenta compilar ni ejecutar el archivo. Combina extensión, nombre y señales
sintácticas para informar al generador de parches qué lenguaje debe respetar.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SourceLanguage:
    language: str
    extension: str
    confidence: str
    frameworks: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


_EXTENSION_LANGUAGE = {
    ".py": "Python",
    ".pyw": "Python",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript/React",
    ".jsx": "JavaScript/React",
    ".cs": "C#",
    ".php": "PHP",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".c": "C",
    ".h": "C/C++ header",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++ header",
    ".swift": "Swift",
    ".dart": "Dart",
    ".scala": "Scala",
    ".groovy": "Groovy",
    ".sh": "Shell",
    ".bash": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".jsp": "JSP/Java",
    ".jspx": "JSP/Java",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".xml": "XML",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".properties": "Java Properties",
    ".env": "Environment configuration",
    ".dockerfile": "Dockerfile",
}

_NAME_LANGUAGE = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
    "gemfile": "Ruby",
    "rakefile": "Ruby",
    "pom.xml": "Maven XML",
    "build.gradle": "Gradle/Groovy",
    "build.gradle.kts": "Gradle/Kotlin",
    "package.json": "JSON",
    "composer.json": "JSON",
    "go.mod": "Go module",
    "cargo.toml": "TOML",
}

_FRAMEWORK_SIGNALS = (
    ("Flask", ("from flask import", "import flask", "flask.", "@app.route", "@app.get(", "@app.post(")),
    ("FastAPI", ("from fastapi import", "import fastapi", "APIRouter(", "FastAPI(")),
    ("Django", ("from django", "import django", "django.", "urlpatterns")),
    ("SQLAlchemy", ("sqlalchemy", "db.session", "declarative_base")),
    ("Spring", ("org.springframework", "@RestController", "@Controller", "@RequestMapping", "@GetMapping", "@PostMapping")),
    ("Jakarta/JAX-RS", ("jakarta.ws.rs", "javax.ws.rs", "@Path(", "@GET", "@POST")),
    ("Servlet/JSP", ("HttpServlet", "doGet(", "doPost(", "<%@ page")),
    ("Express", ("require('express')", 'require("express")', "from 'express'", 'from "express"', "express()", "router.get(", "router.post(")),
    ("NestJS", ("@Controller(", "@Injectable(", "@Get(", "@Post(", "@nestjs/")),
    ("ASP.NET Core", ("Microsoft.AspNetCore", "[ApiController]", "ControllerBase", "MapGet(", "MapPost(")),
    ("Laravel", ("Illuminate\\", "Route::", "extends Controller")),
    ("Symfony", ("Symfony\\Component", "#[Route(", "@Route(")),
    ("Gin", ("github.com/gin-gonic/gin", "gin.Context", "gin.Default(")),
    ("Fiber", ("github.com/gofiber/fiber", "*fiber.Ctx")),
    ("Rails", ("ApplicationController", "before_action", "ActiveRecord::")),
    ("Actix Web", ("actix_web", "#[get(", "#[post(")),
    ("Axum", ("axum::", "Router::new", "State<")),
    ("React", ("from 'react'", 'from "react"', "useState(", "useEffect(")),
    ("Vue", ("from 'vue'", 'from "vue"', "defineComponent(", "<template>")),
)


def detect_source_language(
    relative_path: str,
    text: str = "",
) -> SourceLanguage:
    path = Path(str(relative_path))
    name = path.name.lower()
    suffix = path.suffix.lower()

    language = _NAME_LANGUAGE.get(name)
    evidence: list[str] = []
    confidence = "media"

    if language:
        evidence.append(f"nombre={path.name}")
        confidence = "alta"
    elif suffix in _EXTENSION_LANGUAGE:
        language = _EXTENSION_LANGUAGE[suffix]
        evidence.append(f"extension={suffix}")
        confidence = "alta"
    else:
        stripped = (text or "").lstrip()
        if stripped.startswith("#!") and "python" in stripped.splitlines()[0].lower():
            language = "Python"
            evidence.append("shebang python")
            confidence = "alta"
        elif stripped.startswith("#!") and any(
            shell in stripped.splitlines()[0].lower()
            for shell in ("bash", "/sh", "zsh")
        ):
            language = "Shell"
            evidence.append("shebang shell")
            confidence = "alta"
        elif "<?php" in stripped[:500]:
            language = "PHP"
            evidence.append("marcador <?php")
            confidence = "alta"
        elif "using System;" in text or "namespace " in text and "public class " in text:
            language = "C#"
            evidence.append("sintaxis C#")
        elif "public class " in text and ("import java." in text or "package " in text):
            language = "Java"
            evidence.append("sintaxis Java")
        elif "def " in text and ("import " in text or "from " in text):
            language = "Python"
            evidence.append("sintaxis Python")
        elif "function " in text or "const " in text or "let " in text:
            language = "JavaScript"
            evidence.append("sintaxis JavaScript")
        else:
            language = "Texto/configuración"
            evidence.append("sin firma de lenguaje concluyente")
            confidence = "baja"

    frameworks: list[str] = []
    haystack = text or ""
    for framework, signals in _FRAMEWORK_SIGNALS:
        if any(signal in haystack for signal in signals):
            frameworks.append(framework)

    return SourceLanguage(
        language=language,
        extension=suffix,
        confidence=confidence,
        frameworks=frameworks,
        evidence=evidence,
    )


def detect_language_context(
    source_relative: str,
    source_text: str,
    related_sources: dict[str, str] | None = None,
) -> dict:
    principal = detect_source_language(source_relative, source_text)
    related: dict[str, dict] = {}
    for relative, text in (related_sources or {}).items():
        related[str(relative)] = detect_source_language(
            str(relative),
            str(text),
        ).as_dict()

    frameworks = list(principal.frameworks)
    for item in related.values():
        for framework in item.get("frameworks") or []:
            if framework not in frameworks:
                frameworks.append(framework)

    return {
        "principal": principal.as_dict(),
        "frameworks_contexto": frameworks,
        "archivos_relacionados": related,
    }


# Cambios de estos tipos alteran código/configuración que un proceso en
# ejecución puede haber cargado ya. Aegis no debe verificar un parche contra
# el proceso anterior.
_RESTART_EXTENSIONS = {
    ".py", ".pyw", ".java", ".kt", ".kts", ".js", ".mjs", ".cjs",
    ".ts", ".tsx", ".jsx", ".cs", ".php", ".go", ".rs", ".rb",
    ".c", ".cc", ".cpp", ".cxx", ".swift", ".dart", ".scala",
    ".groovy", ".jsp", ".jspx", ".vue", ".svelte",
    ".xml", ".json", ".yaml", ".yml", ".toml", ".properties", ".env",
}
_RESTART_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "compose.yml", "compose.yaml", "pom.xml", "build.gradle",
    "build.gradle.kts", "package.json",
}


def requires_service_restart(relative_paths: list[str] | tuple[str, ...]) -> bool:
    """Indica si el parche debe cargarse reiniciando/recargando el servicio."""
    for raw in relative_paths:
        path = Path(str(raw))
        if path.name.lower() in _RESTART_NAMES:
            return True
        if path.suffix.lower() in _RESTART_EXTENSIONS:
            return True
    return False
