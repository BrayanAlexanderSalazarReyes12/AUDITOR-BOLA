"""Orquestador común para CLI y GUI.

Garantiza que ambas interfaces ejecuten exactamente los mismos controles.
"""

from __future__ import annotations

from pathlib import Path

from .config import ConfigObjetivo
from .engine import auditar, auditar_alcance_agente, auditar_controles_acceso
from .pilar2 import auditar_pilar2


def diagnosticar(cfg: ConfigObjetivo, target_root: str | Path | None = None) -> dict:
    bola = auditar(cfg)
    acceso = auditar_controles_acceso(cfg)
    agente = auditar_alcance_agente(cfg) if cfg.chequeos_agente else []
    pilar2 = auditar_pilar2(cfg, target_root)

    return {
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
