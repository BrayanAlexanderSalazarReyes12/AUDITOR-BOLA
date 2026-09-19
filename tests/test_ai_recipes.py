import json

import auditor_bola.ai_recipes as ai
from auditor_bola.config import ConfigObjetivo, Correccion


def _cfg():
    return ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        correcciones=[
            Correccion(
                control_id="P1-X",
                archivo="src/App.java",
                operaciones=[],
            )
        ],
    )


def _payload_propuestas():
    enfoques = [
        ("IA-1", "MINIMA"),
        ("IA-2", "ESTRUCTURAL"),
        ("IA-3", "ALTERNATIVA"),
    ]
    return {
        "propuestas": [
            {
                "id": ident,
                "titulo": f"Propuesta {ident}",
                "enfoque": enfoque,
                "explicacion": "Corrige autorización.",
                "riesgo": "BAJO",
                "estrategia": "replace_exact",
                "buscar": "return true;",
                "reemplazar": "return autorizado;",
                "requiere_reinicio": True,
                "consideraciones": "Compilar y verificar.",
            }
            for ident, enfoque in enfoques
        ]
    }


def test_redacta_secretos_sin_destruir_codigo():
    source = (
        'String password = "super-secreto";\n'
        'String token = "abc123";\n'
        'return usuario != null;\n'
    )
    limpio = ai.redactar_secretos(source)
    assert "super-secreto" not in limpio
    assert "abc123" not in limpio
    assert "<REDACTED>" in limpio
    assert "return usuario != null;" in limpio


def test_genera_exactamente_tres_recetas_estructuradas(monkeypatch):
    response_data = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(_payload_propuestas()),
                    }
                ],
            }
        ]
    }

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return response_data

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(ai.requests, "post", fake_post)

    proposals, context = ai.generar_tres_recetas(
        _cfg(),
        control_id="P1-X",
        descripcion="Validar rol",
        detalle="esperado=false real=true",
        source_relative="src/App.java",
        source_text='String api_key = "secret";\nreturn true;\n',
        api_key="test-key",
        model="modelo-prueba",
    )

    assert len(proposals) == 3
    assert {p.enfoque for p in proposals} == {
        "MINIMA",
        "ESTRUCTURAL",
        "ALTERNATIVA",
    }
    assert "secret" not in context["codigo_relevante_redactado"]
    assert captured["url"].endswith("/responses")
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["type"] == "json_schema"


def test_propuesta_se_convierte_a_receta_del_motor():
    p = ai.AIRecipeProposal(
        id="IA-1",
        titulo="mínima",
        enfoque="MINIMA",
        explicacion="x",
        riesgo="BAJO",
        estrategia="replace_exact",
        buscar="a",
        reemplazar="b",
        requiere_reinicio=True,
        consideraciones="c",
    )

    recipe = ai.propuesta_a_correccion(
        p,
        control_id="P1-X",
        source_relative="src/App.java",
    )

    assert recipe.control_id == "P1-X"
    assert recipe.archivo == "src/App.java"
    assert recipe.requiere_reinicio is True
    assert recipe.operaciones[0]["estrategia"] == "replace_exact"


def test_infiere_archivo_desde_receta_existente():
    assert ai.inferir_archivo_control(_cfg(), "P1-X") == "src/App.java"
