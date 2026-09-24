"""CLI del Auditor Correctivo de Seguridad de Dos Pilares."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .config import cargar_config, construir_registro_pilar1
from .p1_resolver import resolve_live_bola_candidates
from .profile_builder import detect_project, build_profile_draft, save_profile_draft
from .cycle import ciclo_correctivo
from .evidence import EvidenceSession
from .process_manager import LocalTargetProcess
from .runner import diagnosticar


def _diagnose(args) -> int:
    cfg = cargar_config(args.config)
    proceso = None
    try:
        if args.manage_target:
            if not args.target_root:
                raise ValueError("--manage-target requiere --target-root")
            proceso = LocalTargetProcess(args.target_root, cfg.runtime, authorized_base_url=cfg.base_url)
            proceso.start()
        _resolve_live(cfg)
        resultado = diagnosticar(cfg, args.target_root)
    finally:
        if proceso:
            proceso.stop()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        evidence = EvidenceSession.create(args.evidence_dir)
        evidence.write_json("baseline/resultados.json", resultado)
        print(f"Evidencia: {evidence.root}")

    r = resultado["resumen"]
    print(f"Sistema: {cfg.sistema} {cfg.version_objetivo or ''}".strip())
    print(
        "Hallazgos: "
        f"BOLA={r['bola_confirmados']} | acceso={r['acceso_vulnerable']} | "
        f"agente={r['agente_vulnerable']} | "
        f"pilar2={r['pilar2_hallazgos']} | errores={r['errores']}"
    )
    total = (
        r["bola_confirmados"]
        + r["acceso_vulnerable"]
        + r["agente_vulnerable"]
        + r["pilar2_hallazgos"]
        + r.get("matriz_hallazgos", 0)
    )
    if r["errores"]:
        return 2
    return 1 if total else 0


def _resolve_live(cfg) -> None:
    cfg.endpoints.extend(resolve_live_bola_candidates(cfg, {"candidatos_pilar1": cfg.candidatos_pilar1}))
    cfg.chequeos_pilar1 = construir_registro_pilar1(cfg.endpoints, cfg.chequeos_acceso, cfg.chequeos_agente)


def _autoconfig(args) -> int:
    profile = build_profile_draft(detect_project(args.target_root), base_url=args.base_url)
    destination = Path(args.out)
    if destination.exists() and not args.force:
        raise ValueError("El perfil ya existe; use otro --out o --force para reemplazarlo")
    save_profile_draft(profile, destination)
    if args.resolve_live:
        cfg = cargar_config(destination)
        _resolve_live(cfg)
        profile["endpoints"] = [asdict(endpoint) for endpoint in cfg.endpoints]
        profile["chequeos_pilar1"] = cfg.chequeos_pilar1
        save_profile_draft(profile, destination)
    print(f"Perfil: {destination.resolve()}")
    return 0


def _correct(args) -> int:
    cfg = cargar_config(args.config)
    proceso = None
    reiniciar = None

    if args.manage_target:
        proceso = LocalTargetProcess(args.target_root, cfg.runtime, authorized_base_url=cfg.base_url)

    try:
        if proceso:
            proceso.start()
            reiniciar = proceso.restart
        manifest = ciclo_correctivo(
            cfg,
            args.control,
            args.target_root,
            evidence_base=args.evidence_dir,
            reiniciar=reiniciar,
        )
    finally:
        if proceso:
            proceso.stop()

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if manifest["estado_final"] in {"CORREGIDO", "SIN_HALLAZGO"} else 1


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Auditor Correctivo de Seguridad de Dos Pilares"
    )
    sub = ap.add_subparsers(dest="command", required=True)

    auto = sub.add_parser("autoconfig", help="detecta el proyecto y genera un perfil")
    auto.add_argument("--target-root", required=True)
    auto.add_argument("--out", required=True)
    auto.add_argument("--base-url", help="URL del objetivo, incluido el contexto del WAR")
    auto.add_argument("--resolve-live", action="store_true", help="resuelve propiedad contra el objetivo iniciado")
    auto.add_argument("--force", action="store_true", help="reemplaza el perfil de salida existente")
    auto.set_defaults(func=_autoconfig)

    diag = sub.add_parser("diagnose", help="diagnostica Pilar 1 y Pilar 2")
    diag.add_argument("--config", required=True, help="perfil JSON del objetivo")
    diag.add_argument("--target-root", help="copia local del código objetivo")
    diag.add_argument("--out", help="JSON de salida")
    diag.add_argument("--evidence-dir", default="evidencias")
    diag.add_argument("--manage-target", action="store_true", help="inicia el objetivo local durante el diagnóstico")
    diag.set_defaults(func=_diagnose)

    corr = sub.add_parser("correct", help="aplica y verifica una corrección")
    corr.add_argument("--config", required=True, help="perfil JSON del objetivo")
    corr.add_argument("--control", required=True)
    corr.add_argument("--target-root", required=True)
    corr.add_argument("--evidence-dir", default="evidencias")
    corr.add_argument(
        "--manage-target",
        action="store_true",
        help="inicia/reinicia el objetivo usando runtime del perfil JSON",
    )
    corr.set_defaults(func=_correct)

    args = ap.parse_args()
    try:
        code = args.func(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
