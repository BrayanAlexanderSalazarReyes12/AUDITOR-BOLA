"""Gestor genérico del proceso local del sistema objetivo."""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import RuntimeConfig


class LocalTargetProcess:
    def __init__(self, target_root: str | Path, runtime: RuntimeConfig):
        self.root = Path(target_root).resolve()
        self.runtime = runtime
        self.process: subprocess.Popen | None = None

    def is_running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    @staticmethod
    def _which(nombre: str, env: dict[str, str]) -> str | None:
        return shutil.which(nombre, path=env.get("PATH"))

    @staticmethod
    def _candidato_local(
        requested: str,
        cwd: Path,
        env: dict[str, str],
    ) -> Path | None:
        """Busca un launcher dentro del propio proyecto.

        Esto cubre, entre otros, mvnw, mvnw.cmd, gradlew, gradlew.bat y
        scripts que el proyecto incluya en su raíz.
        """
        candidate = (cwd / requested).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate

        if os.name == "nt" and not candidate.suffix:
            pathext = env.get(
                "PATHEXT",
                ".COM;.EXE;.BAT;.CMD;.PS1;.PY",
            )
            for extension in pathext.split(";"):
                extension = extension.strip()
                if not extension:
                    continue
                variant = Path(str(candidate) + extension.lower())
                if variant.exists() and variant.is_file():
                    return variant
                variant_upper = Path(str(candidate) + extension.upper())
                if variant_upper.exists() and variant_upper.is_file():
                    return variant_upper

        return None

    def _resolver_ruta_inicial(
        self,
        requested: str,
        cwd: Path,
        env: dict[str, str],
    ) -> str:
        requested_path = Path(requested)

        if requested_path.is_absolute():
            if requested_path.exists() and requested_path.is_file():
                return str(requested_path)
        elif requested_path.parent != Path("."):
            candidate = (cwd / requested_path).resolve()
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        else:
            local = self._candidato_local(requested, cwd, env)
            if local is not None:
                return str(local)

            resolved = self._which(requested, env)
            if resolved:
                return resolved

        raise FileNotFoundError(
            errno.ENOENT,
            (
                f"No se encontró el comando o archivo de inicio '{requested}'. "
                "Verifica que exista en el proyecto o que su runtime esté "
                "instalado y disponible en PATH."
            ),
            requested,
        )

    def _resolver_interprete(
        self,
        resolved: str,
        args: list[str],
        env: dict[str, str],
    ) -> list[str]:
        """Convierte scripts/launchers a una invocación portable."""
        suffix = Path(resolved).suffix.lower()

        if os.name == "nt" and suffix in {".cmd", ".bat"}:
            comspec = env.get("COMSPEC") or self._which("cmd.exe", env)
            if not comspec:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "No se encontró cmd.exe para ejecutar un wrapper de Windows.",
                    "cmd.exe",
                )
            command_line = subprocess.list2cmdline([resolved, *args])
            return [comspec, "/d", "/s", "/c", command_line]

        if suffix == ".ps1":
            powershell = self._which("pwsh", env) or self._which(
                "powershell.exe" if os.name == "nt" else "powershell",
                env,
            )
            if not powershell:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "El objetivo requiere PowerShell (pwsh/powershell) y no está en PATH.",
                    "pwsh",
                )
            return [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                resolved,
                *args,
            ]

        if suffix == ".py":
            return [sys.executable, resolved, *args]

        if suffix == ".sh":
            shell = self._which("bash", env) or self._which("sh", env)
            if not shell:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "El objetivo requiere bash/sh y no está disponible en PATH.",
                    "bash",
                )
            return [shell, resolved, *args]

        if suffix == ".jar":
            java = self._which("java", env)
            if not java:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "El objetivo requiere Java y 'java' no está disponible en PATH.",
                    "java",
                )
            return [java, "-jar", resolved, *args]

        if suffix in {".js", ".mjs", ".cjs"}:
            node = self._which("node", env)
            if not node:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "El objetivo requiere Node.js y 'node' no está disponible en PATH.",
                    "node",
                )
            return [node, resolved, *args]

        return [resolved, *args]

    def _resolver_comando(self, cwd: Path, env: dict[str, str]) -> list[str]:
        """Resuelve cualquier comando declarado por el perfil.

        Casos cubiertos:
        - ejecutables instalados y disponibles en PATH;
        - ejecutables/runners incluidos dentro del proyecto;
        - wrappers .cmd/.bat de Windows (npm, npx, yarn, mvnw, gradlew);
        - scripts .py, .ps1 y .sh;
        - archivos .jar;
        - scripts Node .js/.mjs/.cjs.

        Si el perfil ya declara un runtime explícito, por ejemplo
        ["python", "run.py"] o ["java", "-jar", "app.jar"], se respeta tal cual.
        """
        raw = [str(item) for item in self.runtime.comando_inicio]
        if not raw:
            raise RuntimeError(
                "el perfil no declara runtime.comando_inicio"
            )

        requested = raw[0]
        resolved = self._resolver_ruta_inicial(requested, cwd, env)

        # Cuando el primer elemento ya es un runtime instalado (python, java,
        # node, dotnet, php, ruby, go, etc.), no inferimos nada sobre los
        # argumentos posteriores: simplemente ejecutamos el runtime resuelto.
        if Path(requested).suffix == "" and self._which(requested, env):
            suffix = Path(resolved).suffix.lower()
            if not (os.name == "nt" and suffix in {".cmd", ".bat"}):
                return [resolved, *raw[1:]]

        return self._resolver_interprete(resolved, raw[1:], env)

    def start(self) -> None:
        if self.is_running():
            return
        if not self.runtime.comando_inicio:
            raise RuntimeError(
                "el perfil no declara runtime.comando_inicio"
            )

        cwd = (self.root / self.runtime.directorio_trabajo).resolve()
        if cwd != self.root and self.root not in cwd.parents:
            raise ValueError("directorio_trabajo fuera del target_root")
        if not cwd.exists() or not cwd.is_dir():
            raise FileNotFoundError(
                errno.ENOENT,
                f"No existe el directorio de trabajo del objetivo: {cwd}",
                str(cwd),
            )

        env = os.environ.copy()
        env.update(self.runtime.variables)

        comando = self._resolver_comando(cwd, env)

        try:
            self.process = subprocess.Popen(
                comando,
                cwd=cwd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                errno.ENOENT,
                (
                    "No se pudo iniciar el objetivo. "
                    f"Comando resuelto: {comando[0]!r}. "
                    "Verifica instalación, PATH y runtime requerido."
                ),
                comando[0],
            ) from exc

        time.sleep(self.runtime.espera_inicio)
        if self.process.poll() is not None:
            return_code = self.process.returncode
            self.process = None
            raise RuntimeError(
                "el sistema objetivo terminó durante el arranque "
                f"(código {return_code}). Ejecuta el comando manualmente "
                "en la carpeta del proyecto para ver su salida."
            )

    def stop(self) -> None:
        if not self.is_running():
            self.process = None
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process = None

    def restart(self) -> None:
        self.stop()
        self.start()
