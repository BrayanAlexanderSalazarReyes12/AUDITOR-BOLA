"""Gestor genérico del proceso local del sistema objetivo."""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
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

    def _resolver_comando(self, cwd: Path, env: dict[str, str]) -> list[str]:
        """Resuelve de forma portable el ejecutable declarado por el perfil.

        En Windows herramientas como npm/npx/yarn suelen ser wrappers .cmd.
        CreateProcess no siempre los resuelve correctamente cuando Popen recibe
        una lista. En ese caso se invoca cmd.exe explícitamente, sin activar
        shell=True para el resto de plataformas/comandos.
        """
        raw = [str(item) for item in self.runtime.comando_inicio]
        if not raw:
            raise RuntimeError(
                "el perfil no declara runtime.comando_inicio"
            )

        requested = raw[0]
        requested_path = Path(requested)

        resolved: str | None = None

        if requested_path.is_absolute():
            if requested_path.exists():
                resolved = str(requested_path)
        elif requested_path.parent != Path("."):
            candidate = (cwd / requested_path).resolve()
            if candidate.exists():
                resolved = str(candidate)
        else:
            resolved = shutil.which(requested, path=env.get("PATH"))

        if not resolved:
            raise FileNotFoundError(
                errno.ENOENT,
                (
                    f"No se encontró el comando de inicio '{requested}'. "
                    "Verifica que la herramienta esté instalada y disponible "
                    "en PATH."
                ),
                requested,
            )

        resolved_args = [resolved, *raw[1:]]

        if os.name == "nt" and Path(resolved).suffix.lower() in {".cmd", ".bat"}:
            comspec = env.get("COMSPEC") or shutil.which(
                "cmd.exe", path=env.get("PATH")
            )
            if not comspec:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "No se encontró cmd.exe para ejecutar el wrapper de Windows.",
                    "cmd.exe",
                )

            # Un único argumento después de /c conserva correctamente espacios
            # y comillas de rutas/argumentos mediante las reglas de Windows.
            command_line = subprocess.list2cmdline(resolved_args)
            return [comspec, "/d", "/s", "/c", command_line]

        return resolved_args

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
                    f"No se pudo iniciar el objetivo. Comando resuelto: "
                    f"{comando[0]!r}. Verifica instalación y PATH."
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
