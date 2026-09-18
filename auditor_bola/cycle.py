"""Ciclo correctivo genérico y operaciones de verificación/rollback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from .config import ConfigObjetivo
from .corrective import (
    CorrectionResult,
    apply_correction,
    correction_available,
    rollback,
)
from .evidence import EvidenceSession, sha256_file
from .runner import diagnosticar, filas_gui


def estado_control(resultado: dict, control_id: str) -> str | None:
    filas = [fila for fila in filas_gui(resultado) if fila["id"] == control_id]
    if not filas:
        return None
    if any(fila["estado"] == "ERROR" for fila in filas):
        return "ERROR"
    if any(fila["estado"] == "HALLAZGO" for fila in filas):
        return "HALLAZGO"
    return "SIN_HALLAZGO"


def controles_hallazgo(resultado: dict) -> list[str]:
    """Devuelve todos los controles únicos actualmente en HALLAZGO."""
    controles: list[str] = []
    for fila in filas_gui(resultado):
        control_id = fila["id"]
        if fila["estado"] == "HALLAZGO" and control_id not in controles:
            controles.append(control_id)
    return controles


def verificar_control(
    cfg: ConfigObjetivo,
    control_id: str,
    target_root: str | Path | None,
    *,
    evidence_base: str | Path = "evidencias",
) -> dict:
    """Repite el diagnóstico y conserva evidencia de una verificación manual."""
    evidence = EvidenceSession.create(evidence_base)
    resultado = diagnosticar(cfg, target_root)
    estado = estado_control(resultado, control_id)
    payload = {
        "sistema": cfg.sistema,
        "version_objetivo": cfg.version_objetivo,
        "control": control_id,
        "estado": estado,
        "resultado": resultado,
        "evidencia": str(evidence.root),
    }
    evidence.write_json("verification/manual.json", payload)
    evidence.write_json(
        "manifest.json",
        {
            "sistema": cfg.sistema,
            "version_objetivo": cfg.version_objetivo,
            "control": control_id,
            "tipo": "VERIFICACION_MANUAL",
            "estado_final": estado,
            "evidencia": str(evidence.root),
        },
    )
    return payload


def _rollback_seguro(
    cfg: ConfigObjetivo,
    correccion: CorrectionResult,
    target_root: str | Path,
    evidence: EvidenceSession,
    reiniciar: Callable[[], None] | None,
    manifest: dict,
) -> None:
    """Intenta restaurar el archivo y documenta cualquier fallo del rollback."""
    try:
        rollback(correccion, target_root)
        manifest["rollback"] = True

        if reiniciar:
            try:
                reiniciar()
            except Exception as exc:
                manifest["rollback_restart_error"] = str(exc)

        try:
            restaurado = diagnosticar(cfg, target_root)
            evidence.write_json("verification/rollback.json", restaurado)
        except Exception as exc:
            manifest["rollback_verification_error"] = str(exc)
    except Exception as exc:
        manifest["rollback_error"] = str(exc)


def ciclo_correctivo(
    cfg: ConfigObjetivo,
    control_id: str,
    target_root: str | Path,
    *,
    evidence_base: str | Path = "evidencias",
    reiniciar: Callable[[], None] | None = None,
) -> dict:
    evidence = EvidenceSession.create(evidence_base)

    try:
        baseline = diagnosticar(cfg, target_root)
    except Exception as exc:
        manifest = {
            "sistema": cfg.sistema,
            "version_objetivo": cfg.version_objetivo,
            "control": control_id,
            "tipo": "CICLO_CORRECTIVO",
            "estado_inicial": "ERROR",
            "estado_final": "ERROR",
            "rollback": False,
            "error": f"falló el diagnóstico inicial: {exc}",
            "evidencia": str(evidence.root),
        }
        evidence.write_json("manifest.json", manifest)
        return manifest

    evidence.write_json("baseline/resultados.json", baseline)
    estado_inicial = estado_control(baseline, control_id)

    manifest = {
        "sistema": cfg.sistema,
        "version_objetivo": cfg.version_objetivo,
        "control": control_id,
        "tipo": "CICLO_CORRECTIVO",
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

    if not correction_available(cfg, control_id):
        manifest["estado_final"] = "PENDIENTE_SIN_RECETA"
        manifest["motivo"] = (
            "El hallazgo fue detectado, pero el perfil no declara una receta "
            "automática segura para este control."
        )
        evidence.write_json("manifest.json", manifest)
        return manifest

    correccion: CorrectionResult | None = None

    try:
        correccion = apply_correction(cfg, control_id, target_root, evidence)
        evidence.write_json("cambios/correccion.json", correccion.as_dict())

        if reiniciar:
            reiniciar()

        verificacion = diagnosticar(cfg, target_root)
        evidence.write_json("verification/resultados.json", verificacion)
        estado_despues = estado_control(verificacion, control_id)

        if estado_despues == "SIN_HALLAZGO":
            manifest["estado_final"] = "CORREGIDO"
            evidence.write_json("manifest.json", manifest)
            return manifest

        _rollback_seguro(
            cfg, correccion, target_root, evidence, reiniciar, manifest
        )
        manifest["estado_final"] = (
            "NO_CORREGIDO" if estado_despues == "HALLAZGO" else "ERROR"
        )
        evidence.write_json("manifest.json", manifest)
        return manifest

    except Exception as exc:
        manifest["error"] = str(exc)
        manifest["estado_final"] = "ERROR"

        if correccion is not None:
            _rollback_seguro(
                cfg, correccion, target_root, evidence, reiniciar, manifest
            )

        evidence.write_json("manifest.json", manifest)
        return manifest


def corregir_controles(
    cfg: ConfigObjetivo,
    control_ids: Iterable[str],
    target_root: str | Path,
    *,
    evidence_base: str | Path = "evidencias",
    reiniciar: Callable[[], None] | None = None,
) -> list[dict]:
    """Procesa todos los controles indicados sin omitir los que no tienen receta."""
    vistos: set[str] = set()
    resultados: list[dict] = []

    for control_id in control_ids:
        if control_id in vistos:
            continue
        vistos.add(control_id)

        try:
            resultado = ciclo_correctivo(
                cfg,
                control_id,
                target_root,
                evidence_base=evidence_base,
                reiniciar=reiniciar,
            )
        except Exception as exc:
            resultado = {
                "sistema": cfg.sistema,
                "version_objetivo": cfg.version_objetivo,
                "control": control_id,
                "tipo": "CICLO_CORRECTIVO",
                "estado_final": "ERROR",
                "error": str(exc),
                "evidencia": None,
            }

        resultados.append(resultado)

    return resultados


def rollback_desde_evidencia(
    evidence_dir: str | Path,
    target_root: str | Path,
    *,
    reiniciar: Callable[[], None] | None = None,
) -> dict:
    """Restaura manualmente el backup de una sesión correctiva confirmada."""
    root = Path(evidence_dir).resolve()
    correction_path = root / "cambios" / "correccion.json"
    if not correction_path.exists():
        raise FileNotFoundError(
            f"No existe una corrección reversible en {correction_path}"
        )

    data = json.loads(correction_path.read_text(encoding="utf-8"))
    result = CorrectionResult(**data)
    rollback(result, target_root)

    if reiniciar:
        reiniciar()

    archivo = (Path(target_root).resolve() / result.archivo).resolve()
    hash_restaurado = sha256_file(archivo)
    restauracion_ok = hash_restaurado == result.before_hash

    payload = {
        "control": result.control_id,
        "archivo": result.archivo,
        "rollback_manual": True,
        "hash_esperado": result.before_hash,
        "hash_restaurado": hash_restaurado,
        "restauracion_ok": restauracion_ok,
        "evidencia": str(root),
    }
    verification = root / "verification"
    verification.mkdir(parents=True, exist_ok=True)
    (verification / "manual_rollback.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
