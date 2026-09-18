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
    applied: bool
    before_hash: str
    after_hash: str
    backup: str
    diff: str
    operaciones_aplicadas: int
    mensaje: str

    def as_dict(self) -> dict:
        return asdict(self)


def correction_available(cfg: ConfigObjetivo, control_id: str) -> bool:
    receta = cfg.correccion_por_control(control_id)
    return bool(receta and receta.operaciones)


def _replace_exact(texto: str, op: dict, control_id: str) -> str:
    buscar = op.get("buscar")
    reemplazar = op.get("reemplazar")
    max_reemplazos = int(op.get("max_reemplazos", 1))
    if buscar is None or reemplazar is None:
        raise ValueError(
            f"{control_id}: replace_exact requiere buscar/reemplazar"
        )
    if buscar not in texto:
        raise RuntimeError(
            f"{control_id}: no se encontró el bloque esperado; "
            "no se modifica el archivo"
        )
    return texto.replace(buscar, reemplazar, max_reemplazos)


def _regex_replace(texto: str, op: dict, control_id: str) -> str:
    patron = op.get("patron")
    sustitucion = op.get("sustitucion")
    max_reemplazos = int(op.get("max_reemplazos", 1))
    if patron is None or sustitucion is None:
        raise ValueError(
            f"{control_id}: regex_replace requiere patron/sustitucion"
        )
    nuevo, cantidad = re.subn(
        patron,
        sustitucion,
        texto,
        count=max_reemplazos,
        flags=re.MULTILINE | re.DOTALL,
    )
    if cantidad == 0:
        raise RuntimeError(
            f"{control_id}: el patrón no coincidió; no se modifica el archivo"
        )
    return nuevo


def _aplicar_operacion(texto: str, op: dict, control_id: str) -> str:
    estrategia = op.get("estrategia", "replace_exact")
    if estrategia == "replace_exact":
        return _replace_exact(texto, op, control_id)
    if estrategia == "regex_replace":
        return _regex_replace(texto, op, control_id)
    raise ValueError(
        f"{control_id}: estrategia no soportada: {estrategia}"
    )


def _aplicar_receta(texto: str, receta: Correccion) -> tuple[str, int]:
    if not receta.operaciones:
        raise ValueError(
            f"{receta.control_id}: la receta no contiene operaciones"
        )
    actual = texto
    aplicadas = 0
    for op in receta.operaciones:
        actual = _aplicar_operacion(actual, op, receta.control_id)
        aplicadas += 1
    return actual, aplicadas


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

    despues, aplicadas = _aplicar_receta(antes, receta)
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
        applied=True,
        before_hash=before_hash,
        after_hash=after_hash,
        backup=str(backup),
        diff=diff,
        operaciones_aplicadas=aplicadas,
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
