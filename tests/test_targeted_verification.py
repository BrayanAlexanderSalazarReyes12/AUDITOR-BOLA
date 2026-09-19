import auditor_bola.cycle as cycle


def _resultado(filas):
    return {"filas": filas}


def test_estado_control_filtra_fila_por_cuenta_metodo_y_ruta(monkeypatch):
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda resultado: resultado["filas"],
    )

    resultado = _resultado(
        [
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "cuenta": "lucia",
                "estado": "HALLAZGO",
            },
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "cuenta": "carlos",
                "estado": "SIN_HALLAZGO",
            },
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "GET",
                "ruta": "/reservas/{id}",
                "cuenta": "lucia",
                "estado": "SIN_HALLAZGO",
            },
        ]
    )

    selector = {
        "tipo_control": "bola",
        "metodo": "PATCH",
        "ruta": "/reservas/{id}",
        "cuenta": "lucia",
    }

    assert cycle.estado_control(resultado, "P1-BOLA") == "HALLAZGO"
    assert (
        cycle.estado_control(resultado, "P1-BOLA", selector)
        == "HALLAZGO"
    )

    resultado["filas"][0]["estado"] = "SIN_HALLAZGO"

    assert (
        cycle.estado_control(resultado, "P1-BOLA", selector)
        == "SIN_HALLAZGO"
    )


def test_detecta_regresion_en_fila_que_antes_estaba_segura(monkeypatch):
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda resultado: resultado["filas"],
    )

    baseline = _resultado(
        [
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "cuenta": "lucia",
                "estado": "HALLAZGO",
            },
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "cuenta": "carlos",
                "estado": "SIN_HALLAZGO",
            },
        ]
    )
    verification = _resultado(
        [
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "cuenta": "lucia",
                "estado": "SIN_HALLAZGO",
            },
            {
                "id": "P1-BOLA",
                "tipo_control": "bola",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "cuenta": "carlos",
                "estado": "HALLAZGO",
            },
        ]
    )

    regresiones = cycle.regresiones_control(
        baseline,
        verification,
        "P1-BOLA",
    )

    assert len(regresiones) == 1
    assert regresiones[0]["antes"]["cuenta"] == "carlos"
    assert regresiones[0]["despues"]["estado"] == "HALLAZGO"
