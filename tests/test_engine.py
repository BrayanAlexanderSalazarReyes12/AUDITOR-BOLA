"""Pruebas del motor genérico contra dos sistemas simulados distintos.

Usa multiprocessing para levantar cada Flask falso en un puerto propio
durante la prueba, sin depender de que el usuario los arranque a mano.
"""

from __future__ import annotations

import time
import multiprocessing

import pytest

from auditor_bola.config import ConfigObjetivo, Cuenta, Endpoint
from auditor_bola.engine import auditar
from tests.sistema_falso_blog import crear_app_blog
from tests.sistema_falso_tickets import crear_app_tickets


def _correr_app(factory, puerto):
    factory().run(port=puerto)


@pytest.fixture(scope="module")
def blog_server():
    p = multiprocessing.Process(target=_correr_app, args=(crear_app_blog, 5200), daemon=True)
    p.start()
    time.sleep(1)
    yield "http://127.0.0.1:5200"
    p.terminate()


@pytest.fixture(scope="module")
def tickets_server():
    p = multiprocessing.Process(target=_correr_app, args=(crear_app_tickets, 5201), daemon=True)
    p.start()
    time.sleep(1)
    yield "http://127.0.0.1:5201"
    p.terminate()


def test_detecta_bola_real_en_blog(blog_server):
    cfg = ConfigObjetivo(
        sistema="blog_falso",
        base_url=blog_server,
        cuentas=[
            Cuenta("juan", "clave1", "editor"),
            Cuenta("maria", "clave2", "editor"),
        ],
        endpoints=[
            Endpoint("GET", "/posts/{id}", "1", "juan"),
        ],
    )
    hallazgos = auditar(cfg)
    confirmados = [h for h in hallazgos if h.confirmado_bola]
    assert len(confirmados) == 1
    assert confirmados[0].cuenta == "maria"


def test_no_da_falso_positivo_en_tickets(tickets_server):
    cfg = ConfigObjetivo(
        sistema="tickets_falso",
        base_url=tickets_server,
        cuentas=[
            Cuenta("cliente1", "pass1", "cliente"),
            Cuenta("cliente2", "pass2", "cliente"),
        ],
        endpoints=[
            Endpoint("GET", "/tickets/{id}", "10", "cliente1"),
        ],
    )
    hallazgos = auditar(cfg)
    confirmados = [h for h in hallazgos if h.confirmado_bola]
    assert len(confirmados) == 0


def test_rol_privilegiado_si_puede_acceder(blog_server):
    cfg = ConfigObjetivo(
        sistema="blog_falso",
        base_url=blog_server,
        cuentas=[Cuenta("maria", "clave2", "editor")],
        endpoints=[Endpoint("GET", "/posts/{id}", "1", "juan")],
        roles_privilegiados=["editor"],  # ahora SI se le permite
    )
    hallazgos = auditar(cfg)
    # acceso_esperado ahora es True por el rol, y accede -> no es BOLA
    assert hallazgos[0].acceso_esperado is True
    assert hallazgos[0].confirmado_bola is False
