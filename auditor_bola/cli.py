"""CLI: python -m auditor_bola.cli --config config/sistema.json --out reportes/evidencia.json"""

from __future__ import annotations

import argparse
import json
import sys

from .config import cargar_config
from .engine import auditar, auditar_alcance_agente


def main() -> None:
    ap = argparse.ArgumentParser(description="Auditor genérico de BOLA (Broken Object Level Authorization)")
    ap.add_argument("--config", required=True, help="ruta al YAML del sistema objetivo")
    ap.add_argument("--out", default="evidencia_bola.json", help="ruta del JSON de evidencia")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    hallazgos = auditar(cfg)
    confirmados = [h for h in hallazgos if h.confirmado_bola]

    hallazgos_agente = auditar_alcance_agente(cfg) if cfg.chequeos_agente else []
    vulnerables_agente = [h for h in hallazgos_agente if h.resultado.vulnerable]

    salida = {
        "sistema": cfg.sistema,
        "base_url": cfg.base_url,
        "total_pruebas": len(hallazgos),
        "bola_confirmados": len(confirmados),
        "hallazgos": [h.as_dict() for h in hallazgos],
        "chequeos_agente": [h.as_dict() for h in hallazgos_agente],
        "alcance_agente_vulnerable": len(vulnerables_agente),
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(f"Sistema: {cfg.sistema}")
    print(f"Pruebas BOLA ejecutadas: {len(hallazgos)}")
    print(f"BOLA confirmados: {len(confirmados)}")
    for h in confirmados:
        print(f"  ! {h.metodo} {h.endpoint} — {h.cuenta} ({h.rol}) accedió sin deberlo (HTTP {h.http_status})")

    if hallazgos_agente:
        print(f"\nChequeos de alcance del agente: {len(hallazgos_agente)}")
        for h in hallazgos_agente:
            r = h.resultado
            marca = "VULNERABLE" if r.vulnerable else "ok"
            print(f"  [{marca}] {h.nombre_chequeo} ({h.cuenta}): "
                  f"api_directa={r.cantidad_api_directa} agente={r.cantidad_agente} exceso={r.exceso}")

    print(f"\nEvidencia completa en: {args.out}")
    sys.exit(1 if (confirmados or vulnerables_agente) else 0)


if __name__ == "__main__":
    main()
