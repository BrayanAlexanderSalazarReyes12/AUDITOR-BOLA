"""CLI del Auditor Correctivo de Seguridad de Dos Pilares."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import cargar_config
from .cycle import ciclo_correctivo
from .evidence import EvidenceSession
from .process_manager import LocalTargetProcess
from .runner import diagnosticar


def _diagnose(args) -> int:
    cfg = cargar_config(args.config)
    resultado = diagnosticar(cfg, args.target_root)

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
    )
    return 1 if total else 0


def _correct(args) -> int:
    cfg = cargar_config(args.config)
    proceso = None
    reiniciar = None

    if args.manage_target:
        proceso = LocalTargetProcess(args.target_root, cfg.runtime)
        proceso.start()
        reiniciar = proceso.restart

    try:
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

    diag = sub.add_parser("diagnose", help="diagnostica Pilar 1 y Pilar 2")
    diag.add_argument("--config", required=True, help="perfil JSON del objetivo")
    diag.add_argument("--target-root", help="copia local del código objetivo")
    diag.add_argument("--out", help="JSON de salida")
    diag.add_argument("--evidence-dir", default="evidencias")
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
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
