import json

from auditor_bola.config import cargar_config


def test_carga_dos_pilares(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({
        "sistema": "x",
        "version_objetivo": "1",
        "base_url": "http://localhost",
        "cuentas": [],
        "endpoints": [],
        "chequeos_acceso": [{
            "id_control": "P1-RBAC-X",
            "nombre": "x",
            "cuenta": "u",
            "metodo": "GET",
            "ruta": "/x",
            "acceso_esperado": False
        }],
        "chequeos_pilar2": [{
            "id_control": "P2-X",
            "nombre": "x",
            "tipo": "http_status_policy",
            "codigos_seguros": [403]
        }]
    }), encoding="utf-8")

    cfg = cargar_config(path)
    assert cfg.version_objetivo == "1"
    assert cfg.chequeos_acceso[0].id_control == "P1-RBAC-X"
    assert cfg.chequeos_pilar2[0].codigos_seguros == (403,)
