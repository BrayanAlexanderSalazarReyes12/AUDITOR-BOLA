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
from typing import BinaryIO, Callable
from urllib.parse import urlparse

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
        self._configured_runtime = runtime
        self.runtime = runtime
        self.process: subprocess.Popen | None = None
        self._service_running = False
        self._prepared = False
        self._output: BinaryIO | None = None
        self._runtime_selected = False
        self._started_successfully = False
        self._selection_notes: list[str] = []
        self._cleanup_notes: list[str] = []
        self._progress_callback: Callable[[int, str], None] | None = None

    def _emit_progress(self, value: int, message: str) -> None:
        callback = self._progress_callback
        if callback is not None:
            callback(max(0, min(100, int(value))), message)

    def _modo(self) -> str:
        return self._runtime_mode(self.runtime)

    @staticmethod
    def _platform_key() -> str:
        if _is_windows():
            return "windows"
        if sys.platform == "darwin":
            return "macos"
        return "linux"

    def _command_for_runtime(
        self,
        runtime: RuntimeConfig,
        action: str,
    ) -> list[str]:
        if action not in {"inicio", "detener", "reinicio"}:
            raise ValueError(
                f"acción de runtime no soportada: {action}"
            )

        base = list(
            getattr(runtime, f"comando_{action}") or []
        )
        per_os = dict(
            getattr(runtime, f"comando_{action}_por_so") or {}
        )
        platform_key = self._platform_key()

        chosen = per_os.get(platform_key)
        if chosen is None:
            chosen = per_os.get("default")
        if chosen is None:
            chosen = base

        return [str(item) for item in chosen]

    def _command_for(self, action: str) -> list[str]:
        return self._command_for_runtime(
            self.runtime,
            action,
        )

    def _preparation_commands_for_runtime(
        self,
        runtime: RuntimeConfig,
    ) -> list[list[str]]:
        base = list(runtime.comandos_preparacion or [])
        per_os = dict(
            runtime.comandos_preparacion_por_so or {}
        )
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

    def _preparation_commands(self) -> list[list[str]]:
        return self._preparation_commands_for_runtime(
            self.runtime
        )

    @staticmethod
    def _runtime_mode(runtime: RuntimeConfig) -> str:
        mode = (runtime.modo or "process").strip().lower()
        if mode == "command":
            return "process"
        if mode not in {"process", "service", "external"}:
            raise ValueError(
                f"runtime.modo no soportado: {runtime.modo!r}; "
                "use process, service o external"
            )
        return mode

    def _runtime_options(self) -> list[RuntimeConfig]:
        options = [self._configured_runtime]

        for raw in self._configured_runtime.alternativas or []:
            if not isinstance(raw, dict):
                continue
            data = dict(raw)
            data["alternativas"] = []
            try:
                options.append(RuntimeConfig(**data))
            except TypeError:
                continue

        return options

    @staticmethod
    def _runtime_label(runtime: RuntimeConfig) -> str:
        if runtime.nombre:
            return runtime.nombre
        command = list(runtime.comando_inicio or [])
        return command[0] if command else runtime.modo

    def _context_for_runtime(
        self,
        runtime: RuntimeConfig,
    ) -> tuple[Path, dict[str, str]]:
        cwd = (
            self.root / runtime.directorio_trabajo
        ).resolve()

        if cwd != self.root and self.root not in cwd.parents:
            raise ValueError(
                "directorio_trabajo fuera del target_root"
            )

        if not cwd.exists() or not cwd.is_dir():
            raise FileNotFoundError(
                errno.ENOENT,
                (
                    "No existe el directorio de trabajo "
                    f"del objetivo: {cwd}"
                ),
                str(cwd),
            )

        env = os.environ.copy()
        env.update(runtime.variables)
        return cwd, env

    def _validate_runtime_candidate(
        self,
        runtime: RuntimeConfig,
    ) -> None:
        mode = self._runtime_mode(runtime)
        if mode == "external":
            raise RuntimeError(
                "requiere inicio externo"
            )

        cwd, env = self._context_for_runtime(runtime)
        start_command = self._command_for_runtime(
            runtime,
            "inicio",
        )
        if not start_command:
            raise RuntimeError(
                "no declara comando de inicio"
            )

        self._resolver_comando(
            cwd,
            env,
            raw=start_command,
        )

        if runtime.preparar_automaticamente:
            for preparation in (
                self._preparation_commands_for_runtime(runtime)
            ):
                self._resolver_comando(
                    cwd,
                    env,
                    raw=preparation,
                )

    def _select_runtime_if_needed(self) -> None:
        self._emit_progress(10, "Evaluando estrategias de arranque disponibles…")
        if self._runtime_selected:
            return

        problems: list[str] = []
        external: list[str] = []

        for index, candidate in enumerate(
            self._runtime_options()
        ):
            label = self._runtime_label(candidate)
            mode = self._runtime_mode(candidate)

            if mode == "external":
                external.append(label)
                continue

            try:
                self._validate_runtime_candidate(candidate)
            except Exception as exc:
                command = self._command_for_runtime(
                    candidate,
                    "inicio",
                )
                executable = (
                    command[0]
                    if command
                    else "sin comando"
                )
                problems.append(
                    f"{label}: no disponible "
                    f"({executable}) — {exc}"
                )
                continue

            self.runtime = candidate
            self._runtime_selected = True
            self._emit_progress(
                20,
                "Runtime seleccionado: "
                f"{self._runtime_label(candidate)}",
            )
            self._selection_notes = problems
            return

        self.runtime = self._configured_runtime
        self._selection_notes = problems

        lines = [
            "Aegis no encontró una estrategia de arranque "
            "ejecutable para esta aplicación.",
        ]
        if problems:
            lines.append("")
            lines.append("Estrategias evaluadas:")
            lines.extend(
                f"- {problem}"
                for problem in problems
            )
        if external:
            lines.append("")
            lines.append(
                "También se detectaron opciones que requieren "
                "iniciar el objetivo fuera de Aegis: "
                + ", ".join(external)
                + "."
            )
        lines.extend(
            [
                "",
                "Instala uno de los runtimes requeridos o "
                "ajusta runtime en el perfil JSON.",
            ]
        )
        raise RuntimeError("\n".join(lines))

    def runtime_status(self) -> dict[str, object]:
        return {
            "seleccionado": self._runtime_selected,
            "nombre": self._runtime_label(self.runtime),
            "origen": self.runtime.origen,
            "modo": self._runtime_mode(self.runtime),
            "base_url": self.runtime.base_url,
            "comando_inicio": self._command_for("inicio"),
            "alternativas_descartadas": list(
                self._selection_notes
            ),
            "limpieza_previa": list(self._cleanup_notes),
        }

    def has_started(self) -> bool:
        return bool(
            self._started_successfully
            or self._service_running
            or (
                self.process
                and self.process.poll() is None
            )
        )

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
        return self._context_for_runtime(self.runtime)

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

    def _target_process_markers(self) -> list[str]:
        """Marcadores específicos para reconocer procesos del proyecto."""
        markers = [str(self.root)]
        try:
            cwd, env = self._context()
            resolved = self._resolver_comando(
                cwd,
                env,
                raw=self._command_for("inicio"),
            )
        except Exception:
            resolved = self._command_for("inicio")

        for item in resolved[1:]:
            text = str(item).strip()
            if not text:
                continue
            candidate = Path(text)
            if candidate.is_absolute():
                markers.append(str(candidate))
            elif candidate.suffix or "/" in text or "\\" in text:
                try:
                    markers.append(str((self.root / text).resolve()))
                except OSError:
                    markers.append(text)

        normalized: list[str] = []
        seen: set[str] = set()
        for marker in markers:
            value = os.path.normcase(os.path.normpath(marker))
            if len(value) < 4 or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _command_matches_target(self, command_line: str) -> bool:
        if not command_line:
            return False
        haystack = os.path.normcase(command_line)
        return any(
            marker in haystack
            for marker in self._target_process_markers()
        )

    def _discover_target_processes(self) -> set[int]:
        """Busca procesos del mismo proyecto sin tocar procesos ajenos."""
        matches: set[int] = set()
        current_pid = os.getpid()

        if _is_windows():
            powershell = (
                shutil.which("powershell.exe")
                or shutil.which("pwsh.exe")
                or shutil.which("pwsh")
            )
            if not powershell:
                return matches
            script = (
                "Get-CimInstance Win32_Process | "
                "ForEach-Object { "
                "'{0}`t{1}' -f $_.ProcessId,$_.CommandLine "
                "}"
            )
            try:
                completed = subprocess.run(
                    [powershell, "-NoProfile", "-Command", script],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                return matches
            if completed.returncode != 0:
                return matches
            rows = completed.stdout.splitlines()
            for row in rows:
                raw_pid, sep, command = row.strip().partition("\t")
                if not sep or not raw_pid.isdigit():
                    continue
                pid = int(raw_pid)
                if pid <= 4 or pid == current_pid:
                    continue
                if self._command_matches_target(command.strip()):
                    matches.add(pid)
            return matches

        try:
            completed = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return matches
        if completed.returncode != 0:
            return matches

        for row in completed.stdout.splitlines():
            line = row.strip()
            if not line:
                continue
            raw_pid, sep, command = line.partition(" ")
            if not sep or not raw_pid.isdigit():
                continue
            pid = int(raw_pid)
            if pid <= 1 or pid == current_pid:
                continue
            if self._command_matches_target(command.strip()):
                matches.add(pid)
        return matches

    def _terminate_pid_tree_by_id(self, pid: int) -> bool:
        if pid <= 4 or pid == os.getpid():
            return False

        if _is_windows():
            try:
                completed = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except (OSError, subprocess.SubprocessError):
                return False
            return completed.returncode == 0

        try:
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError, OSError):
            return False
        try:
            if pgid == pid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return False

        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError, OSError):
            return True

        try:
            if pgid == pid:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        return True

    def _terminate_all_previous_target_processes(self) -> list[int]:
        """Cierra cualquier proceso anterior perteneciente al mismo proyecto."""
        killed: list[int] = []
        for pid in sorted(self._discover_target_processes()):
            if self._terminate_pid_tree_by_id(pid):
                killed.append(pid)
        return killed

    def _local_port_from_runtime(self) -> int | None:
        """Devuelve el puerto local explícito usado por el runtime."""
        raw_url = str(self.runtime.base_url or "").strip()
        if not raw_url:
            return None

        try:
            parsed = urlparse(raw_url)
            host = (parsed.hostname or "").lower()
            port = parsed.port
        except (ValueError, TypeError):
            return None

        local_hosts = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "::",
        }
        if host not in local_hosts or port is None:
            return None

        # Evita cerrar por accidente servicios del sistema en puertos
        # privilegiados. Los perfiles generados por Aegis usan puertos
        # explícitos de desarrollo (3000, 5000, 8000, 8080, etc.).
        if port < 1024:
            return None
        return int(port)

    def _windows_listener_pids(self, port: int) -> set[int]:
        try:
            completed = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return set()

        if completed.returncode != 0:
            return set()

        pids: set[int] = set()
        suffix = f":{port}"
        for raw_line in completed.stdout.splitlines():
            line = raw_line.strip()
            if not line or "LISTENING" not in line.upper():
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            local_address = parts[1]
            if not local_address.endswith(suffix):
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid > 4 and pid != os.getpid():
                pids.add(pid)
        return pids

    def _posix_listener_pids(self, port: int) -> set[int]:
        env = os.environ.copy()
        lsof = self._which("lsof", env)
        if lsof:
            try:
                completed = subprocess.run(
                    [
                        lsof,
                        "-nP",
                        "-t",
                        f"-iTCP:{port}",
                        "-sTCP:LISTEN",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if completed.returncode in {0, 1}:
                    return {
                        int(item)
                        for item in completed.stdout.split()
                        if item.isdigit()
                        and int(item) > 1
                        and int(item) != os.getpid()
                    }
            except (OSError, subprocess.SubprocessError):
                pass

        fuser = self._which("fuser", env)
        if fuser:
            try:
                completed = subprocess.run(
                    [fuser, "-n", "tcp", str(port)],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                output = f"{completed.stdout} {completed.stderr}"
                return {
                    int(item)
                    for item in output.replace(f"{port}/tcp:", " ").split()
                    if item.isdigit()
                    and int(item) > 1
                    and int(item) != os.getpid()
                }
            except (OSError, subprocess.SubprocessError):
                pass

        return set()

    def _terminate_stale_listener(self, port: int) -> list[int]:
        """Elimina procesos huérfanos que mantienen ocupado el puerto objetivo."""
        if _is_windows():
            pids = self._windows_listener_pids(port)
            killed: list[int] = []
            for pid in sorted(pids):
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
                        killed.append(pid)
                except (OSError, subprocess.SubprocessError):
                    continue
            return killed

        pids = self._posix_listener_pids(port)
        killed: list[int] = []
        for pid in sorted(pids):
            try:
                pgid = os.getpgid(pid)
            except (ProcessLookupError, PermissionError, OSError):
                pgid = None

            try:
                if pgid == pid:
                    os.killpg(pgid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except (ProcessLookupError, PermissionError, OSError):
                continue

        if killed:
            time.sleep(0.35)
            for pid in killed:
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, PermissionError, OSError):
                    continue
                try:
                    pgid = os.getpgid(pid)
                except (ProcessLookupError, PermissionError, OSError):
                    pgid = None
                try:
                    if pgid == pid:
                        os.killpg(pgid, signal.SIGKILL)
                    else:
                        os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError):
                    pass

        return killed

    def _cleanup_previous_instance(self) -> None:
        """Limpia instancias anteriores antes de cualquier nuevo arranque.

        Esto cubre cierres forzados de Aegis donde el proceso objetivo o un
        servicio (por ejemplo Docker Compose) pudo quedar vivo.
        """
        self._cleanup_notes = []
        self._emit_progress(
            25,
            "Buscando y cerrando instancias anteriores del objetivo…",
        )

        # Si esta instancia de Aegis todavía conserva un proceso administrado,
        # se detiene primero de forma normal.
        if self.has_started():
            try:
                self.stop()
                self._cleanup_notes.append(
                    "Se detuvo la instancia administrada que seguía activa."
                )
            except Exception as exc:
                self._cleanup_notes.append(
                    f"No se pudo detener la instancia administrada: {exc}"
                )

        mode = self._modo()
        stop_command = self._command_for("detener")

        killed_target_pids = self._terminate_all_previous_target_processes()
        if killed_target_pids:
            self._cleanup_notes.append(
                "Se cerraron procesos anteriores del mismo proyecto: "
                + ", ".join(str(pid) for pid in killed_target_pids)
            )
        else:
            self._cleanup_notes.append(
                "No se detectaron procesos anteriores del mismo proyecto."
            )

        # En modo service el comando de parada es la forma más precisa de
        # limpiar servicios huérfanos (docker compose down, systemctl, etc.).
        if mode == "service" and stop_command:
            try:
                self._run_control_command(
                    stop_command,
                    action_name="limpiar instancia anterior",
                )
                self._cleanup_notes.append(
                    "Se ejecutó el comando de limpieza del servicio anterior."
                )
            except Exception as exc:
                # Una parada puede fallar simplemente porque no había servicio.
                # No debe impedir probar el arranque nuevo.
                self._cleanup_notes.append(
                    "El comando de limpieza previa no encontró un servicio "
                    f"detenible o falló: {exc}"
                )

        port = self._local_port_from_runtime()
        if port is not None:
            killed = self._terminate_stale_listener(port)
            if killed:
                self._cleanup_notes.append(
                    f"Se cerraron procesos huérfanos en el puerto {port}: "
                    + ", ".join(str(pid) for pid in killed)
                )
            else:
                self._cleanup_notes.append(
                    f"Puerto {port} libre; no se detectaron procesos huérfanos."
                )

        self._service_running = False
        self._started_successfully = False
        self.process = None
        self._close_output_buffer()
        self._emit_progress(32, "Limpieza previa completada.")

    def _prepare_if_needed(self) -> None:
        if not self.runtime.preparar_automaticamente or self._prepared:
            self._emit_progress(35, "Dependencias listas.")
            return

        commands = self._preparation_commands()
        if not commands:
            self._prepared = True
            self._emit_progress(35, "No se requiere preparación adicional.")
            return

        total = len(commands)
        for index, command in enumerate(commands, start=1):
            command_text = " ".join(str(item) for item in command)
            self._emit_progress(
                25 + int(((index - 1) / max(1, total)) * 30),
                f"Preparando dependencias ({index}/{total}): {command_text}",
            )
            self._run_control_command(
                command,
                action_name=f"preparar ({index}/{total})",
            )

        self._prepared = True
        self._emit_progress(55, "Preparación del proyecto completada.")

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

    def start(
        self,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, object]:
        self._progress_callback = progress_callback
        self._emit_progress(5, "Iniciando aplicación objetivo…")
        self._select_runtime_if_needed()
        mode = self._modo()

        if mode == "external":
            raise RuntimeError(
                "Este perfil requiere un runtime externo. "
                "Inicia la aplicación fuera de Aegis y luego "
                "ejecuta el diagnóstico contra base_url."
            )

        self._cleanup_previous_instance()
        self._prepare_if_needed()

        start_command = self._command_for("inicio")
        if not start_command:
            raise RuntimeError(
                "el perfil no declara comando de inicio para "
                f"{self._platform_key()}"
            )

        if mode == "service":
            self._emit_progress(65, "Iniciando servicio objetivo…")
            self._run_control_command(
                start_command,
                action_name="iniciar",
            )
            self._service_running = True
            self._started_successfully = True
            self._emit_progress(85, "Esperando estabilización del servicio…")
            time.sleep(self.runtime.espera_inicio)
            self._emit_progress(100, "Aplicación objetivo iniciada.")
            return self.runtime_status()

        cwd, env = self._context()
        command = self._resolver_comando(
            cwd,
            env,
            raw=start_command,
        )

        self._emit_progress(65, "Lanzando proceso de la aplicación…")
        self._reset_output_buffer()

        try:
            popen_kwargs = {
                "cwd": cwd,
                "env": env,
                "stdout": self._output,
                "stderr": subprocess.STDOUT,
            }

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
            self.process = None
            raise FileNotFoundError(
                errno.ENOENT,
                (
                    "No se pudo iniciar el objetivo. "
                    f"Comando resuelto: {command[0]!r}. "
                    "Verifica instalación, PATH y runtime requerido."
                ),
                command[0],
            ) from exc

        self._emit_progress(85, "Esperando que la aplicación quede estable…")
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

        self._started_successfully = True
        self._emit_progress(100, "Aplicación objetivo iniciada.")
        return self.runtime_status()

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
        # Si el arranque falló, no ejecutar comandos de parada del runtime
        # configurado. Evita, por ejemplo, intentar "docker compose down"
        # después de que Docker no estaba instalado.
        if not self.has_started():
            self._close_output_buffer()
            return

        mode = self._modo()

        if mode == "external":
            self._started_successfully = False
            return

        stop_command = self._command_for("detener")

        if mode == "service":
            if self._service_running and stop_command:
                self._run_control_command(
                    stop_command,
                    action_name="detener",
                )
            self._service_running = False
            self._started_successfully = False
            return

        if self.process is not None:
            self._terminate_process_tree()
            self.process = None

        self._close_output_buffer()

        if self._started_successfully and stop_command:
            self._run_control_command(
                stop_command,
                action_name="detener",
            )

        self._started_successfully = False

    def restart(self) -> dict[str, object]:
        if not self.has_started():
            return self.start()

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
            self._started_successfully = True
            time.sleep(self.runtime.espera_inicio)
            return self.runtime_status()

        self.stop()
        return self.start()
