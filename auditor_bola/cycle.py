"""Ciclo correctivo genérico: diagnosticar -> corregir -> verificar -> rollback."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import ConfigObjetivo
from .corrective import apply_correction, rollback
from .evidence import EvidenceSession
from .runner import diagnosticar, filas_gui


def _estado_control(resultado: dict, control_id: str) -> str | None:
    filas = [fila for fila in filas_gui(resultado) if fila["id"] == control_id]
    if not filas:
        return None
    if any(fila["estado"] == "ERROR" for fila in filas):
        return "ERROR"
    if any(fila["estado"] == "HALLAZGO" for fila in filas):
        return "HALLAZGO"
    return "SIN_HALLAZGO"


def ciclo_correctivo(
    cfg: ConfigObjetivo,
    control_id: str,
    target_root: str | Path,
    *,
    evidence_base: str | Path = "evidencias",
    reiniciar: Callable[[], None] | None = None,
) -> dict:
    evidence = EvidenceSession.create(evidence_base)
    baseline = diagnosticar(cfg, target_root)
    evidence.write_json("baseline/resultados.json", baseline)

    estado_inicial = _estado_control(baseline, control_id)
    manifest = {
        "sistema": cfg.sistema,
        "version_objetivo": cfg.version_objetivo,
        "control": control_id,
        "estado_inicial": estado_inicial,
        "estado_final": None,
        "rollback": False,
        "evidencia": str(evidence.root),
    }

    if estado_inicial == "SIN_HALLAZGO":
        manifest["estado_final"] = "SIN_HALLAZGO"
        evidence.write_json("manifest.json", manifest)
        return manifest

    if estado_inicial in {None, "ERROR"}:
        manifest["estado_final"] = "ERROR"
        evidence.write_json("manifest.json", manifest)
        return manifest

    correccion = apply_correction(cfg, control_id, target_root, evidence)
    evidence.write_json("cambios/correccion.json", correccion.as_dict())

    if reiniciar:
        reiniciar()

    verificacion = diagnosticar(cfg, target_root)
    evidence.write_json("verification/resultados.json", verificacion)
    estado_despues = _estado_control(verificacion, control_id)

    if estado_despues == "SIN_HALLAZGO":
        manifest["estado_final"] = "CORREGIDO"
    else:
        rollback(correccion, target_root)
        manifest["rollback"] = True
        if reiniciar:
            reiniciar()
        restaurado = diagnosticar(cfg, target_root)
        evidence.write_json("verification/rollback.json", restaurado)
        manifest["estado_final"] = (
            "NO_CORREGIDO" if estado_despues == "HALLAZGO" else "ERROR"
        )

    evidence.write_json("manifest.json", manifest)
    return manifest
