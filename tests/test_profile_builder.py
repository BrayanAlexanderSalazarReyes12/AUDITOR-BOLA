import json

from auditor_bola.profile_builder import (
    build_profile_draft,
    detect_project,
    save_profile_draft,
)


def test_detecta_node_express_y_endpoints(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({
            "scripts": {"start": "node src/server.js"},
            "dependencies": {"express": "^4.0.0"},
        }),
        encoding="utf-8",
    )
    routes = tmp_path / "src" / "routes"
    routes.mkdir(parents=True)
    (routes / "users.js").write_text(
        "const router = require('express').Router();\n"
        "router.get('/api/users/:id', handler);\n"
        "router.post('/api/users', create);\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)

    assert "javascript" in detection.languages
    assert "express" in detection.frameworks
    assert detection.runtime["comando_inicio"] == ["npm", "start"]
    assert any(route.path == "/api/users/:id" for route in detection.routes)


def test_detecta_flask_y_runtime_python(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.0.0\nrequests==2.0.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\napp.run()\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n"
        "@app.get('/health')\n"
        "def health(): return 'ok'\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)

    assert "python" in detection.languages
    assert "flask" in detection.frameworks
    assert profile["base_url"] == "http://127.0.0.1:5000"
    assert profile["runtime"]["comando_inicio"] == ["python", "run.py"]
    assert any(
        item["ruta"] == "/health"
        for item in profile["metadata_detectada"]["endpoints_candidatos"]
    )


def test_descriptor_auditor_package_tiene_prioridad_para_arranque(tmp_path):
    (tmp_path / "auditor-package.json").write_text(
        json.dumps({
            "name": "Demo Port",
            "language": "java",
            "framework": ["servlet"],
            "build": {
                "install": "mvn clean package",
                "start": "java -jar app.jar",
            },
        }),
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)

    assert detection.name == "Demo Port"
    assert "java" in detection.languages
    assert "servlet" in detection.frameworks
    assert detection.runtime["comando_inicio"] == ["java", "-jar", "app.jar"]


def test_perfil_generado_es_json_persistible(tmp_path):
    project = tmp_path / "my-app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"dependencies": {"express": "4"}}),
        encoding="utf-8",
    )

    detection = detect_project(project)
    profile = build_profile_draft(
        detection,
        system_name="Mi Aplicación",
        version="2.0.0",
        base_url="http://127.0.0.1:4567",
    )

    out = save_profile_draft(profile, tmp_path / "config" / "mi-app.json")
    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["sistema"] == "mi-aplicacion"
    assert data["version_objetivo"] == "2.0.0"
    assert data["base_url"] == "http://127.0.0.1:4567"
    assert data["metadata_detectada"]["perfil_generado_automaticamente"] is True
