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



def test_ciclo_marca_corregida_la_fila_objetivo_sin_exigir_limpiar_otro_hallazgo(
    tmp_path,
    monkeypatch,
):
    from auditor_bola.config import ConfigObjetivo, Correccion
    from auditor_bola.corrective import CorrectionResult

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
                "metodo": "GET",
                "ruta": "/reservas/{id}",
                "cuenta": "otra",
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
                "metodo": "GET",
                "ruta": "/reservas/{id}",
                "cuenta": "otra",
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

    resultados = iter([baseline, verification])
    monkeypatch.setattr(
        cycle,
        "diagnosticar",
        lambda cfg, target: next(resultados),
    )
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda resultado: resultado["filas"],
    )
    monkeypatch.setattr(cycle, "correction_available", lambda cfg, cid: True)
    monkeypatch.setattr(
        cycle,
        "apply_correction",
        lambda *args, **kwargs: CorrectionResult(
            control_id="P1-BOLA",
            archivo="app.py",
            applied=True,
            before_hash="a",
            after_hash="b",
            backup="backup",
            diff="- inseguro\n+ seguro\n",
            operaciones_aplicadas=1,
            mensaje="ok",
        ),
    )

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-BOLA",
                archivo="app.py",
                operaciones=[{"estrategia": "replace_exact"}],
            )
        ],
    )

    selector = {
        "tipo_control": "bola",
        "metodo": "PATCH",
        "ruta": "/reservas/{id}",
        "cuenta": "lucia",
    }

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-BOLA",
        tmp_path,
        evidence_base=tmp_path / "evidencias",
        selector=selector,
    )

    assert result["estado_final"] == "CORREGIDO"
    assert result["estado_despues"] == "SIN_HALLAZGO"
    assert result["estado_global_despues"] == "HALLAZGO"
    assert result["regresiones"] == []


def test_ciclo_rechaza_receta_si_rompe_una_fila_previamente_segura(
    tmp_path,
    monkeypatch,
):
    from auditor_bola.config import ConfigObjetivo, Correccion
    from auditor_bola.corrective import CorrectionResult

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

    resultados = iter([baseline, verification])
    monkeypatch.setattr(
        cycle,
        "diagnosticar",
        lambda cfg, target: next(resultados),
    )
    monkeypatch.setattr(
        cycle,
        "filas_gui",
        lambda resultado: resultado["filas"],
    )
    monkeypatch.setattr(cycle, "correction_available", lambda cfg, cid: True)
    monkeypatch.setattr(
        cycle,
        "apply_correction",
        lambda *args, **kwargs: CorrectionResult(
            control_id="P1-BOLA",
            archivo="app.py",
            applied=True,
            before_hash="a",
            after_hash="b",
            backup="backup",
            diff="- inseguro\n+ seguro\n",
            operaciones_aplicadas=1,
            mensaje="ok",
        ),
    )

    def fake_rollback(cfg, correction, target, evidence, restart, manifest):
        manifest["rollback"] = True

    monkeypatch.setattr(cycle, "_rollback_seguro", fake_rollback)

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-BOLA",
                archivo="app.py",
                operaciones=[{"estrategia": "replace_exact"}],
            )
        ],
    )

    selector = {
        "tipo_control": "bola",
        "metodo": "PATCH",
        "ruta": "/reservas/{id}",
        "cuenta": "lucia",
    }

    result = cycle.ciclo_correctivo(
        cfg,
        "P1-BOLA",
        tmp_path,
        evidence_base=tmp_path / "evidencias",
        selector=selector,
    )

    assert result["estado_final"] == "NO_CORREGIDO"
    assert result["rollback"] is True
    assert len(result["regresiones"]) == 1
    assert "regresiones" in result["motivo"]
