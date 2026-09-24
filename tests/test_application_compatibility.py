import json
import threading

import pytest
import requests
from flask import Flask, jsonify, request, session, redirect
from werkzeug.serving import make_server

from auditor_bola.config import ConfigObjetivo, Cuenta, Endpoint
from auditor_bola.engine import auditar
from auditor_bola.evidence import EvidenceSession
from auditor_bola.profile_builder import detect_project, build_profile_draft, _account_from_mapping
from auditor_bola.seed_data import seed_records
from auditor_bola.transport import request_http, AuthenticationError


@pytest.fixture
def auth_server():
    app = Flask(__name__)
    app.secret_key = "test-only"

    @app.post("/context/login")
    def login():
        body = request.get_json(silent=True) or request.form
        if body.get("password") != "valid":
            return "invalid", 401
        session["username"] = body["username"]
        if request.is_json:
            return jsonify(token=body["username"])
        return redirect("/context/home")

    @app.get("/context/profile/1")
    def profile():
        user = session.get("username") or request.headers.get("Authorization", "").removeprefix("Bearer ")
        return (jsonify(username=user), 200) if user else ("denied", 401)

    @app.get("/context/redirect")
    def denied_redirect():
        return redirect("/context/home")

    @app.get("/context/home")
    def home():
        return "login page", 200

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/context"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.mark.parametrize("auth_type,encoding", [("session", "form"), ("login_bearer", "json")])
def test_login_uses_context_and_isolates_accounts(auth_server, auth_type, encoding):
    for username in ("alice", "bob", "alice"):
        account = Cuenta(username, "valid", "USER", auth_type=auth_type,
                         login={"ruta": "/login", "formato": encoding})
        response = request_http("GET", auth_server + "/profile/1", cuenta=account, base_url=auth_server)
        assert response.json() == {"username": username}
    account.password = "wrong"
    with pytest.raises(AuthenticationError):
        request_http("GET", auth_server + "/profile/1", cuenta=account, base_url=auth_server)


def test_redirect_is_not_followed(auth_server):
    assert request_http("GET", auth_server + "/redirect").status_code == 302


def test_unavailable_target_is_error_not_clean(monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("offline")
    monkeypatch.setattr("auditor_bola.engine.request_http", unavailable)
    cfg = ConfigObjetivo("demo", "http://127.0.0.1", [Cuenta("alice", "pw", "USER")],
                         [Endpoint("GET", "/profile/{id}", "1", "alice")])
    rows = auditar(cfg)
    assert rows[0].error
    assert not rows[0].confirmado_bola


def test_account_username_wins_over_email():
    account, _ = _account_from_mapping({"id": 1, "email": "other@lab.local", "username": "admin", "password": "pw"}, source="seed.sql", confidence="alta")
    assert account["username"] == "admin"


def test_sql_seed_reads_all_rows_and_java_literals():
    source = '''st.execute("CREATE TABLE USERS (ID INT, USERNAME VARCHAR(60), PASSWORD VARCHAR(120))");
    st.execute("INSERT INTO USERS VALUES " + "(1,'a','pa')," + "(2,'b','pb')");'''
    assert list(seed_records(source)) == [
        {"id": "1", "username": "a", "password": "pa"},
        {"id": "2", "username": "b", "password": "pb"},
    ]


def test_blueprint_mount_login_and_no_unrelated_bola(tmp_path):
    (tmp_path / "api.py").write_text('''from flask import Blueprint, request, session
bp = Blueprint("auth", __name__)
@bp.post("/login")
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    session["username"] = username
@bp.get("/profile/<int:user_id>")
def profile(user_id):
    return db.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
@bp.get("/download")
def download():
    return request.args.get("file")
''', encoding="utf-8")
    (tmp_path / "app.py").write_text('from api import bp as auth_bp\napp.register_blueprint(auth_bp, url_prefix="/api")')
    (tmp_path / "seed.sql").write_text("INSERT INTO users (id, username, password, role) VALUES (1,'a','pa','ADMIN'),(2,'b','pb','USER');")
    profile = build_profile_draft(detect_project(tmp_path))
    assert {a["auth_type"] for a in profile["cuentas"]} == {"session"}
    assert profile["cuentas"][0]["login"]["ruta"] == "/api/login"
    assert [ep["ruta"] for ep in profile["endpoints"]] == ["/api/profile/{id}"]


def test_express_mount_excludes_database_get(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"start": "node app.js"}}))
    (tmp_path / "auditor-package.json").write_text(json.dumps({"build": {"start": "npm start"}}))
    (tmp_path / "app.js").write_text("const accounts = require('./users'); app.use('/api', accounts);")
    (tmp_path / "users.js").write_text("router.get('/profile/:id', handler); db.get('SELECT * FROM users', callback);")
    detection = detect_project(tmp_path)
    assert [(route.method, route.path) for route in detection.routes] == [("GET", "/api/profile/:id")]
    assert detection.runtime["base_url"] == "http://127.0.0.1:3000"


def test_evidence_is_unique_even_with_frozen_clock(tmp_path, monkeypatch):
    monkeypatch.setattr("auditor_bola.evidence._timestamp", lambda: "same-time")
    assert len({EvidenceSession.create(tmp_path).root for _ in range(10)}) == 10
