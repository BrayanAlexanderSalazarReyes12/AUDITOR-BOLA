import json

import auditor_bola.profile_builder as profile_builder
from auditor_bola.profile_builder import (
    build_profile_draft,
    detect_project,
    detect_runtime_profile,
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
    assert profile["base_url"] == ""
    assert profile["runtime"]["base_url"] == ""
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


def test_detecta_laravel_y_ruta_php(tmp_path):
    (tmp_path / "composer.json").write_text(
        json.dumps({"require": {"laravel/framework": "^11.0"}}),
        encoding="utf-8",
    )
    (tmp_path / "artisan").write_text("", encoding="utf-8")
    routes = tmp_path / "routes"
    routes.mkdir()
    (routes / "web.php").write_text(
        "Route::get('/orders/{id}', controller);\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)

    assert "php" in detection.languages
    assert "laravel" in detection.frameworks
    assert detection.runtime["comando_inicio"][:3] == ["php", "artisan", "serve"]
    assert any(route.path == "/orders/{id}" for route in detection.routes)


def test_detecta_rust_y_runtime_cargo(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        "[package]\nname='demo'\n[dependencies]\naxum='0.7'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")

    detection = detect_project(tmp_path)

    assert "rust" in detection.languages
    assert "axum" in detection.frameworks
    assert detection.runtime["comando_inicio"] == ["cargo", "run"]


def test_stack_desconocido_no_se_rechaza_y_usa_external(tmp_path):
    (tmp_path / "main.custom").write_text("demo", encoding="utf-8")

    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)

    assert profile["runtime"]["modo"] == "external"
    assert profile["sistema"]


def test_detecta_cuentas_en_seed_json(tmp_path):
    seed = tmp_path / "data" / "users.json"
    seed.parent.mkdir()
    seed.write_text(
        json.dumps({
            "users": [
                {
                    "username": "admin",
                    "password": "admin123",
                    "role": "ADMIN",
                },
                {
                    "usuario": "operador",
                    "clave": "demo456",
                    "rol": "OPERADOR",
                },
            ]
        }),
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)

    by_user = {
        item["username"]: item
        for item in profile["cuentas"]
    }
    assert by_user["admin"]["password"] == "admin123"
    assert by_user["admin"]["role"] == "ADMIN"
    assert by_user["operador"]["role"] == "OPERADOR"
    assert "ADMIN" in profile["roles_privilegiados"]
    assert len(
        profile["metadata_detectada"]["cuentas_candidatas"]
    ) >= 2


def test_detecta_cuenta_en_insert_sql(tmp_path):
    sql = tmp_path / "db" / "seed.sql"
    sql.parent.mkdir()
    sql.write_text(
        "INSERT INTO usuarios "
        "(username, password, role) "
        "VALUES ('auditor', 'clave123', 'ADMIN');\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)

    assert any(
        item["username"] == "auditor"
        and item["password"] == "clave123"
        for item in detection.accounts
    )


def test_detecta_cuenta_en_env_y_ignora_dependencias(tmp_path):
    (tmp_path / ".env.local").write_text(
        'USERNAME="localuser"\n'
        'PASSWORD="localpass"\n'
        'ROLE="USER"\n',
        encoding="utf-8",
    )
    ignored = tmp_path / "node_modules" / "demo"
    ignored.mkdir(parents=True)
    (ignored / "users.json").write_text(
        json.dumps({
            "username": "dependency-user",
            "password": "should-not-appear",
            "role": "ADMIN",
        }),
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    usernames = {item["username"] for item in detection.accounts}

    assert "localuser" in usernames
    assert "dependency-user" not in usernames


def test_endpoint_inventory_no_se_limita_a_300(tmp_path):
    routes = tmp_path / "routes.js"
    routes.write_text(
        "\n".join(
            f"app.get('/api/items/{index}', handler);"
            for index in range(350)
        ),
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)

    assert len(detection.routes) >= 350
    assert len(profile["endpoints_detectados"]) >= 350
    assert (
        profile["metadata_detectada"]["total_endpoints_detectados"]
        >= 350
    )


def test_spring_combina_prefijo_de_controlador(tmp_path):
    source = tmp_path / "src" / "UserController.java"
    source.parent.mkdir()
    source.write_text(
        '@RestController\n'
        '@RequestMapping("/api/users")\n'
        'public class UserController {\n'
        '  @GetMapping("/{id}")\n'
        '  public Object get() { return null; }\n'
        '  @PostMapping\n'
        '  public Object create() { return null; }\n'
        '}\n',
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    routes = {(r.method, r.path) for r in detection.routes}

    assert ("GET", "/api/users/{id}") in routes
    assert ("POST", "/api/users") in routes


def test_servlet_annotation_y_web_xml_entran_al_inventario(tmp_path):
    servlet = tmp_path / "src" / "ApiServlet.java"
    servlet.parent.mkdir()
    servlet.write_text(
        '@WebServlet(urlPatterns={"/api/a", "/api/b"})\n'
        'public class ApiServlet {}\n',
        encoding="utf-8",
    )
    webxml = tmp_path / "src" / "main" / "webapp" / "WEB-INF" / "web.xml"
    webxml.parent.mkdir(parents=True)
    webxml.write_text(
        '<web-app><servlet-mapping>'
        '<servlet-name>Legacy</servlet-name>'
        '<url-pattern>/legacy/*</url-pattern>'
        '</servlet-mapping></web-app>',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    paths = {item["ruta"] for item in profile["endpoints_detectados"]}

    assert "/api/a" in paths
    assert "/api/b" in paths
    assert "/legacy/*" in paths


def test_aspnet_y_nextjs_se_detectan(tmp_path):
    controller = tmp_path / "Controllers" / "OrdersController.cs"
    controller.parent.mkdir()
    controller.write_text(
        '[Route("api/[controller]")]\n'
        'public class OrdersController {\n'
        ' [HttpGet("{id}")] public object Get() => null;\n'
        '}\n',
        encoding="utf-8",
    )

    route = tmp_path / "app" / "api" / "health" / "route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        'export async function GET() {}\n'
        'export async function POST() {}\n',
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    routes = {(r.method, r.path) for r in detection.routes}

    assert ("GET", "/api/Orders/{id}") in routes
    assert ("GET", "/api/health") in routes
    assert ("POST", "/api/health") in routes


def test_referencias_fetch_y_formulario_apoyan_descubrimiento(tmp_path):
    page = tmp_path / "web" / "page.jsp"
    page.parent.mkdir()
    page.write_text(
        '<form method="post" action="/auth/login"></form>\n'
        '<script>fetch("/api/profile", {method: "PATCH"});</script>\n',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    routes = {
        (item["metodo"], item["ruta"])
        for item in profile["endpoints_detectados"]
    }

    assert ("POST", "/auth/login") in routes
    assert ("PATCH", "/api/profile") in routes


def test_openapi_yaml_se_incorpora_al_json(tmp_path):
    spec = tmp_path / "openapi.yaml"
    spec.write_text(
        'openapi: 3.0.0\n'
        'paths:\n'
        '  /api/orders:\n'
        '    get:\n'
        '      responses: {}\n'
        '    post:\n'
        '      responses: {}\n',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    routes = {
        (item["metodo"], item["ruta"])
        for item in profile["endpoints_detectados"]
    }

    assert ("GET", "/api/orders") in routes
    assert ("POST", "/api/orders") in routes


def test_readme_md_aporta_cuentas_y_endpoints(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Manual de pruebas\n\n"
        "Usuario: qa.admin\n"
        "Contraseña: qa-secret\n"
        "Rol: ADMIN\n\n"
        "GET /api/usuarios\n"
        "POST https://localhost:8080/api/login\n"
        "curl -X PATCH https://localhost:8080/api/profile\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)

    by_user = {
        item["username"]: item
        for item in profile["cuentas"]
    }
    assert by_user["qa.admin"]["password"] == "qa-secret"
    assert by_user["qa.admin"]["role"] == "ADMIN"

    routes = {
        (item["metodo"], item["ruta"])
        for item in profile["endpoints_detectados"]
    }
    assert ("GET", "/api/usuarios") in routes
    assert ("POST", "/api/login") in routes
    assert ("PATCH", "/api/profile") in routes

    account_evidence = next(
        item
        for item in profile["metadata_detectada"]["cuentas_candidatas"]
        if item["username"] == "qa.admin"
    )
    assert account_evidence["tipo_fuente"] == "documentacion"

    endpoint = next(
        item
        for item in profile["endpoints_detectados"]
        if item["ruta"] == "/api/usuarios"
    )
    assert "documentacion" in endpoint["tipos_fuente"]


def test_tabla_markdown_de_usuarios_se_detecta(tmp_path):
    manual = tmp_path / "docs" / "usuarios.md"
    manual.parent.mkdir()
    manual.write_text(
        "| Usuario | Contraseña | Rol |\n"
        "| --- | --- | --- |\n"
        "| ana.vargas | clave-ana | analista |\n"
        "| bruno.mejia | clave-bruno | coordinador |\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    users = {
        item["username"]: item
        for item in detection.accounts
    }

    assert users["ana.vargas"]["password"] == "clave-ana"
    assert users["ana.vargas"]["role"] == "analista"
    assert users["bruno.mejia"]["role"] == "coordinador"


def test_archivo_textual_desconocido_tambien_se_escanea(tmp_path):
    notes = tmp_path / "deployment.runtimeinfo"
    notes.write_text(
        "usuario: deploy.user\n"
        "password: deploy-pass\n"
        "role: OPERADOR\n"
        "endpoint=/internal/sync\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert any(
        item["username"] == "deploy.user"
        for item in profile["cuentas"]
    )
    assert any(
        item["ruta"] == "/internal/sync"
        for item in profile["endpoints_detectados"]
    )


def test_postman_json_generico_aporta_endpoints(tmp_path):
    collection = tmp_path / "testing-collection.json"
    collection.write_text(
        json.dumps({
            "info": {"name": "Demo"},
            "item": [
                {
                    "name": "Detalle",
                    "request": {
                        "method": "DELETE",
                        "url": {
                            "raw": "http://localhost:8080/api/items/42"
                        },
                    },
                },
                {
                    "name": "Listado",
                    "request": {
                        "method": "GET",
                        "url": "/api/items",
                    },
                },
            ],
        }),
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    routes = {
        (item["metodo"], item["ruta"])
        for item in profile["endpoints_detectados"]
    }

    assert ("DELETE", "/api/items/42") in routes
    assert ("GET", "/api/items") in routes


def test_archivo_binario_desconocido_no_se_interpreta_como_texto(tmp_path):
    binary = tmp_path / "blob.custom"
    binary.write_bytes(
        b"GET /api/falso\x00usuario: hacker\x00password: no"
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert not any(
        item["ruta"] == "/api/falso"
        for item in profile["endpoints_detectados"]
    )
    assert not any(
        item["username"] == "hacker"
        for item in profile["cuentas"]
    )


def test_markdown_bold_labels_detectan_cuenta(tmp_path):
    manual = tmp_path / "MANUAL_ACCESO.md"
    manual.write_text(
        "- **Usuario:** soporte.demo\n"
        "- **Contraseña:** soporte-123\n"
        "- **Rol:** SOPORTE\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    by_user = {
        item["username"]: item
        for item in detection.accounts
    }

    assert by_user["soporte.demo"]["password"] == "soporte-123"
    assert by_user["soporte.demo"]["role"] == "SOPORTE"


def test_detecta_version_desde_package_json(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "demo-app",
            "version": "2.7.4",
            "dependencies": {"express": "4.18.2"},
        }),
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)

    assert detection.version == "2.7.4"
    assert detection.version_source == "package.json"
    assert profile["version_objetivo"] == "2.7.4"
    assert profile["metadata_detectada"]["version_detectada"] == "2.7.4"


def test_detecta_version_maven_directa_y_no_dependencia(tmp_path):
    (tmp_path / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        '<modelVersion>4.0.0</modelVersion>'
        '<groupId>com.demo</groupId>'
        '<artifactId>demo</artifactId>'
        '<version>3.4.1</version>'
        '<dependencies>'
        '<dependency>'
        '<groupId>x</groupId>'
        '<artifactId>y</artifactId>'
        '<version>99.99.99</version>'
        '</dependency>'
        '</dependencies>'
        '</project>',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "3.4.1"
    assert profile["metadata_detectada"]["version_fuente"] == "pom.xml"


def test_detecta_version_maven_por_propiedad_revision(tmp_path):
    (tmp_path / "pom.xml").write_text(
        '<project>'
        '<modelVersion>4.0.0</modelVersion>'
        '<version>${revision}</version>'
        '<properties><revision>5.2.0-SNAPSHOT</revision></properties>'
        '</project>',
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)

    assert detection.version == "5.2.0-SNAPSHOT"


def test_detecta_version_desde_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\n'
        'name = "demo"\n'
        'version = "1.8.3"\n',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "1.8.3"
    assert profile["metadata_detectada"]["version_fuente"] == "pyproject.toml"


def test_detecta_version_desde_gradle(tmp_path):
    (tmp_path / "build.gradle").write_text(
        "plugins { id 'java' }\n"
        "version = '4.6.2'\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "4.6.2"


def test_detecta_version_desde_readme_como_fallback(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Demo\n\n"
        "Versión actual: v6.1.0\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "6.1.0"
    assert profile["metadata_detectada"]["version_fuente"] == "README.md"
    assert profile["metadata_detectada"]["version_confianza"] == "media"


def test_sin_version_no_inventa_1_0_0(tmp_path):
    (tmp_path / "main.custom").write_text(
        "aplicacion sin version declarada",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "desconocida"
    assert profile["metadata_detectada"]["version_detectada"] is None


def test_version_explicita_sobrescribe_la_detectada(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "demo",
            "version": "2.0.0",
        }),
        encoding="utf-8",
    )

    profile = build_profile_draft(
        detect_project(tmp_path),
        version="9.9.9",
    )

    assert profile["version_objetivo"] == "9.9.9"


def test_detecta_version_en_application_properties(tmp_path):
    props = tmp_path / "src" / "main" / "resources" / "application.properties"
    props.parent.mkdir(parents=True)
    props.write_text(
        "info.app.version=7.3.2\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "7.3.2"
    assert (
        profile["metadata_detectada"]["version_fuente"]
        == "src/main/resources/application.properties"
    )


def test_detecta_version_en_constante_python(tmp_path):
    (tmp_path / "__version__.py").write_text(
        '__version__ = "8.0.1"\n',
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))

    assert profile["version_objetivo"] == "8.0.1"


def test_docker_compose_conserva_runtime_nativo_como_alternativa(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_builder,
        "_docker_available_on_host",
        lambda: True,
    )
    (tmp_path / "compose.yml").write_text(
        "services:\n  app:\n    image: demo\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps({
            "name": "demo",
            "version": "1.2.3",
            "scripts": {"start": "node server.js"},
            "dependencies": {"express": "4.18.2"},
        }),
        encoding="utf-8",
    )
    (tmp_path / "server.js").write_text(
        "console.log('demo');\n",
        encoding="utf-8",
    )

    detection = detect_project(tmp_path)
    runtime = detection.runtime

    assert runtime["nombre"] == "Docker Compose"
    assert runtime["comando_inicio"][0] == "docker"
    assert runtime["base_url"] == "http://127.0.0.1:3000"
    assert len(runtime["alternativas"]) == 1

    native = runtime["alternativas"][0]
    assert native["nombre"] == "Node.js (npm)"
    assert native["comando_inicio"] == ["npm", "start"]
    assert native["base_url"] == "http://127.0.0.1:3000"



def test_docker_compose_detecta_puerto_publicado(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_builder,
        "_docker_available_on_host",
        lambda: True,
    )
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  app:\n"
        "    image: demo\n"
        "    ports:\n"
        "      - \"8088:5000\"\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\napp.run(port=5000)\n",
        encoding="utf-8",
    )

    runtime, base_url = detect_runtime_profile(tmp_path)

    assert runtime["nombre"] == "Docker Compose"
    assert runtime["base_url"] == "http://127.0.0.1:8088"
    assert base_url == "http://127.0.0.1:8088"


def test_flask_run_py_detecta_puerto_explicito(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\n"
        "app.run(host='127.0.0.1', port=9090, debug=False)\n",
        encoding="utf-8",
    )

    runtime, base_url = detect_runtime_profile(tmp_path)

    assert runtime["comando_inicio"] == ["python", "run.py"]
    assert runtime["base_url"] == "http://127.0.0.1:9090"
    assert base_url == "http://127.0.0.1:9090"



def test_perfil_json_expone_plan_de_ejecucion_local(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        profile_builder,
        "_docker_available_on_host",
        lambda: True,
    )
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  app:\n"
        "    image: demo\n"
        "    ports:\n"
        "      - \"8080:5000\"\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\napp.run(port=5000)\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    runtime = profile["runtime"]
    plan = profile["metadata_detectada"]["plan_ejecucion"]

    assert runtime["preferencia_arranque"] == "contenedor"
    assert runtime["permitir_fallback_local"] is True
    assert runtime["nombre"] == "Docker Compose"
    assert runtime["alternativas"][0]["nombre"] == "Python"
    assert plan["principal"]["comando_inicio"][0] == "docker"
    assert plan["alternativas"][0]["comando_inicio"] == [
        "python",
        "run.py",
    ]



def test_flask_run_py_sin_puerto_no_inventa_5000(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\n"
        "from config import PORT\n"
        "app.run(port=PORT)\n",
        encoding="utf-8",
    )

    runtime, base_url = detect_runtime_profile(tmp_path)

    assert runtime["nombre"] == "Python"
    assert runtime["comando_inicio"] == ["python", "run.py"]
    assert runtime["base_url"] == ""
    assert base_url == ""



def test_sin_docker_json_prioriza_python_local(tmp_path, monkeypatch):
    monkeypatch.setattr(
        profile_builder,
        "_docker_available_on_host",
        lambda: False,
    )
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  app:\n"
        "    image: demo\n"
        "    ports:\n"
        "      - \"5050:5050\"\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\n"
        "app.run(host='127.0.0.1', port=5050)\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    runtime = profile["runtime"]
    environment = profile["metadata_detectada"]["entorno_ejecucion"]

    assert runtime["nombre"] == "Python"
    assert runtime["preferencia_arranque"] == "local"
    assert runtime["comando_inicio"] == ["python", "run.py"]
    assert runtime["base_url"] == "http://127.0.0.1:5050"
    assert runtime["alternativas"][0]["nombre"] == "Docker Compose"
    assert profile["base_url"] == "http://127.0.0.1:5050"
    assert environment["docker_instalado"] is False
    assert environment["runtime_principal"] == "Python"


def test_con_docker_json_prioriza_compose(tmp_path, monkeypatch):
    monkeypatch.setattr(
        profile_builder,
        "_docker_available_on_host",
        lambda: True,
    )
    (tmp_path / "compose.yml").write_text(
        "services:\n"
        "  app:\n"
        "    image: demo\n"
        "    ports:\n"
        "      - \"8088:5000\"\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\napp.run(port=5000)\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    runtime = profile["runtime"]
    environment = profile["metadata_detectada"]["entorno_ejecucion"]

    assert runtime["nombre"] == "Docker Compose"
    assert runtime["preferencia_arranque"] == "contenedor"
    assert runtime["base_url"] == "http://127.0.0.1:8088"
    assert runtime["alternativas"][0]["nombre"] == "Python"
    assert environment["docker_instalado"] is True
    assert environment["runtime_principal"] == "Docker Compose"



def test_autoperfil_infiere_controles_p2_de_alta_confianza(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "Flask==3.1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "run.py").write_text(
        "from app import app\n"
        "app.run(port=5050)\n",
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "import os\n"
        "from flask import Flask, request\n"
        "app = Flask(__name__)\n"
        "SECRET_KEY=os.getenv(\"APP_SECRET\", \"dev-secret\")\n"
        "@app.get('/health')\n"
        "def health(): return 'ok'\n"
        "@app.after_request\n"
        "def cors(response):\n"
        "    origin = request.headers.get(\"Origin\")\n"
        "    if origin:\n"
        "        response.headers[\"Access-Control-Allow-Origin\"] = origin\n"
        "        response.headers[\"Access-Control-Allow-Credentials\"] = \"true\"\n"
        "    return response\n",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nUSER root\n",
        encoding="utf-8",
    )

    profile = build_profile_draft(detect_project(tmp_path))
    checks = {
        item["id_control"]: item
        for item in profile["chequeos_pilar2"]
    }

    assert "P2-AUTO-CORS-001" in checks
    assert checks["P2-AUTO-CORS-001"]["ruta"] == "/health"
    assert "P2-AUTO-SECRET-001" in checks
    assert checks["P2-AUTO-SECRET-001"]["archivo"] == "app.py"
    assert "P2-AUTO-DOCKER-001" in checks
    assert profile["metadata_detectada"]["total_controles_activos"] == 3
