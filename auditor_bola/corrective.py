"""Motor genérico de correcciones controladas.

No contiene nombres de aplicaciones ni archivos concretos. Cada aplicación
declara sus recetas de corrección en su perfil JSON.
"""

from __future__ import annotations

import difflib
import re
import shutil
from dataclasses import asdict, dataclass, field
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
    archivos: list[dict] = field(default_factory=list)

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
        # Si el texto de reemplazo ya está presente, la operación es
        # idempotente: otra corrección pudo haber resuelto el mismo bloque.
        if reemplazar in texto:
            return texto
        raise RuntimeError(
            f"{control_id}: no se encontró el bloque esperado ni la versión "
            "corregida; no se modifica el archivo"
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


def _plan_cambios(receta: Correccion) -> list[dict]:
    raw = [
        dict(item)
        for item in (receta.cambios or [])
        if isinstance(item, dict)
    ]
    if raw:
        plan: list[dict] = []
        for item in raw:
            archivo = str(item.get("archivo") or "").strip()
            operaciones = [
                dict(op)
                for op in (item.get("operaciones") or [])
                if isinstance(op, dict)
            ]
            if not archivo or not operaciones:
                raise ValueError(
                    f"{receta.control_id}: cambio multiarchivo incompleto"
                )
            plan.append({
                "archivo": archivo,
                "operaciones": operaciones,
            })
        return plan

    if not receta.archivo or not receta.operaciones:
        raise ValueError(
            f"{receta.control_id}: la receta no contiene cambios aplicables"
        )
    return [{
        "archivo": receta.archivo,
        "operaciones": [dict(op) for op in receta.operaciones],
    }]


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if target == root or root not in target.parents:
        raise ValueError("ruta de corrección fuera del target_root")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(target)
    return target


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
    plan = _plan_cambios(receta)

    # Fase 1: validar TODO el plan en memoria. Si un cambio falla, ningún
    # archivo se modifica.
    prepared: list[dict] = []
    for change in plan:
        relative = str(change["archivo"]).replace("\\", "/")
        archivo = _safe_target(root, relative)
        antes = archivo.read_text(encoding="utf-8")
        local_recipe = Correccion(
            control_id=receta.control_id,
            archivo=relative,
            operaciones=list(change["operaciones"]),
        )
        despues, applied_count = _aplicar_receta(
            antes,
            local_recipe,
        )
        prepared.append({
            "archivo": relative,
            "path": archivo,
            "antes": antes,
            "despues": despues,
            "before_hash": sha256_file(archivo),
            "operaciones_aplicadas": applied_count,
        })

    backup_dir = evidence.root / "cambios" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    modified: list[dict] = []

    try:
        # Fase 2: backups de todos los archivos antes de escribir ninguno.
        for item in prepared:
            relative = item["archivo"]
            backup = backup_dir / relative.replace("/", "__").replace("\\", "__")
            shutil.copy2(item["path"], backup)
            item["backup"] = str(backup)

        # Fase 3: escritura transaccional. Ante cualquier excepción se
        # restauran los archivos ya escritos.
        for item in prepared:
            item["path"].write_text(
                item["despues"],
                encoding="utf-8",
            )
            after_hash = sha256_file(item["path"])
            diff = "".join(
                difflib.unified_diff(
                    item["antes"].splitlines(keepends=True),
                    item["despues"].splitlines(keepends=True),
                    fromfile=f"{item['archivo']}.before",
                    tofile=f"{item['archivo']}.after",
                )
            )
            detail = {
                "archivo": item["archivo"],
                "before_hash": item["before_hash"],
                "after_hash": after_hash,
                "backup": item["backup"],
                "diff": diff,
                "operaciones_aplicadas": item["operaciones_aplicadas"],
            }
            modified.append(detail)
            safe_name = item["archivo"].replace("/", "__").replace("\\", "__")
            (evidence.root / "cambios" / f"{control_id}__{safe_name}.diff").write_text(
                diff,
                encoding="utf-8",
            )
    except Exception:
        for item in prepared:
            backup = Path(str(item.get("backup") or ""))
            target = item.get("path")
            if backup.is_file() and isinstance(target, Path):
                shutil.copy2(backup, target)
        raise

    if not modified:
        raise RuntimeError(
            f"{control_id}: el plan no produjo archivos modificados"
        )

    combined_diff = "\n".join(
        detail["diff"] for detail in modified if detail.get("diff")
    )
    (evidence.root / "cambios" / f"{control_id}.diff").write_text(
        combined_diff,
        encoding="utf-8",
    )

    primary = modified[0]
    return CorrectionResult(
        control_id=control_id,
        archivo=primary["archivo"],
        applied=True,
        before_hash=primary["before_hash"],
        after_hash=primary["after_hash"],
        backup=primary["backup"],
        diff=combined_diff,
        operaciones_aplicadas=sum(
            int(item["operaciones_aplicadas"])
            for item in modified
        ),
        mensaje=(
            receta.descripcion
            or "corrección aplicada transaccionalmente; requiere verificación"
        ),
        archivos=modified,
    )
def rollback(result: CorrectionResult, target_root: str | Path) -> None:
    root = Path(target_root).resolve()
    files = list(result.archivos or [])
    if not files:
        files = [{
            "archivo": result.archivo,
            "backup": result.backup,
        }]

    errors: list[str] = []
    for item in files:
        relative = str(item.get("archivo") or "")
        backup = Path(str(item.get("backup") or ""))
        archivo = (root / relative).resolve()
        try:
            if archivo == root or root not in archivo.parents:
                raise ValueError(
                    f"ruta de rollback fuera del target_root: {relative}"
                )
            if not backup.is_file():
                raise FileNotFoundError(backup)
            shutil.copy2(backup, archivo)
        except Exception as exc:
            errors.append(f"{relative}: {exc}")

    if errors:
        raise RuntimeError(
            "rollback incompleto: " + "; ".join(errors)
        )
