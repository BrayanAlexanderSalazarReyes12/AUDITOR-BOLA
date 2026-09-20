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
from .security_model import attach_runtime_consolidation


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
            value = force
        detail = (
            f"{message} · Control {completed}/{total}"
            if force is None
            else message
        )
        progress_callback(value, detail)

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

    matriz_acceso = auditar_matriz_acceso(
        cfg,
        progress_callback=lambda text: advance(text),
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
            "matriz_acceso": [
                item.as_dict() for item in matriz_acceso
            ],
        },
        "pilar2": [item.as_dict() for item in pilar2],
        "resumen": {
            "controles_configurados": configured_total,
            "controles_pilar1": p1_total,
            "controles_pilar2": p2_total,
            "controles_ejecutados": completed,
            "matriz_endpoint_usuario_total": len(matriz_acceso),
            "matriz_accesos": sum(
                item.clasificacion == "ACCESO"
                for item in matriz_acceso
            ),
            "matriz_denegados": sum(
                item.clasificacion == "DENEGADO"
                for item in matriz_acceso
            ),
            "matriz_hallazgos_confirmados": sum(
                item.clasificacion == "HALLAZGO_CONFIRMADO"
                for item in matriz_acceso
            ),
            "matriz_hallazgos_probables": sum(
                item.clasificacion == "POSIBLE_HALLAZGO"
                for item in matriz_acceso
            ),
            "matriz_cumple": sum(
                item.clasificacion == "CUMPLE"
                for item in matriz_acceso
            ),
            "matriz_no_concluyentes": sum(
                item.clasificacion in {
                    "NO_CONCLUYENTE",
                    "NO_EJECUTABLE",
                    "OBSERVADO",
                }
                for item in matriz_acceso
            ),
            "bola_confirmados": sum(item.confirmado_bola for item in bola),
            "acceso_vulnerable": sum(item.vulnerable for item in acceso),
            "agente_vulnerable": sum(item.resultado.vulnerable for item in agente),
            "pilar2_hallazgos": sum(item.estado == "HALLAZGO" for item in pilar2),
            "errores": sum(item.estado == "ERROR" for item in pilar2),
        },
    }
    resultado = attach_runtime_consolidation(resultado)
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

    for item in resultado["pilar1"].get("matriz_acceso", []):
        clasificacion = item.get("clasificacion") or "OBSERVADO"
        if clasificacion == "ERROR":
            estado = "ERROR"
        elif clasificacion == "NO_EJECUTABLE":
            estado = "OMITIDO"
        elif clasificacion == "HALLAZGO_CONFIRMADO":
            estado = (
                "CONFIRMADO"
                if item.get("id_control_referencia")
                else "VULNERABLE"
            )
        elif clasificacion == "POSIBLE_HALLAZGO":
            estado = "VULNERABLE"
        elif clasificacion == "CUMPLE":
            estado = "SIN_HALLAZGO"
        else:
            estado = "OBSERVADO"
        filas.append(
            {
                "pilar": "P1",
                "id": (
                    item.get("id_control_referencia")
                    or "P1-MATRIX"
                ),
                "control": (
                    "Matriz endpoint × usuario · "
                    f"{item['metodo']} {item['endpoint_detectado']}"
                ),
                "cuenta": item["cuenta"],
                "estado": estado,
                "detalle": (
                    f"{clasificacion} · {item.get('detalle') or ''}"
                ),
                "tipo_control": "matriz_acceso",
                "metodo": item["metodo"],
                "ruta": item["endpoint_detectado"],
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