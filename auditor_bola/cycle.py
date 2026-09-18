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
    receta = cfg.correccion_por_control(control_id)

    try:
        correccion = apply_correction(cfg, control_id, target_root, evidence)
        evidence.write_json("cambios/correccion.json", correccion.as_dict())

        if receta and receta.requiere_reinicio and reiniciar is None:
            rollback(correccion, target_root)
            manifest["rollback"] = True
            manifest["estado_final"] = "REQUIERE_REINICIO"
            manifest["motivo"] = (
                "La receta fue aplicada a la copia local, pero este control "
                "requiere reiniciar el objetivo antes de verificar. El cambio "
                "se revirtió para no dejar el proyecto en un estado parcial."
            )
            evidence.write_json("manifest.json", manifest)
            return manifest

        if reiniciar:
            reiniciar()

        verificacion = diagnosticar(cfg, target_root)
        evidence.write_json("verification/resultados.json", verificacion)
        estado_despues = estado_control(verificacion, control_id)
        manifest["estado_despues"] = estado_despues

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


def listar_sesiones_correccion(
    evidence_base: str | Path,
) -> list[Path]:
    """Lista sesiones con corrección, de la más reciente a la más antigua."""
    base = Path(evidence_base).resolve()
    if not base.exists():
        return []
    sesiones = [
        path
        for path in base.iterdir()
        if path.is_dir() and (path / "cambios" / "correccion.json").exists()
    ]
    return sorted(sesiones, key=lambda path: path.name, reverse=True)


def controles_desde_evidencias(
    evidence_base: str | Path,
) -> list[str]:
    """Obtiene controles únicos presentes en sesiones correctivas."""
    controles: list[str] = []
    for session in listar_sesiones_correccion(evidence_base):
        try:
            data = json.loads(
                (session / "cambios" / "correccion.json").read_text(
                    encoding="utf-8"
                )
            )
            control = data.get("control_id")
            if control and control not in controles:
                controles.append(control)
        except Exception:
            continue
    return controles


def rollback_todas_desde_evidencias(
    evidence_base: str | Path,
    target_root: str | Path,
    *,
    reiniciar: Callable[[], None] | None = None,
) -> dict:
    """Revierte todas las correcciones aplicables, en orden inverso.

    Seguridad:
    - Si el hash actual coincide con after_hash, restaura el backup.
    - Si coincide con before_hash, la sesión ya está revertida.
    - Si no coincide con ninguno, no sobrescribe el archivo.
    """
    base = Path(evidence_base).resolve()
    root = Path(target_root).resolve()
    sesiones = listar_sesiones_correccion(base)

    resultados: list[dict] = []
    hubo_cambios = False

    for session in sesiones:
        correction_path = session / "cambios" / "correccion.json"
        try:
            data = json.loads(correction_path.read_text(encoding="utf-8"))
            correction = CorrectionResult(**data)
            archivo = (root / correction.archivo).resolve()

            if archivo != root and root not in archivo.parents:
                raise ValueError("ruta de rollback fuera del target_root")
            if not archivo.exists():
                raise FileNotFoundError(archivo)

            current_hash = sha256_file(archivo)

            if current_hash == correction.before_hash:
                estado = "YA_REVERTIDA"
                restored_hash = current_hash

            elif current_hash == correction.after_hash:
                rollback(correction, root)
                restored_hash = sha256_file(archivo)
                if restored_hash == correction.before_hash:
                    estado = "REVERTIDA"
                    hubo_cambios = True
                else:
                    estado = "ERROR_HASH"

            else:
                estado = "CONFLICTO_HASH"
                restored_hash = current_hash

            payload = {
                "sesion": str(session),
                "control": correction.control_id,
                "archivo": correction.archivo,
                "estado": estado,
                "hash_actual_antes": current_hash,
                "hash_esperado_corregido": correction.after_hash,
                "hash_original": correction.before_hash,
                "hash_actual_despues": restored_hash,
            }

        except Exception as exc:
            payload = {
                "sesion": str(session),
                "estado": "ERROR",
                "error": str(exc),
            }

        resultados.append(payload)

        verification = session / "verification"
        verification.mkdir(parents=True, exist_ok=True)
        (verification / "rollback_total.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    reinicio_error = None
    if hubo_cambios and reiniciar:
        try:
            reiniciar()
        except Exception as exc:
            reinicio_error = str(exc)

    resumen = {
        "sesiones_encontradas": len(sesiones),
        "revertidas": sum(
            item.get("estado") == "REVERTIDA" for item in resultados
        ),
        "ya_revertidas": sum(
            item.get("estado") == "YA_REVERTIDA" for item in resultados
        ),
        "conflictos_hash": sum(
            item.get("estado") == "CONFLICTO_HASH" for item in resultados
        ),
        "errores": sum(
            item.get("estado") in {"ERROR", "ERROR_HASH"}
            for item in resultados
        ),
        "reinicio_error": reinicio_error,
        "resultados": resultados,
    }

    base.mkdir(parents=True, exist_ok=True)
    (base / "rollback_total_ultimo.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resumen
