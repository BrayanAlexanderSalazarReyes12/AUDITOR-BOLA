"""Validación técnica y QA posterior a parches.

El módulo ejecuta únicamente validadores y comandos de build/test reconocidos.
No instala dependencias, no ejecuta migraciones ni comandos arbitrarios del
proyecto. Si no existe un plan seguro, lo informa como NO_APLICA/NO_DISPONIBLE
sin inventar éxito.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class ValidationStep:
    nombre: str
    estado: str  # OK | FAILED | NO_APLICA | NO_DISPONIBLE
    comando: list[str] = field(default_factory=list)
    detalle: str = ""
    returncode: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectValidationReport:
    archivo: str
    sintaxis: ValidationStep
    build: ValidationStep
    tests: ValidationStep
    tecnico_ok: bool
    build_aplicable: bool
    tests_aplicables: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _hidden_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs: dict = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)
    }
    startupinfo_factory = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_factory is not None:
        info = startupinfo_factory()
        info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = info
    return kwargs


def _project_python(root: Path) -> str | None:
    candidates = (
        root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
    )
    for item in candidates:
        if item.is_file():
            return str(item.resolve())
    for name in ("python", "python3"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    if not getattr(sys, "frozen", False) and sys.executable:
        return sys.executable
    return None


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    nombre: str,
) -> ValidationStep:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            **_hidden_kwargs(),
        )
    except FileNotFoundError as exc:
        return ValidationStep(
            nombre=nombre,
            estado="NO_DISPONIBLE",
            comando=command,
            detalle=str(exc),
        )
    except subprocess.TimeoutExpired as exc:
        return ValidationStep(
            nombre=nombre,
            estado="FAILED",
            comando=command,
            detalle=f"timeout de {timeout}s: {exc}",
        )
    except OSError as exc:
        return ValidationStep(
            nombre=nombre,
            estado="FAILED",
            comando=command,
            detalle=str(exc),
        )

    output = (completed.stderr or completed.stdout or "").strip()
    if len(output) > 6000:
        output = output[-6000:]
    return ValidationStep(
        nombre=nombre,
        estado="OK" if completed.returncode == 0 else "FAILED",
        comando=command,
        detalle=output,
        returncode=completed.returncode,
    )


def _syntax_check(root: Path, relative: str) -> ValidationStep:
    path = (root / relative).resolve()
    if not path.is_file():
        return ValidationStep(
            nombre="sintaxis",
            estado="FAILED",
            detalle=f"archivo inexistente: {relative}",
        )
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ValidationStep(
            nombre="sintaxis",
            estado="FAILED",
            detalle=str(exc),
        )

    suffix = path.suffix.lower()
    try:
        if suffix == ".py":
            ast.parse(text)
        elif suffix == ".json":
            json.loads(text)
        elif suffix in {".xml", ".jspx"}:
            ET.fromstring(text)
        else:
            return ValidationStep(
                nombre="sintaxis",
                estado="NO_APLICA",
                detalle=(
                    "No hay parser estándar seguro para este tipo; "
                    "se delega al build del proyecto."
                ),
            )
    except (SyntaxError, json.JSONDecodeError, ET.ParseError) as exc:
        return ValidationStep(
            nombre="sintaxis",
            estado="FAILED",
            detalle=str(exc),
        )

    return ValidationStep(
        nombre="sintaxis",
        estado="OK",
        detalle=f"{suffix or 'archivo'} válido",
    )


def _local_wrapper(root: Path, unix_name: str, win_name: str) -> list[str] | None:
    if os.name == "nt":
        path = root / win_name
        if path.is_file():
            return [str(path.resolve())]
        return None
    path = root / unix_name
    if not path.is_file():
        return None
    if os.access(path, os.X_OK):
        return [str(path.resolve())]
    shell = shutil.which("sh")
    return [shell, str(path.resolve())] if shell else None


def _node_scripts(root: Path) -> dict:
    package = root / "package.json"
    if not package.is_file():
        return {}
    try:
        data = json.loads(package.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts")
    return scripts if isinstance(scripts, dict) else {}


def _detect_build(root: Path) -> tuple[list[str] | None, bool]:
    if (root / "pom.xml").is_file():
        wrapper = _local_wrapper(root, "mvnw", "mvnw.cmd")
        if wrapper:
            return [*wrapper, "-q", "-DskipTests", "package"], True
        mvn = shutil.which("mvn")
        return ([mvn, "-q", "-DskipTests", "package"] if mvn else None, True)

    if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        wrapper = _local_wrapper(root, "gradlew", "gradlew.bat")
        if wrapper:
            return [*wrapper, "assemble"], True
        gradle = shutil.which("gradle")
        return ([gradle, "assemble"] if gradle else None, True)

    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        dotnet = shutil.which("dotnet")
        return ([dotnet, "build", "--nologo"] if dotnet else None, True)

    if (root / "go.mod").is_file():
        go = shutil.which("go")
        return ([go, "test", "-run", "^$", "./..."] if go else None, True)

    scripts = _node_scripts(root)
    if "build" in scripts:
        npm = shutil.which("npm")
        return ([npm, "run", "build", "--if-present"] if npm else None, True)

    # Python y configuraciones interpretadas no tienen fase build obligatoria.
    return None, False


def _detect_tests(root: Path) -> tuple[list[str] | None, bool]:
    if (root / "pom.xml").is_file():
        wrapper = _local_wrapper(root, "mvnw", "mvnw.cmd")
        if wrapper:
            return [*wrapper, "-q", "test"], True
        mvn = shutil.which("mvn")
        return ([mvn, "-q", "test"] if mvn else None, True)

    if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
        wrapper = _local_wrapper(root, "gradlew", "gradlew.bat")
        if wrapper:
            return [*wrapper, "test"], True
        gradle = shutil.which("gradle")
        return ([gradle, "test"] if gradle else None, True)

    if any(root.glob("*.sln")) or any(root.glob("*.csproj")):
        dotnet = shutil.which("dotnet")
        return ([dotnet, "test", "--nologo"] if dotnet else None, True)

    if (root / "go.mod").is_file():
        go = shutil.which("go")
        return ([go, "test", "./..."] if go else None, True)

    scripts = _node_scripts(root)
    script = str(scripts.get("test") or "").strip()
    if script and "no test specified" not in script.lower():
        npm = shutil.which("npm")
        return ([npm, "test", "--", "--runInBand"] if npm else None, True)

    has_pytests = (
        (root / "tests").is_dir()
        or (root / "pytest.ini").is_file()
        or (root / "pyproject.toml").is_file()
    )
    if has_pytests:
        python = _project_python(root)
        if python:
            return [python, "-m", "pytest", "-q"], True
        return None, True

    return None, False


def validate_project_after_patch(
    target_root: str | Path,
    relative_file: str,
    *,
    build_timeout: int = 180,
    test_timeout: int = 240,
) -> ProjectValidationReport:
    """Ejecuta validación sintáctica, build conocido y tests conocidos."""
    root = Path(target_root).resolve()
    syntax = _syntax_check(root, relative_file)

    build_cmd, build_applicable = _detect_build(root)
    if build_applicable and not build_cmd:
        build = ValidationStep(
            nombre="build",
            estado="NO_DISPONIBLE",
            detalle="Se detectó un sistema de build, pero su runtime no está disponible.",
        )
    elif build_cmd:
        build = _run(
            build_cmd,
            cwd=root,
            timeout=build_timeout,
            nombre="build",
        )
    else:
        build = ValidationStep(
            nombre="build",
            estado="NO_APLICA",
            detalle="El proyecto no declara una fase de build reconocida.",
        )

    test_cmd, tests_applicable = _detect_tests(root)
    if tests_applicable and not test_cmd:
        tests = ValidationStep(
            nombre="tests",
            estado="NO_DISPONIBLE",
            detalle="Se detectaron pruebas, pero su runtime no está disponible.",
        )
    elif test_cmd:
        tests = _run(
            test_cmd,
            cwd=root,
            timeout=test_timeout,
            nombre="tests",
        )
    else:
        tests = ValidationStep(
            nombre="tests",
            estado="NO_APLICA",
            detalle="No se detectó una suite de pruebas ejecutable de forma segura.",
        )

    syntax_ok = syntax.estado in {"OK", "NO_APLICA"}
    build_ok = (
        build.estado in {"OK", "NO_APLICA"}
        if not build_applicable
        else build.estado == "OK"
    )
    tests_ok = (
        tests.estado in {"OK", "NO_APLICA"}
        if not tests_applicable
        else tests.estado == "OK"
    )
    return ProjectValidationReport(
        archivo=relative_file,
        sintaxis=syntax,
        build=build,
        tests=tests,
        tecnico_ok=bool(syntax_ok and build_ok and tests_ok),
        build_aplicable=build_applicable,
        tests_aplicables=tests_applicable,
    )
