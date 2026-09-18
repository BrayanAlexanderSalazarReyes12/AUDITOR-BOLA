"""Sistema de prueba #1: un 'blog' con posts privados por usuario.

Nombres de campo totalmente distintos a Tramitia (post_id, autor, editor)
a propósito, para demostrar que el motor no depende de ningún vocabulario
particular. Tiene un BOLA real e intencional en /posts/{id}.
"""

from __future__ import annotations

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash


def crear_app_blog() -> Flask:
    app = Flask("blog_falso")

    USUARIOS = {
        "juan": {"password": generate_password_hash("clave1"), "role": "editor"},
        "maria": {"password": generate_password_hash("clave2"), "role": "editor"},
        "admin_blog": {"password": generate_password_hash("adminpass"), "role": "admin"},
    }

    POSTS = {
        1: {"post_id": 1, "autor": "juan", "titulo": "Notas privadas de Juan"},
        2: {"post_id": 2, "autor": "maria", "titulo": "Borrador de Maria"},
    }

    def usuario_actual():
        auth = request.authorization
        if not auth:
            return None
        u = USUARIOS.get(auth.username)
        if not u or not check_password_hash(u["password"], auth.password):
            return None
        return {"username": auth.username, "role": u["role"]}

    @app.get("/posts/<int:post_id>")
    def ver_post(post_id):
        u = usuario_actual()
        if not u:
            return jsonify(error="no autenticado"), 401
        post = POSTS.get(post_id)
        if not post:
            return jsonify(error="no existe"), 404
        # BOLA A PROPOSITO: no verifica que u["username"] == post["autor"]
        return jsonify(post)

    @app.patch("/posts/<int:post_id>")
    def editar_post(post_id):
        u = usuario_actual()
        if not u:
            return jsonify(error="no autenticado"), 401
        post = POSTS.get(post_id)
        if not post:
            return jsonify(error="no existe"), 404
        # BOLA A PROPOSITO tambien en escritura
        data = request.get_json(silent=True) or {}
        post.update({k: v for k, v in data.items() if k in ("titulo",)})
        return jsonify(post)

    return app


if __name__ == "__main__":
    crear_app_blog().run(port=5100)
