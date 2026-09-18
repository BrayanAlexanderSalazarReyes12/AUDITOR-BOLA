"""Gestor genérico del proceso local del sistema objetivo."""

from __future__ import annotations

import os
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

        env = os.environ.copy()
        env.update(self.runtime.variables)

        self.process = subprocess.Popen(
            self.runtime.comando_inicio,
            cwd=cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(self.runtime.espera_inicio)
        if self.process.poll() is not None:
            self.process = None
            raise RuntimeError("el sistema objetivo terminó durante el arranque")

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
