"""Motor genérico de correcciones controladas.

No contiene nombres de aplicaciones ni archivos concretos. Cada aplicación
declara sus recetas de corrección en su perfil JSON.
"""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import ConfigObjetivo, Correccion
from .evidence import EvidenceSession, sha256_file


@dataclass
class CorrectionResult:
    control_id: str
    archivo: str
    estrategia: str
    applied: bool
    before_hash: str
    after_hash: str
    backup: str
    diff: str
    mensaje: str

    def as_dict(self) -> dict:
        return asdict(self)


def correction_available(cfg: ConfigObjetivo, control_id: str) -> bool:
    return cfg.correccion_por_control(control_id) is not None


def _aplicar_receta(texto: str, receta: Correccion) -> str:
    if receta.estrategia == "replace_exact":
        if receta.buscar is None or receta.reemplazar is None:
            raise ValueError(
                f"{receta.control_id}: replace_exact requiere buscar/reemplazar"
            )
        if receta.buscar not in texto:
            raise RuntimeError(
                f"{receta.control_id}: no se encontró el bloque esperado; "
                "no se modifica el archivo"
            )
        return texto.replace(
            receta.buscar, receta.reemplazar, receta.max_reemplazos
        )

    if receta.estrategia == "regex_replace":
        if receta.patron is None or receta.sustitucion is None:
            raise ValueError(
                f"{receta.control_id}: regex_replace requiere patron/sustitucion"
            )
        nuevo, cantidad = re.subn(
            receta.patron,
            receta.sustitucion,
            texto,
            count=receta.max_reemplazos,
            flags=re.MULTILINE,
        )
        if cantidad == 0:
            raise RuntimeError(
                f"{receta.control_id}: el patrón no coincidió; "
                "no se modifica el archivo"
            )
        return nuevo

    raise ValueError(
        f"{receta.control_id}: estrategia no soportada: {receta.estrategia}"
    )


def apply_correction(
    cfg: ConfigObjetivo,
    control_id: str,
    target_root: str | Path,
    evidence: EvidenceSession,
) -> CorrectionResult:
    receta = cfg.correccion_por_control(control_id)
    if receta is None:
        raise ValueError(f"no existe corrección declarada para {control_id}")

    root = Path(target_root).resolve()
    archivo = (root / receta.archivo).resolve()

    if archivo != root and root not in archivo.parents:
        raise ValueError("ruta de corrección fuera del target_root")
    if not archivo.exists():
        raise FileNotFoundError(archivo)

    antes = archivo.read_text(encoding="utf-8")
    before_hash = sha256_file(archivo)

    backup_dir = evidence.root / "cambios" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / receta.archivo.replace("/", "__").replace("\\", "__")
    shutil.copy2(archivo, backup)

    despues = _aplicar_receta(antes, receta)
    archivo.write_text(despues, encoding="utf-8")
    after_hash = sha256_file(archivo)

    diff = "".join(
        difflib.unified_diff(
            antes.splitlines(keepends=True),
            despues.splitlines(keepends=True),
            fromfile=f"{receta.archivo}.before",
            tofile=f"{receta.archivo}.after",
        )
    )
    (evidence.root / "cambios" / f"{control_id}.diff").write_text(
        diff, encoding="utf-8"
    )

    return CorrectionResult(
        control_id=control_id,
        archivo=receta.archivo,
        estrategia=receta.estrategia,
        applied=True,
        before_hash=before_hash,
        after_hash=after_hash,
        backup=str(backup),
        diff=diff,
        mensaje=(
            receta.descripcion
            or "corrección aplicada a la copia local; requiere verificación"
        ),
    )


def rollback(result: CorrectionResult, target_root: str | Path) -> None:
    root = Path(target_root).resolve()
    archivo = (root / result.archivo).resolve()
    backup = Path(result.backup)

    if archivo != root and root not in archivo.parents:
        raise ValueError("ruta de rollback fuera del target_root")
    shutil.copy2(backup, archivo)
