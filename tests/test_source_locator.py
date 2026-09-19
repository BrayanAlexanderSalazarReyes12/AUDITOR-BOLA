from auditor_bola.config import (
    ChequeoPilar2,
    ConfigObjetivo,
    Endpoint,
)
from auditor_bola.source_locator import resolver_archivo_fuente


def _cfg(endpoint: Endpoint) -> ConfigObjetivo:
    return ConfigObjetivo(
        sistema="demo",
        base_url="http://127.0.0.1:9999",
        cuentas=[],
        endpoints=[endpoint],
    )


def test_resuelve_controlador_java_por_ruta_y_metodo(tmp_path):
    root = tmp_path / "app"
    target = root / "src/main/java/com/demo/ReservaController.java"
    target.parent.mkdir(parents=True)
    target.write_text(
        '''
@RestController
class ReservaController {
    @PatchMapping("/reservas/{id}")
    public Reserva actualizar(@PathVariable Long id) {
        return servicio.actualizar(id);
    }
}
''',
        encoding="utf-8",
    )
    (root / "README.md").write_text("reservas PATCH", encoding="utf-8")

    cfg = _cfg(
        Endpoint(
            id_control="P1-BOLA",
            descripcion="BOLA PATCH /reservas/{id}",
            metodo="PATCH",
            ruta="/reservas/{id}",
            id_prueba="10",
            propietario_esperado="ana",
        )
    )

    result = resolver_archivo_fuente(
        cfg,
        root,
        control_id="P1-BOLA",
        metodo="PATCH",
        ruta="/reservas/{id}",
        descripcion="BOLA PATCH /reservas/{id}",
    )

    assert result.archivo == "src/main/java/com/demo/ReservaController.java"
    assert result.confianza in {"alta", "media"}
    assert result.origen == "búsqueda automática"


def test_resuelve_ruta_python_sin_depender_del_framework(tmp_path):
    root = tmp_path / "app"
    target = root / "app/reservas.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        '''
@bp.get("/reservas/<int:id>")
def obtener_reserva(id):
    return buscar_reserva(id)
''',
        encoding="utf-8",
    )

    cfg = _cfg(
        Endpoint(
            id_control="P1-BOLA",
            metodo="GET",
            ruta="/reservas/{id}",
            id_prueba="10",
            propietario_esperado="ana",
        )
    )

    result = resolver_archivo_fuente(
        cfg,
        root,
        control_id="P1-BOLA",
        metodo="GET",
        ruta="/reservas/{id}",
        descripcion="BOLA GET /reservas/{id}",
    )

    assert result.archivo == "app/reservas.py"


def test_resuelve_endpoint_javascript_express(tmp_path):
    root = tmp_path / "app"
    target = root / "src/routes/reservas.js"
    target.parent.mkdir(parents=True)
    target.write_text(
        '''
router.patch("/reservas/:id", autenticar, async (req, res) => {
  const reserva = await Reserva.findById(req.params.id);
  res.json(reserva);
});
''',
        encoding="utf-8",
    )

    cfg = _cfg(
        Endpoint(
            id_control="P1-BOLA",
            metodo="PATCH",
            ruta="/reservas/{id}",
            id_prueba="10",
            propietario_esperado="ana",
        )
    )

    result = resolver_archivo_fuente(
        cfg,
        root,
        control_id="P1-BOLA",
        metodo="PATCH",
        ruta="/reservas/{id}",
        descripcion="BOLA PATCH /reservas/{id}",
    )

    assert result.archivo == "src/routes/reservas.js"


def test_archivo_declarado_tiene_prioridad_y_distingue_metodo(tmp_path):
    root = tmp_path / "app"
    read_file = root / "src/ReadReserva.java"
    write_file = root / "src/WriteReserva.java"
    read_file.parent.mkdir(parents=True)
    read_file.write_text("class ReadReserva {}", encoding="utf-8")
    write_file.write_text("class WriteReserva {}", encoding="utf-8")

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[
            Endpoint(
                id_control="P1-BOLA",
                metodo="GET",
                ruta="/reservas/{id}",
                id_prueba="1",
                propietario_esperado="ana",
                archivos_fuente=["src/ReadReserva.java"],
            ),
            Endpoint(
                id_control="P1-BOLA",
                metodo="PATCH",
                ruta="/reservas/{id}",
                id_prueba="1",
                propietario_esperado="ana",
                archivos_fuente=["src/WriteReserva.java"],
            ),
        ],
    )

    result = resolver_archivo_fuente(
        cfg,
        root,
        control_id="P1-BOLA",
        metodo="PATCH",
        ruta="/reservas/{id}",
    )

    assert result.archivo == "src/WriteReserva.java"
    assert result.confianza == "alta"
    assert result.origen == "perfil/receta"


def test_pilar2_utiliza_archivo_estatico_declarado(tmp_path):
    root = tmp_path / "app"
    target = root / "config/app.properties"
    target.parent.mkdir(parents=True)
    target.write_text("debug=true\n", encoding="utf-8")

    cfg = ConfigObjetivo(
        sistema="demo",
        base_url="",
        cuentas=[],
        endpoints=[],
        chequeos_pilar2=[
            ChequeoPilar2(
                id_control="P2-CONFIG",
                nombre="Debug deshabilitado",
                tipo="source_contains",
                archivo="config/app.properties",
                patron_inseguro="debug=true",
            )
        ],
    )

    result = resolver_archivo_fuente(
        cfg,
        root,
        control_id="P2-CONFIG",
    )

    assert result.archivo == "config/app.properties"
    assert result.origen == "perfil/receta"
