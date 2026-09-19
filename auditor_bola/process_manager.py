"""Gestor multiplataforma del proceso local del sistema objetivo."""

from __future__ import annotations

import errno
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

from .config import RuntimeConfig


def _is_windows() -> bool:
    """Aísla la detección de Windows para permitir pruebas portables."""
    return os.name == "nt"


class LocalTargetProcess:
    """Arranca objetivos heterogéneos sin acoplar el Auditor a un framework.

    Modos:
    - process/command: proceso persistente administrado con Popen.
    - service: comandos de control que terminan, pero dejan un servicio activo.
    - external: el objetivo ya está administrado fuera del Auditor.

    También puede ejecutar comandos declarativos de preparación antes del
    primer arranque administrado, por ejemplo instalación de dependencias.
    """

    def __init__(self, target_root: str | Path, runtime: RuntimeConfig):
        self.root = Path(target_root).resolve()
        self.runtime = runtime
        self.process: subprocess.Popen | None = None
        self._service_running = False
        self._prepared = False
        self._output: BinaryIO | None = None

    def _modo(self) -> str:
        mode = (self.runtime.modo or "process").strip().lower()
        if mode == "command":
            return "process"
        if mode not in {"process", "service", "external"}:
            raise ValueError(
                f"runtime.modo no soportado: {self.runtime.modo!r}; "
                "use process, service o external"
            )
        return mode

    @staticmethod
    def _platform_key() -> str:
        if _is_windows():
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

    def _preparation_commands(self) -> list[list[str]]:
        base = list(self.runtime.comandos_preparacion or [])
        per_os = dict(self.runtime.comandos_preparacion_por_so or {})
        platform_key = self._platform_key()

        chosen = per_os.get(platform_key)
        if chosen is None:
            chosen = per_os.get("default")
        if chosen is None:
            chosen = base

        return [
            [str(item) for item in command]
            for command in chosen
            if command
        ]

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
        candidate = (cwd / requested).resolve()
        if candidate.exists() and candidate.is_file():
            return candidate

        if _is_windows() and not candidate.suffix:
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
        suffix = Path(resolved).suffix.lower()

        if _is_windows() and suffix in {".cmd", ".bat"}:
            comspec = env.get("COMSPEC") or self._which("cmd.exe", env)
            if not comspec:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "No se encontró cmd.exe para ejecutar un wrapper de Windows.",
                    "cmd.exe",
                )

            # No construir previamente una cadena con list2cmdline: al pasar
            # esa cadena nuevamente a subprocess las comillas internas pueden
            # llegar a cmd.exe como \"...\". Usar CALL deja que subprocess
            # haga una única capa de quoting y permite rutas con espacios.
            return [
                comspec,
                "/d",
                "/s",
                "/c",
                "call",
                resolved,
                *args,
            ]

        if suffix == ".ps1":
            powershell = self._which("pwsh", env) or self._which(
                "powershell.exe" if _is_windows() else "powershell",
                env,
            )
            if not powershell:
                raise FileNotFoundError(
                    errno.ENOENT,
                    "El objetivo requiere PowerShell y no está disponible en PATH.",
                    "pwsh",
                )
            command = [powershell, "-NoProfile"]
            if _is_windows():
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
            if not (_is_windows() and suffix in {".cmd", ".bat"}):
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
            timeout=300,
        )

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if len(detail) > 4000:
                detail = detail[-4000:]
            raise RuntimeError(
                f"No se pudo {action_name} el objetivo "
                f"(código {completed.returncode}).\n\n{detail}"
            )

    def _prepare_if_needed(self) -> None:
        if not self.runtime.preparar_automaticamente or self._prepared:
            return

        commands = self._preparation_commands()
        if not commands:
            self._prepared = True
            return

        total = len(commands)
        for index, command in enumerate(commands, start=1):
            self._run_control_command(
                command,
                action_name=f"preparar ({index}/{total})",
            )

        self._prepared = True

    def _reset_output_buffer(self) -> None:
        self._close_output_buffer()
        self._output = tempfile.TemporaryFile(mode="w+b")

    def _close_output_buffer(self) -> None:
        if self._output is not None:
            try:
                self._output.close()
            finally:
                self._output = None

    def runtime_output_tail(self, max_bytes: int = 6000) -> str:
        if self._output is None:
            return ""

        try:
            self._output.flush()
            end = self._output.seek(0, os.SEEK_END)
            start = max(0, end - max_bytes)
            self._output.seek(start)
            raw = self._output.read()
            self._output.seek(0, os.SEEK_END)
        except (OSError, ValueError):
            return ""

        return raw.decode("utf-8", errors="replace").strip()

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

        self._prepare_if_needed()

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

        self._reset_output_buffer()

        try:
            popen_kwargs = {
                "cwd": cwd,
                "env": env,
                "stdout": self._output,
                "stderr": subprocess.STDOUT,
            }

            # Crear un grupo/sesión independiente permite detener también los
            # procesos hijo que lance el runtime (npm -> node, mvn -> java,
            # scripts -> servidores, etc.).
            if _is_windows():
                popen_kwargs["creationflags"] = getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                )
            else:
                popen_kwargs["start_new_session"] = True

            self.process = subprocess.Popen(
                command,
                **popen_kwargs,
            )
        except FileNotFoundError as exc:
            self._close_output_buffer()
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
            detail = self.runtime_output_tail()
            self.process = None
            self._close_output_buffer()

            message = (
                "el sistema objetivo terminó durante el arranque "
                f"(código {return_code})."
            )
            if detail:
                message += f"\n\nSalida del proceso:\n{detail}"
            else:
                message += (
                    "\nNo produjo salida. Verifica el comando y las "
                    "dependencias del proyecto."
                )
            raise RuntimeError(message)

    def _terminate_process_tree(self) -> None:
        """Detiene el proceso administrado y todos sus descendientes.

        Terminar únicamente el wrapper padre no es suficiente: en Windows,
        por ejemplo, npm.cmd/cmd.exe puede dejar node.exe atendiendo el mismo
        puerto. La verificación posterior terminaría hablando con el código
        anterior y marcaría cualquier receta como NO_CORREGIDO.
        """
        process = self.process
        if process is None:
            return

        if process.poll() is not None:
            return

        pid = process.pid

        if _is_windows():
            # taskkill /T elimina el árbol completo; /F evita que un hijo que
            # ignora la terminación mantenga vivo el servidor anterior.
            try:
                completed = subprocess.run(
                    [
                        "taskkill",
                        "/PID",
                        str(pid),
                        "/T",
                        "/F",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if completed.returncode == 0:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
                    return
            except (OSError, subprocess.SubprocessError):
                pass

            # Fallback si taskkill no está disponible.
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            return

        # En POSIX el proceso se creó con start_new_session=True, por lo que
        # su PID identifica el grupo de procesos de la aplicación.
        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, OSError):
            pgid = None

        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass

        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        else:
            try:
                process.kill()
            except OSError:
                pass

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

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

        if self.process is not None:
            self._terminate_process_tree()
            self.process = None

        self._close_output_buffer()

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
