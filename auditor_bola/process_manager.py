"""Gestor multiplataforma del proceso local del sistema objetivo."""

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
    """Arranca objetivos heterogéneos sin acoplar el Auditor a un framework.

    Modos:
    - process/command: proceso persistente administrado con Popen.
    - service: comandos de control que terminan, pero dejan un servicio activo
      (por ejemplo: docker compose up -d, systemctl, XAMPP).
    - external: el objetivo ya está administrado fuera del Auditor.
    """

    def __init__(self, target_root: str | Path, runtime: RuntimeConfig):
        self.root = Path(target_root).resolve()
        self.runtime = runtime
        self.process: subprocess.Popen | None = None
        self._service_running = False

    def _modo(self) -> str:
        mode = (self.runtime.modo or "process").strip().lower()
        if mode == "command":
            # Compatibilidad con perfiles experimentales anteriores.
            return "process"
        if mode not in {"process", "service", "external"}:
            raise ValueError(
                f"runtime.modo no soportado: {self.runtime.modo!r}; "
                "use process, service o external"
            )
        return mode

    @staticmethod
    def _platform_key() -> str:
        if os.name == "nt":
            return "windows"
        if sys.platform == "darwin":
            return "macos"
        return "linux"

    def _command_for(self, action: str) -> list[str]:
        """Selecciona comando común o override específico del SO."""
        if action not in {"inicio", "detener", "reinicio"}:
            raise ValueError(f"acción de runtime no soportada: {action}")

        base = list(getattr(self.runtime, f"comando_{action}") or [])
        per_os = dict(
            getattr(self.runtime, f"comando_{action}_por_so") or {}
        )
        platform_key = self._platform_key()

        chosen = per_os.get(platform_key)
        if chosen is None:
            chosen = per_os.get("default")
        if chosen is None:
            chosen = base

        return [str(item) for item in chosen]

    def is_running(self) -> bool:
        mode = self._modo()
        if mode == "service":
            return self._service_running
        if mode == "external":
            return False
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
        """Busca un launcher dentro del propio proyecto."""
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

                for variant_suffix in {
                    extension,
                    extension.lower(),
                    extension.upper(),
                }:
                    variant = Path(str(candidate) + variant_suffix)
                    if variant.exists() and variant.is_file():
                        return variant

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
                f"No se encontró el comando o archivo '{requested}'. "
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
                    "El objetivo requiere PowerShell y no está disponible en PATH.",
                    "pwsh",
                )
            command = [powershell, "-NoProfile"]
            if os.name == "nt":
                command.extend(["-ExecutionPolicy", "Bypass"])
            command.extend(["-File", resolved, *args])
            return command

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

    def _resolver_comando(
        self,
        cwd: Path,
        env: dict[str, str],
        raw: list[str] | None = None,
    ) -> list[str]:
        """Resuelve un comando de perfil de forma portable.

        Si raw no se pasa, se usa el comando de inicio aplicable al SO actual.
        """
        raw = list(raw if raw is not None else self._command_for("inicio"))
        raw = [str(item) for item in raw]

        if not raw:
            raise RuntimeError(
                "el perfil no declara un comando aplicable al sistema operativo "
                f"actual ({self._platform_key()})"
            )

        requested = raw[0]
        resolved = self._resolver_ruta_inicial(requested, cwd, env)

        if Path(requested).suffix == "" and self._which(requested, env):
            suffix = Path(resolved).suffix.lower()
            if not (os.name == "nt" and suffix in {".cmd", ".bat"}):
                return [resolved, *raw[1:]]

        return self._resolver_interprete(resolved, raw[1:], env)

    def _context(self) -> tuple[Path, dict[str, str]]:
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
        return cwd, env

    def _run_control_command(
        self,
        raw: list[str],
        *,
        action_name: str,
    ) -> None:
        cwd, env = self._context()
        command = self._resolver_comando(cwd, env, raw=raw)

        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if len(detail) > 1000:
                detail = detail[-1000:]
            raise RuntimeError(
                f"No se pudo {action_name} el objetivo "
                f"(código {completed.returncode}). {detail}"
            )

    def start(self) -> None:
        mode = self._modo()

        if mode == "external":
            raise RuntimeError(
                "Este perfil declara runtime.modo='external'. "
                "El objetivo debe iniciarse fuera del Auditor; después puede "
                "ejecutarse el diagnóstico contra base_url."
            )

        if self.is_running():
            return

        start_command = self._command_for("inicio")
        if not start_command:
            raise RuntimeError(
                "el perfil no declara comando de inicio para "
                f"{self._platform_key()}"
            )

        if mode == "service":
            self._run_control_command(
                start_command,
                action_name="iniciar",
            )
            self._service_running = True
            time.sleep(self.runtime.espera_inicio)
            return

        cwd, env = self._context()
        command = self._resolver_comando(cwd, env, raw=start_command)

        try:
            self.process = subprocess.Popen(
                command,
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
                    f"Comando resuelto: {command[0]!r}. "
                    "Verifica instalación, PATH y runtime requerido."
                ),
                command[0],
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
        mode = self._modo()

        if mode == "external":
            return

        stop_command = self._command_for("detener")

        if mode == "service":
            if stop_command:
                self._run_control_command(
                    stop_command,
                    action_name="detener",
                )
            self._service_running = False
            return

        if self.is_running():
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None

        if stop_command:
            self._run_control_command(
                stop_command,
                action_name="detener",
            )

    def restart(self) -> None:
        mode = self._modo()

        if mode == "external":
            raise RuntimeError(
                "Este perfil usa runtime.modo='external'; "
                "el reinicio debe administrarse fuera del Auditor."
            )

        restart_command = self._command_for("reinicio")

        if mode == "service" and restart_command:
            self._run_control_command(
                restart_command,
                action_name="reiniciar",
            )
            self._service_running = True
            time.sleep(self.runtime.espera_inicio)
            return

        self.stop()
        self.start()
