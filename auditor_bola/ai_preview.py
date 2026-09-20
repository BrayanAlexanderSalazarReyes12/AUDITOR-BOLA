"""Previsualización segura de recetas generadas por IA.

Este módulo no escribe archivos. Solo valida que la receta propuesta pueda
aplicarse sobre el archivo elegido y genera un diff unificado.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from .config import Correccion


def _aplicar_en_memoria(texto: str, receta: Correccion) -> tuple[str, int]:
    actual = texto
    aplicadas = 0

    for op in receta.operaciones:
        estrategia = op.get("estrategia", "replace_exact")
        limite = int(op.get("max_reemplazos", 1))

        if estrategia == "replace_exact":
            buscar = op.get("buscar")
            reemplazar = op.get("reemplazar")
            if buscar is None or reemplazar is None:
                raise ValueError("replace_exact requiere buscar/reemplazar")
            if buscar not in actual:
                raise RuntimeError(
                    "La propuesta no coincide exactamente con el código actual."
                )
            actual = actual.replace(buscar, reemplazar, limite)

        elif estrategia == "regex_replace":
            patron = op.get("patron")
            sustitucion = op.get("sustitucion")
            if patron is None or sustitucion is None:
                raise ValueError("regex_replace requiere patron/sustitucion")
            actual, cantidad = re.subn(
                patron,
                sustitucion,
                actual,
                count=limite,
                flags=re.MULTILINE | re.DOTALL,
            )
            if cantidad == 0:
                raise RuntimeError(
                    "La expresión regular propuesta no coincide con el código."
                )
        else:
            raise ValueError(f"estrategia no soportada: {estrategia}")

        aplicadas += 1

    return actual, aplicadas


def preview_recipe(
    receta: Correccion,
    target_root: str | Path,
) -> dict:
    """Previsualiza una receta de uno o varios archivos sin escribir cambios."""
    root = Path(target_root).resolve()
    raw_changes = [
        dict(item)
        for item in (receta.cambios or [])
        if isinstance(item, dict)
    ]
    plan = raw_changes or [{
        "archivo": receta.archivo,
        "operaciones": list(receta.operaciones or []),
    }]

    previews: list[dict] = []
    total_ops = 0
    for change in plan:
        relative = str(change.get("archivo") or "").replace("\\", "/")
        operaciones = [
            dict(item)
            for item in (change.get("operaciones") or [])
            if isinstance(item, dict)
        ]
        if not relative or not operaciones:
            raise ValueError("cambio de receta incompleto")

        archivo = (root / relative).resolve()
        if archivo == root or root not in archivo.parents:
            raise ValueError("ruta fuera de la carpeta objetivo")
        if not archivo.exists():
            raise FileNotFoundError(archivo)

        antes = archivo.read_text(encoding="utf-8")
        local = Correccion(
            control_id=receta.control_id,
            archivo=relative,
            operaciones=operaciones,
        )
        despues, aplicadas = _aplicar_en_memoria(antes, local)
        total_ops += aplicadas
        diff = "".join(
            difflib.unified_diff(
                antes.splitlines(keepends=True),
                despues.splitlines(keepends=True),
                fromfile=f"{relative}.before",
                tofile=f"{relative}.after",
            )
        )
        previews.append({
            "archivo": relative,
            "operaciones_aplicables": aplicadas,
            "cambia_archivo": antes != despues,
            "codigo_antes": antes,
            "codigo_despues": despues,
            "diff": diff,
        })

    first = previews[0]
    return {
        "archivo": first["archivo"],
        "operaciones_aplicables": total_ops,
        "cambia_archivo": any(
            item["cambia_archivo"]
            for item in previews
        ),
        "codigo_antes": first["codigo_antes"],
        "codigo_despues": first["codigo_despues"],
        "diff": "\n".join(
            item["diff"]
            for item in previews
            if item.get("diff")
        ),
        "archivos": previews,
    }
