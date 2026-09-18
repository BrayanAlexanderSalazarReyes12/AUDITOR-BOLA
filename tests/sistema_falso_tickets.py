"""Sistema de prueba #2: tickets de soporte, CORRECTAMENTE protegido.

Sirve como control negativo: si el motor marcara BOLA aquí, sería un
falso positivo y el motor estaría mal. Nombres de campo distintos otra
vez (ticket_id, creado_por, agente) para seguir probando genericidad.
"""

from __future__ import annotations

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash


def crear_app_tickets() -> Flask:
    app = Flask("tickets_falso")

    USUARIOS = {
        "cliente1": {"password": generate_password_hash("pass1"), "role": "cliente"},
        "cliente2": {"password": generate_password_hash("pass2"), "role": "cliente"},
        "agente_soporte": {"password": generate_password_hash("agentepass"), "role": "agente"},
    }

    TICKETS = {
        10: {"ticket_id": 10, "creado_por": "cliente1", "asunto": "No me llega el correo"},
        11: {"ticket_id": 11, "creado_por": "cliente2", "asunto": "Factura duplicada"},
    }

    def usuario_actual():
        auth = request.authorization
        if not auth:
            return None
        u = USUARIOS.get(auth.username)
        if not u or not check_password_hash(u["password"], auth.password):
            return None
        return {"username": auth.username, "role": u["role"]}

    @app.get("/tickets/<int:ticket_id>")
    def ver_ticket(ticket_id):
        u = usuario_actual()
        if not u:
            return jsonify(error="no autenticado"), 401
        ticket = TICKETS.get(ticket_id)
        if not ticket:
            return jsonify(error="no existe"), 404
        # CORRECTO: valida propiedad o rol agente
        if u["role"] != "agente" and u["username"] != ticket["creado_por"]:
            return jsonify(error="prohibido"), 403
        return jsonify(ticket)

    @app.patch("/tickets/<int:ticket_id>")
    def editar_ticket(ticket_id):
        u = usuario_actual()
        if not u:
            return jsonify(error="no autenticado"), 401
        ticket = TICKETS.get(ticket_id)
        if not ticket:
            return jsonify(error="no existe"), 404
        if u["role"] != "agente" and u["username"] != ticket["creado_por"]:
            return jsonify(error="prohibido"), 403
        data = request.get_json(silent=True) or {}
        ticket.update({k: v for k, v in data.items() if k in ("asunto",)})
        return jsonify(ticket)

    return app


if __name__ == "__main__":
    crear_app_tickets().run(port=5101)
