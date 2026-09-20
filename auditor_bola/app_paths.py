"""Rutas de recursos y datos persistentes de Aegis Auditor.

En desarrollo se conserva el comportamiento del repositorio. En la versión
empaquetada (.exe), los datos escribibles viven en el perfil del usuario y los
recursos de solo lectura se resuelven desde el bundle de PyInstaller.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_NAME = "AegisAuditor"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return project_root()


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def user_data_root() -> Path:
    override = os.getenv("AEGIS_DATA_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return (Path(base) / APP_NAME).resolve()
        return (Path.home() / "AppData" / "Local" / APP_NAME).resolve()

    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / APP_NAME
        ).resolve()

    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        return (Path(xdg) / APP_NAME).expanduser().resolve()
    return (Path.home() / ".local" / "share" / APP_NAME).resolve()


def runtime_data_root() -> Path:
    """Dev: repositorio. Ejecutable: carpeta persistente del usuario."""
    return user_data_root() if is_frozen() else project_root()


def default_config_dir() -> Path:
    return runtime_data_root() / "config"


def default_evidence_dir() -> Path:
    return runtime_data_root() / "evidencias"


def default_ai_config_path() -> Path:
    """Configuración local del proveedor IA de Aegis."""
    return default_config_dir() / "ai-provider.json"


def default_recipe_dir() -> Path:
    return runtime_data_root() / "recetas"


def default_article_dir() -> Path:
    return runtime_data_root() / "articulo"


def _copy_if_missing(source: Path, destination: Path) -> None:
    if destination.exists() or not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def bootstrap_user_data() -> Path:
    """Prepara carpetas persistentes y plantillas cuando corre como .exe."""
    root = runtime_data_root()
    for folder in (
        default_config_dir(),
        default_evidence_dir(),
        default_recipe_dir(),
        default_recipe_dir() / "conocimiento",
        default_article_dir(),
    ):
        folder.mkdir(parents=True, exist_ok=True)

    if is_frozen():
        _copy_if_missing(
            resource_path("config", "plantilla.json"),
            default_config_dir() / "plantilla.json",
        )
        _copy_if_missing(
            resource_path("docs", "REQUISITOS_USO.md"),
            root / "docs" / "REQUISITOS_USO.md",
        )
        _copy_if_missing(
            resource_path("docs", "ARQUITECTURA_DOS_PILARES.md"),
            root / "docs" / "ARQUITECTURA_DOS_PILARES.md",
        )

    return root


def configure_packaged_environment() -> Path:
    root = bootstrap_user_data()

    if is_frozen():
        os.environ.setdefault(
            "AUDITOR_RECIPE_LIBRARY",
            str(default_recipe_dir()),
        )
        os.environ.setdefault(
            "AUDITOR_REMEDIATION_KNOWLEDGE",
            str(default_recipe_dir() / "conocimiento"),
        )

    return root
