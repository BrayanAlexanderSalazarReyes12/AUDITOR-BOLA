import json

from auditor_bola.config import Correccion
from auditor_bola.recipe_library import (
    buscar_recetas_compatibles,
    guardar_receta_biblioteca,
    marcar_uso_receta,
)


def _recipe(archivo="src/App.java"):
    return Correccion(
        control_id="P1-BOLA",
        archivo=archivo,
        descripcion="Validar propiedad del recurso",
        requiere_reinicio=True,
        operaciones=[
            {
                "estrategia": "replace_exact",
                "buscar": "return true;",
                "reemplazar": "return usuarioEsPropietario;",
                "max_reemplazos": 1,
            }
        ],
    )


def test_guarda_receta_sin_fijar_ruta_para_reutilizacion(tmp_path):
    library = tmp_path / "recetas"

    path = guardar_receta_biblioteca(
        _recipe(),
        sistema="Sistema A",
        metodo="PATCH",
        ruta="/reservas/{id}",
        tipo_control="bola",
        titulo="Validación de propietario",
        fuente="gemma",
        proveedor="Laboratorio UTB",
        modelo="lab-coder",
        verificada=True,
        library_root=library,
    )

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["control_id"] == "P1-BOLA"
    assert data["verificada"] is True
    assert data["operaciones"][0]["buscar"] == "return true;"
    assert data["origenes"][0]["archivo_origen"] == "src/App.java"
    assert "api_key" not in json.dumps(data).lower()


def test_receta_se_adapta_a_otro_sistema_si_el_preview_coincide(tmp_path):
    library = tmp_path / "recetas"
    target = tmp_path / "otro_sistema"
    source = target / "src" / "ReservaController.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "class ReservaController {\n"
        "  boolean puedeAcceder() { return true; }\n"
        "}\n",
        encoding="utf-8",
    )

    guardar_receta_biblioteca(
        _recipe(),
        sistema="Sistema A",
        metodo="PATCH",
        ruta="/reservas/{id}",
        verificada=True,
        library_root=library,
    )

    candidates = buscar_recetas_compatibles(
        control_id="P1-BOLA",
        target_root=target,
        archivo="src/ReservaController.java",
        metodo="PATCH",
        ruta="/ordenes/{id}",
        library_root=library,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.correccion.archivo == "src/ReservaController.java"
    assert "usuarioEsPropietario" in candidate.preview["codigo_despues"]


def test_descarta_receta_si_no_aplica_al_codigo_actual(tmp_path):
    library = tmp_path / "recetas"
    target = tmp_path / "otro_sistema"
    source = target / "src" / "ReservaController.java"
    source.parent.mkdir(parents=True)
    source.write_text("return false;\n", encoding="utf-8")

    guardar_receta_biblioteca(
        _recipe(),
        sistema="Sistema A",
        verificada=True,
        library_root=library,
    )

    candidates = buscar_recetas_compatibles(
        control_id="P1-BOLA",
        target_root=target,
        archivo="src/ReservaController.java",
        library_root=library,
    )

    assert candidates == []


def test_registra_uso_exitoso_y_marca_verificada(tmp_path):
    library = tmp_path / "recetas"
    path = guardar_receta_biblioteca(
        _recipe(),
        sistema="Sistema A",
        verificada=False,
        library_root=library,
    )

    marcar_uso_receta(path, exitoso=True)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["verificada"] is True
    assert data["estadisticas"]["usos"] == 1
    assert data["estadisticas"]["usos_exitosos"] == 1
