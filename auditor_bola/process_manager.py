"""Gestor opcional del proceso local de Tramitia para pruebas correctivas."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


class LocalTargetProcess:
    def __init__(self, target_root: str | Path):
        self.root = Path(target_root).resolve()
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.process = subprocess.Popen(
            [sys.executable, "run.py"],
            cwd=self.root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.2)
        if self.process.poll() is not None:
            raise RuntimeError("Tramitia local terminó durante el arranque")

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
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
