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


def test_carga_correccion_que_requiere_reinicio(tmp_path):
    path = tmp_path / "cfg-restart.json"
    path.write_text(json.dumps({
        "sistema": "x",
        "base_url": "",
        "cuentas": [],
        "endpoints": [],
        "correcciones": [{
            "control_id": "P1-X",
            "archivo": "src/app.py",
            "requiere_reinicio": True,
            "operaciones": [{
                "estrategia": "replace_exact",
                "buscar": "a",
                "reemplazar": "b"
            }]
        }]
    }), encoding="utf-8")

    cfg = cargar_config(path)
    assert cfg.correcciones[0].requiere_reinicio is True


def test_carga_runtime_multiplataforma(tmp_path):
    path = tmp_path / "cfg-runtime.json"
    path.write_text(json.dumps({
        "sistema": "moodle-demo",
        "base_url": "http://localhost:8080",
        "cuentas": [],
        "endpoints": [],
        "runtime": {
            "modo": "service",
            "comando_inicio": ["docker", "compose", "up", "-d"],
            "comando_detener": ["docker", "compose", "down"],
            "comando_inicio_por_so": {
                "windows": ["docker", "compose", "up", "-d"],
                "linux": ["docker", "compose", "up", "-d"],
                "macos": ["docker", "compose", "up", "-d"]
            }
        }
    }), encoding="utf-8")

    cfg = cargar_config(path)
    assert cfg.runtime.modo == "service"
    assert cfg.runtime.comando_detener == ["docker", "compose", "down"]
    assert cfg.runtime.comando_inicio_por_so["windows"][0] == "docker"



def test_carga_chequeos_pilar1_como_registro_canonico(tmp_path):
    path = tmp_path / "cfg-p1.json"
    path.write_text(json.dumps({
        "sistema": "x",
        "base_url": "http://127.0.0.1:5050",
        "cuentas": [
            {
                "username": "ana",
                "password": "x",
                "role": "analista"
            },
            {
                "username": "bob",
                "password": "x",
                "role": "analista"
            }
        ],
        "endpoints": [],
        "chequeos_acceso": [],
        "chequeos_agente": [],
        "chequeos_pilar1": [
            {
                "tipo": "bola",
                "id_control": "P1-BOLA-X",
                "nombre": "objeto ajeno",
                "metodo": "GET",
                "ruta": "/api/items/{id}",
                "id_prueba": "1",
                "propietario_esperado": "ana",
                "autogenerado": True,
                "confianza": "alta",
                "fuentes_evidencia": ["tests/fixtures/items.json"]
            },
            {
                "tipo": "acceso",
                "id_control": "P1-RBAC-X",
                "nombre": "admin restringido",
                "cuenta": "bob",
                "metodo": "GET",
                "ruta": "/api/admin",
                "acceso_esperado": False
            }
        ],
        "chequeos_pilar2": []
    }), encoding="utf-8")

    cfg = cargar_config(path)

    assert len(cfg.chequeos_pilar1) == 2
    assert len(cfg.endpoints) == 1
    assert cfg.endpoints[0].id_control == "P1-BOLA-X"
    assert cfg.endpoints[0].propietario_esperado == "ana"
    assert len(cfg.chequeos_acceso) == 1
    assert cfg.chequeos_acceso[0].id_control == "P1-RBAC-X"


def test_perfil_legacy_construye_registro_pilar1_en_memoria(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({
        "sistema": "legacy",
        "base_url": "http://localhost",
        "cuentas": [],
        "endpoints": [
            {
                "id_control": "P1-BOLA-LEGACY",
                "metodo": "GET",
                "ruta": "/items/{id}",
                "id_prueba": "7",
                "propietario_esperado": "ana"
            }
        ]
    }), encoding="utf-8")

    cfg = cargar_config(path)

    assert len(cfg.chequeos_pilar1) == 1
    assert cfg.chequeos_pilar1[0]["tipo"] == "bola"
    assert cfg.chequeos_pilar1[0]["id_control"] == "P1-BOLA-LEGACY"
