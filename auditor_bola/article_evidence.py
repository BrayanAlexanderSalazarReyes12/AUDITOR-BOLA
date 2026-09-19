"""Exportación redactada de evidencia para documentación y artículos."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


SENSITIVE_KEY = re.compile(
    r"(password|passwd|token|secret|cookie|authorization|api[_-]?key|credential)",
    re.I,
)

ALLOWED_NAMES = {
    "manifest.json",
    "resultados.json",
    "correccion.json",
    "manual.json",
    "rollback.json",
    "conocimiento_aprendido.json",
    "contexto_redactado.json",
    "propuestas.json",
    "seleccion.json",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if SENSITIVE_KEY.search(str(key)):
                result[key] = "[REDACTADO]"
            else:
                result[key] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _copy_redacted_json(source: Path, destination: Path) -> None:
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(_redact(data), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def export_article_package(session_dir: str | Path, destination_root: str | Path) -> Path:
    """Crea una copia publicable de una sesión sin alterar el original."""
    source = Path(session_dir).expanduser().resolve()
    destination_root = Path(destination_root).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(source)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = destination_root / f"{source.name}-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    copied = []

    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if "backup" in {part.lower() for part in relative.parts}:
            continue
        if path.suffix.lower() == ".diff":
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(relative.as_posix())
            continue
        if path.suffix.lower() == ".json" and path.name in ALLOWED_NAMES:
            target = out / relative
            _copy_redacted_json(path, target)
            if target.exists():
                copied.append(relative.as_posix())

    summary = [
        "# Paquete de evidencia para artículo",
        "",
        f"- Sesión fuente: {source.name}",
        f"- Exportado: {datetime.now().isoformat(timespec='seconds')}",
        "- Backups de código: excluidos",
        "- JSON: redactado por nombres de campos sensibles",
        "",
        "## Archivos incluidos",
        "",
    ]
    summary.extend(f"- {item}" for item in sorted(copied))
    summary.extend(["", "La evidencia original permanece sin modificaciones.", ""])
    (out / "RESUMEN_ARTICULO.md").write_text("\n".join(summary), encoding="utf-8")
    return out
