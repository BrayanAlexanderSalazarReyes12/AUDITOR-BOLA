from auditor_bola.security_semantics import (
    infer_object_identity,
    route_parameter_name,
)


def test_infiere_codigo_y_creador_anidado_sin_nombres_tramitia():
    item = {
        "codigo": 57,
        "creador": {
            "login": "ana.vargas",
        },
        "titulo": "demo",
    }

    evidence = infer_object_identity(
        item,
        {"ana.vargas", "bruno.mejia"},
    )

    assert evidence is not None
    assert evidence["id_prueba"] == "57"
    assert evidence["propietario_esperado"] == "ana.vargas"
    assert evidence["campo_id"] == "codigo"
    assert evidence["campo_propietario"] == "creador.login"


def test_parametro_de_ruta_tiene_prioridad_para_identificador():
    item = {
        "id": 999,
        "ticket_id": 14,
        "author": "bruno.mejia",
    }

    evidence = infer_object_identity(
        item,
        {"bruno.mejia"},
        route_parameter="ticket_id",
    )

    assert evidence is not None
    assert evidence["id_prueba"] == "14"
    assert evidence["campo_id"] == "ticket_id"


def test_no_confunde_assigned_to_con_propietario():
    item = {
        "id": 7,
        "assigned_to": "ana.vargas",
    }

    assert (
        infer_object_identity(
            item,
            {"ana.vargas"},
        )
        is None
    )


def test_extrae_parametro_de_rutas_de_varios_frameworks():
    assert route_parameter_name("/items/<int:item_id>") == "item_id"
    assert route_parameter_name("/items/{recordId}") == "recordid"
    assert route_parameter_name("/items/:uuid") == "uuid"
