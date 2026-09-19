from auditor_bola.ai_preview import preview_recipe
from auditor_bola.config import Correccion


def test_preview_no_modifica_archivo(tmp_path):
    target = tmp_path / "target"
    source = target / "src" / "App.java"
    source.parent.mkdir(parents=True)
    source.write_text("return true;\n", encoding="utf-8")

    recipe = Correccion(
        control_id="P1-X",
        archivo="src/App.java",
        operaciones=[
            {
                "estrategia": "replace_exact",
                "buscar": "return true;",
                "reemplazar": "return autorizado;",
            }
        ],
    )

    result = preview_recipe(recipe, target)

    assert result["cambia_archivo"] is True
    assert "-return true;" in result["diff"]
    assert "+return autorizado;" in result["diff"]
    assert source.read_text(encoding="utf-8") == "return true;\n"


def test_preview_rechaza_receta_que_no_coincide(tmp_path):
    target = tmp_path / "target"
    source = target / "src" / "App.java"
    source.parent.mkdir(parents=True)
    source.write_text("return false;\n", encoding="utf-8")

    recipe = Correccion(
        control_id="P1-X",
        archivo="src/App.java",
        operaciones=[
            {
                "estrategia": "replace_exact",
                "buscar": "return true;",
                "reemplazar": "return autorizado;",
            }
        ],
    )

    try:
        preview_recipe(recipe, target)
    except RuntimeError as exc:
        assert "no coincide" in str(exc)
    else:
        raise AssertionError("La previsualización debía rechazar la receta")
