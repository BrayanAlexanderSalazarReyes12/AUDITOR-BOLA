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
    root = Path(target_root).resolve()
    archivo = (root / receta.archivo).resolve()

    if archivo != root and root not in archivo.parents:
        raise ValueError("ruta fuera de la carpeta objetivo")
    if not archivo.exists():
        raise FileNotFoundError(archivo)

    antes = archivo.read_text(encoding="utf-8")
    despues, aplicadas = _aplicar_en_memoria(antes, receta)

    diff = "".join(
        difflib.unified_diff(
            antes.splitlines(keepends=True),
            despues.splitlines(keepends=True),
            fromfile=f"{receta.archivo}.before",
            tofile=f"{receta.archivo}.after",
        )
    )

    return {
        "archivo": receta.archivo,
        "operaciones_aplicables": aplicadas,
        "cambia_archivo": antes != despues,
        "diff": diff,
    }
