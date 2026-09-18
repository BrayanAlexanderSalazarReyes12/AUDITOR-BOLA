"""Conservación de evidencia del ciclo de auditoría/corrección."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    ruta = Path(path)
    h = hashlib.sha256()
    with ruta.open("rb") as handle:
        for bloque in iter(lambda: handle.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class EvidenceSession:
    root: Path

    @classmethod
    def create(cls, base_dir: str | Path = "evidencias") -> "EvidenceSession":
        root = Path(base_dir) / _timestamp()
        (root / "baseline").mkdir(parents=True, exist_ok=True)
        (root / "cambios").mkdir(parents=True, exist_ok=True)
        (root / "verification").mkdir(parents=True, exist_ok=True)
        return cls(root=root)

    def write_json(self, relative: str, payload: dict | list) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def snapshot_file(self, path: str | Path, label: str) -> dict:
        ruta = Path(path)
        data = {
            "path": str(ruta),
            "sha256": sha256_file(ruta),
            "size": ruta.stat().st_size,
        }
        self.write_json(f"{label}/hash-{ruta.name}.json", data)
        return data
