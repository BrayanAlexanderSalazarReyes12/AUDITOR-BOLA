"""Orquestador común para CLI y GUI.

Garantiza que ambas interfaces ejecuten exactamente los mismos controles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import ConfigObjetivo
from .engine import auditar, auditar_alcance_agente, auditar_controles_acceso
from .pilar2 import auditar_pilar2


ProgressCallback = Callable[[int, str], None]


def diagnosticar(
    cfg: ConfigObjetivo,
    target_root: str | Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """Ejecuta P1 + P2 e informa avance real por control completado."""
    total = (
        len(cfg.endpoints) * len(cfg.cuentas)
        + len(cfg.chequeos_acceso)
        + len(cfg.chequeos_agente)
        + len(cfg.chequeos_pilar2)
    )
    total = max(1, total)
    completed = 0

    def report(message: str, *, force: int | None = None) -> None:
        if progress_callback is None:
            return
        if force is None:
            value = 5 + int((completed / total) * 90)
            value = max(5, min(95, value))
        else:
            value = force
        progress_callback(value, message)

    def advance(message: str) -> None:
        nonlocal completed
        completed += 1
        report(message)

    report("Preparando controles de Pilar 1…", force=5)

    bola = auditar(
        cfg,
        progress_callback=lambda text: advance(text),
    )
    acceso = auditar_controles_acceso(
        cfg,
        progress_callback=lambda text: advance(text),
    )
    agente = (
        auditar_alcance_agente(
            cfg,
            progress_callback=lambda text: advance(text),
        )
        if cfg.chequeos_agente
        else []
    )

    if cfg.chequeos_pilar2:
        report("Iniciando Pilar 2 · Arquitectura y Configuración…")
    pilar2 = auditar_pilar2(
        cfg,
        target_root,
        progress_callback=lambda text: advance(text),
    )

    report("Consolidando resultados y hallazgos…", force=98)

    resultado = {
        "sistema": cfg.sistema,
        "version_objetivo": cfg.version_objetivo,
        "base_url": cfg.base_url,
        "pilar1": {
            "bola": [item.as_dict() for item in bola],
            "acceso": [item.as_dict() for item in acceso],
            "alcance_agente": [item.as_dict() for item in agente],
        },
        "pilar2": [item.as_dict() for item in pilar2],
        "resumen": {
            "bola_confirmados": sum(item.confirmado_bola for item in bola),
            "acceso_vulnerable": sum(item.vulnerable for item in acceso),
            "agente_vulnerable": sum(item.resultado.vulnerable for item in agente),
            "pilar2_hallazgos": sum(item.estado == "HALLAZGO" for item in pilar2),
            "errores": sum(item.estado == "ERROR" for item in pilar2),
        },
    }
    report("Diagnóstico Pilar 1 + Pilar 2 completado.", force=100)
    return resultado

def filas_gui(resultado: dict) -> list[dict]:
    """Normaliza todos los motores a filas simples para la GUI."""
    filas: list[dict] = []

    for item in resultado["pilar1"]["bola"]:
        estado = "HALLAZGO" if item["confirmado_bola"] else "SIN_HALLAZGO"
        filas.append(
            {
                "pilar": "P1",
                "id": item.get("id_control") or "P1-BOLA",
                "control": item.get("descripcion") or f"BOLA {item['metodo']} {item['endpoint']}",
                "cuenta": item["cuenta"],
                "estado": estado,
                "detalle": f"HTTP {item['http_status']} · esperado={item['acceso_esperado']} real={item['acceso_real']}",
                "tipo_control": "bola",
                "metodo": item["metodo"],
                "ruta": item["endpoint"],
            }
        )

    for item in resultado["pilar1"]["acceso"]:
        filas.append(
            {
                "pilar": "P1",
                "id": item["id_control"],
                "control": item["nombre"],
                "cuenta": item["cuenta"],
                "estado": "HALLAZGO" if item["vulnerable"] else "SIN_HALLAZGO",
                "detalle": f"HTTP {item['http_status']} · esperado={item['acceso_esperado']} real={item['acceso_real']}",
                "tipo_control": "acceso",
                "metodo": item["metodo"],
                "ruta": item["endpoint"],
            }
        )

    for item in resultado["pilar1"]["alcance_agente"]:
        r = item["resultado"]
        filas.append(
            {
                "pilar": "P1",
                "id": item["id_control"],
                "control": item["nombre_chequeo"],
                "cuenta": item["cuenta"],
                "estado": "HALLAZGO" if r["vulnerable"] else "SIN_HALLAZGO",
                "detalle": f"API={r['cantidad_api_directa']} agente={r['cantidad_agente']} exceso={r['exceso']}",
                "tipo_control": "alcance_agente",
                "metodo": None,
                "ruta": None,
            }
        )

    for item in resultado["pilar2"]:
        filas.append(
            {
                "pilar": "P2",
                "id": item["id_control"],
                "control": item["nombre"],
                "cuenta": "-",
                "estado": item["estado"],
                "detalle": item["detalle"],
                "tipo_control": item["tipo"],
                "metodo": None,
                "ruta": None,
            }
        )

    return filas
