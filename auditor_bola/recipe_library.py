"""Biblioteca reutilizable de recetas correctivas.

Las recetas aceptadas pueden persistirse dentro del propio auditor para
reutilizarse en otros sistemas. La biblioteca no aplica recetas por similitud
de nombre solamente: cada candidata se adapta al archivo actual y debe superar
un preview determinista antes de ser ofrecida al usuario.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .ai_preview import preview_recipe
from .config import Correccion


SCHEMA_VERSION = 1


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    limpio = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return limpio.strip("-._") or "receta"


def biblioteca_por_defecto() -> Path:
    override = os.getenv("AUDITOR_RECIPE_LIBRARY")
    if override:
        return Path(override).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "recetas").resolve()


def _fingerprint(correccion: Correccion) -> str:
    """ID estable independiente de la ruta concreta de la aplicación."""
    payload = {
        "control_id": correccion.control_id,
        "operaciones": correccion.operaciones,
        "requiere_reinicio": correccion.requiere_reinicio,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class RecipeLibraryCandidate:
    recipe_id: str
    path: Path
    titulo: str
    verificada: bool
    score: int
    correccion: Correccion
    preview: dict
    metadata: dict

    def public_dict(self) -> dict:
        return {
            "recipe_id": self.recipe_id,
            "path": str(self.path),
            "titulo": self.titulo,
            "verificada": self.verificada,
            "score": self.score,
            "correccion": asdict(self.correccion),
            "preview": self.preview,
            "metadata": self.metadata,
        }


def guardar_receta_biblioteca(
    correccion: Correccion,
    *,
    sistema: str,
    version_objetivo: str | None = None,
    metodo: str | None = None,
    ruta: str | None = None,
    tipo_control: str | None = None,
    titulo: str | None = None,
    fuente: str = "usuario",
    proveedor: str | None = None,
    modelo: str | None = None,
    verificada: bool = False,
    library_root: str | Path | None = None,
) -> Path:
    """Guarda o actualiza una receta reusable sin almacenar credenciales."""
    root = (
        Path(library_root).resolve()
        if library_root is not None
        else biblioteca_por_defecto()
    )
    recipe_id = _fingerprint(correccion)
    folder = root / _safe_name(correccion.control_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{recipe_id[:20]}.json"

    now = _ts()
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    origen = {
        "sistema": sistema,
        "version_objetivo": version_objetivo,
        "archivo_origen": correccion.archivo,
        "extension_origen": Path(correccion.archivo).suffix.lower(),
        "metodo": metodo.upper() if metodo else None,
        "ruta": ruta,
        "tipo_control": tipo_control,
        "fuente": fuente,
        "proveedor": proveedor,
        "modelo": modelo,
        "registrado_en": now,
    }

    origins = list(existing.get("origenes") or [])
    clave_origen = (
        origen["sistema"],
        origen["archivo_origen"],
        origen["metodo"],
        origen["ruta"],
    )
    if not any(
        (
            item.get("sistema"),
            item.get("archivo_origen"),
            item.get("metodo"),
            item.get("ruta"),
        )
        == clave_origen
        for item in origins
    ):
        origins.append(origen)

    old_stats = existing.get("estadisticas") or {}
    verificaciones = int(old_stats.get("verificaciones_exitosas", 0))
    if verificada:
        verificaciones += 1

    data = {
        "schema_version": SCHEMA_VERSION,
        "recipe_id": recipe_id,
        "control_id": correccion.control_id,
        "titulo": titulo or correccion.descripcion or correccion.control_id,
        "descripcion": correccion.descripcion,
        "requiere_reinicio": correccion.requiere_reinicio,
        "operaciones": correccion.operaciones,
        "extension_origen": Path(correccion.archivo).suffix.lower(),
        "verificada": bool(existing.get("verificada")) or verificada,
        "creada_en": existing.get("creada_en") or now,
        "actualizada_en": now,
        "origenes": origins,
        "estadisticas": {
            "verificaciones_exitosas": verificaciones,
            "usos": int(old_stats.get("usos", 0)),
            "usos_exitosos": int(old_stats.get("usos_exitosos", 0)),
        },
    }

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _iter_recipe_files(root: Path, control_id: str):
    folder = root / _safe_name(control_id)
    if not folder.exists():
        return
    for path in sorted(folder.glob("*.json")):
        if path.name.lower() == "readme.json":
            continue
        yield path


def _score_recipe(
    data: dict,
    *,
    archivo: str,
    metodo: str | None,
    ruta: str | None,
) -> int:
    score = 0
    if data.get("verificada"):
        score += 50

    extension = Path(archivo).suffix.lower()
    if extension and extension == str(data.get("extension_origen") or "").lower():
        score += 15

    wanted_method = metodo.upper() if metodo else None
    for origin in data.get("origenes") or []:
        origin_method = str(origin.get("metodo") or "").upper() or None
        origin_route = origin.get("ruta")
        if wanted_method and origin_method == wanted_method:
            score += 12
        if ruta and origin_route == ruta:
            score += 12

    stats = data.get("estadisticas") or {}
    score += min(10, int(stats.get("usos_exitosos", 0)) * 2)
    return score


def buscar_recetas_compatibles(
    *,
    control_id: str,
    target_root: str | Path,
    archivo: str,
    metodo: str | None = None,
    ruta: str | None = None,
    library_root: str | Path | None = None,
) -> list[RecipeLibraryCandidate]:
    """Devuelve solo recetas que pueden previsualizarse sobre el archivo actual."""
    root = (
        Path(library_root).resolve()
        if library_root is not None
        else biblioteca_por_defecto()
    )
    target = Path(target_root).resolve()
    results: list[RecipeLibraryCandidate] = []

    for path in _iter_recipe_files(root, control_id) or []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("control_id") != control_id:
                continue

            correction = Correccion(
                control_id=control_id,
                archivo=archivo,
                operaciones=list(data.get("operaciones") or []),
                descripcion=data.get("descripcion") or data.get("titulo"),
                requiere_reinicio=bool(data.get("requiere_reinicio", False)),
            )
            preview = preview_recipe(correction, target)
            if not preview.get("cambia_archivo"):
                continue

            results.append(
                RecipeLibraryCandidate(
                    recipe_id=str(data.get("recipe_id") or path.stem),
                    path=path,
                    titulo=str(data.get("titulo") or control_id),
                    verificada=bool(data.get("verificada")),
                    score=_score_recipe(
                        data,
                        archivo=archivo,
                        metodo=metodo,
                        ruta=ruta,
                    ),
                    correccion=correction,
                    preview=preview,
                    metadata=data,
                )
            )
        except Exception:
            # Una receta incompatible o dañada no debe bloquear las demás.
            continue

    results.sort(
        key=lambda item: (
            not item.verificada,
            -item.score,
            item.titulo.lower(),
            item.recipe_id,
        )
    )
    return results


def marcar_uso_receta(
    path: str | Path,
    *,
    exitoso: bool,
) -> None:
    recipe_path = Path(path)
    data = json.loads(recipe_path.read_text(encoding="utf-8"))
    stats = data.setdefault("estadisticas", {})
    stats["usos"] = int(stats.get("usos", 0)) + 1
    if exitoso:
        stats["usos_exitosos"] = int(stats.get("usos_exitosos", 0)) + 1
        data["verificada"] = True
    data["actualizada_en"] = _ts()
    recipe_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
