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
from typing import Any, Callable


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