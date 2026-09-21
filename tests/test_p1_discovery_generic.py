from pathlib import Path

from auditor_bola.profile_builder import build_profile_draft, detect_project


def test_query_parameter_idor_and_db_owner_are_discovered(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        '''
from flask import request
def profile():
    user_id = request.args.get("id")
    return get_user(user_id)
''',
        encoding="utf-8",
    )
    (tmp_path / "db.py").write_text(
        '''
INSERT INTO users (id, username, password, role)
VALUES (1, 'admin', 'admin123', 'ADMIN');
INSERT INTO users (id, username, password, role)
VALUES (2, 'user', 'user123', 'USER');
''',
        encoding="utf-8",
    )
    detection = detect_project(tmp_path)
    profile = build_profile_draft(detection)
    bola = [
        item for item in profile["chequeos_pilar1"]
        if item.get("tipo") == "bola"
    ]
    assert bola
    assert any("?id={id}" in str(item.get("ruta")) for item in bola)


def test_java_servlet_get_is_materialized_as_get(tmp_path: Path):
    source = '''
import javax.servlet.annotation.WebServlet;
@WebServlet("/profile")
public class ProfileServlet {
    protected void doGet(javax.servlet.http.HttpServletRequest request,
                         javax.servlet.http.HttpServletResponse response) {}
}
'''
    (tmp_path / "ProfileServlet.java").write_text(source, encoding="utf-8")
    detection = detect_project(tmp_path)
    routes = {(r.method, r.path) for r in detection.routes}
    assert ("GET", "/profile") in routes
