"""Orquestador común para CLI y GUI.

Garantiza que ambas interfaces ejecuten exactamente los mismos controles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import ConfigObjetivo
from .engine import (
    auditar,
    auditar_alcance_agente,
    auditar_controles_acceso,
    auditar_matriz_acceso,
)
from .pilar2 import auditar_pilar2
from .security_model import (\n    attach_runtime_consolidation,\n    infer_resource,\n    stable_finding_id,\n)


ProgressCallback = Callable[[int, str], None]


def diagnosticar(
    cfg: ConfigObjetivo,
    target_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
    *,
    require_both_pillars: bool = False,
) -> dict:
    """Ejecuta P1 + P2 e informa avance real por control completado."""
    p1_total = (
        len(cfg.endpoints) * len(cfg.cuentas)
        + len(cfg.chequeos_acceso)
        + len(cfg.chequeos_agente)
    )
    p2_total = len(cfg.chequeos_pilar2)
    matrix_total = (
        len(cfg.endpoints_detectados) * len(cfg.cuentas)
        if cfg.probar_todos_endpoints_con_todos_usuarios
        else 0
    )
    configured_total = p1_total + p2_total
    execution_total = configured_total + matrix_total

    missing: list[str] = []
    if p1_total == 0:
        missing.append("Pilar 1 (Identidad y Control de Acceso)")
    if p2_total == 0:
        missing.append("Pilar 2 (Arquitectura y Configuración)")

    if configured_total == 0:
        raise RuntimeError(
            "El perfil contiene 0 controles activos. "
            "Los endpoints detectados son inventario, no pruebas de "
            "seguridad ejecutables."
        )

    if require_both_pillars and missing:
        raise RuntimeError(
            "La auditoría P1 + P2 está incompleta: no hay controles activos "
            "para "
            + " y ".join(missing)
            + ". Los endpoints detectados son inventario y los candidatos "
            "P1 requieren confirmar semántica de seguridad antes de "
            "ejecutarse. No se informará '0 hallazgos' como si ambos pilares "
            "hubieran sido evaluados."
        )

    total = execution_total
    completed = 0

    def report(message: str, *, force: int | None = None) -> None:
        if progress_callback is None:
            return
        if force is None:
            value = 5 + int((completed / total) * 90)
            value = max(5, min(95, value))
        else: