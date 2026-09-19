import json

from auditor_bola.remediation_knowledge import (
    RemediationKnowledge,
    buscar_conocimiento,
    crear_conocimiento_respaldo_verificado,
    guardar_conocimiento,
    registrar_uso_conocimiento,
)


def _knowledge():
    return RemediationKnowledge(
        control_id="P1-BOLA",
        titulo="Validar autorización a nivel de objeto",
        causa_raiz=(
            "El servidor confía en el identificador solicitado sin comprobar "
            "que el sujeto pueda operar sobre ese recurso."
        ),
        invariante_seguridad=(
            "Toda operación sobre un recurso debe autorizar al sujeto contra "
            "el recurso concreto antes de leerlo o modificarlo."
        ),
        estrategia_general=[
            "Resolver la identidad autenticada.",
            "Cargar el recurso solicitado.",
            "Evaluar propiedad, alcance o política de autorización.",
            "Rechazar antes de ejecutar la operación si no está autorizado.",
        ],
        señales_aplicabilidad=[
            "El endpoint recibe un identificador de recurso.",
            "Un usuario puede actuar sobre un recurso ajeno.",
        ],
        requisitos_implementacion=[
            "La autorización debe ejecutarse en servidor.",
            "El recurso evaluado debe ser el mismo que se opera.",
        ],
        anti_patrones=[
            "Confiar únicamente en que el usuario esté autenticado.",
            "Autorizar usando datos aportados por el cliente.",
        ],
        contrato_verificacion=[
            "El propietario conserva acceso.",
            "Otro usuario recibe denegación.",
            "No aparecen regresiones en casos previamente seguros.",
        ],
        lenguajes_observados=[".py"],
        tipo_control="bola",
        verificada=True,
        casos_exitosos=1,
    )


def test_guarda_medicina_semantica_separada_del_parche_literal(tmp_path):
    root = tmp_path / "conocimiento"
    path = guardar_conocimiento(
        _knowledge(),
        caso_exitoso={
            "sistema": "Sistema A",
            "extension": ".py",
            "metodo": "PATCH",
        },
        root=root,
    )

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["tipo"] == "conocimiento_correctivo_semantico"
    assert data["control_id"] == "P1-BOLA"
    assert data["verificada"] is True
    assert data["casos_exitosos"] >= 1
    assert "operaciones" not in data
    assert "buscar" not in json.dumps(data)
    assert "reemplazar" not in json.dumps(data)


def test_medicina_se_recupera_para_codigo_distinto(tmp_path):
    root = tmp_path / "conocimiento"
    guardar_conocimiento(_knowledge(), root=root)

    candidatos = buscar_conocimiento(
        control_id="P1-BOLA",
        descripcion="BOLA PATCH de pedidos",
        tipo_control="bola",
        source_text=(
            "@PatchMapping(\"/pedidos/{id}\")\n"
            "public Pedido actualizar(Long id) { ... }"
        ),
        extension=".java",
        root=root,
    )

    assert len(candidatos) == 1
    assert candidatos[0].knowledge.control_id == "P1-BOLA"
    assert candidatos[0].score >= 100
    assert (
        "autorizar"
        in candidatos[0].knowledge.invariante_seguridad.lower()
    )


def test_medicina_no_depende_del_mismo_lenguaje(tmp_path):
    root = tmp_path / "conocimiento"
    guardar_conocimiento(_knowledge(), root=root)

    java = buscar_conocimiento(
        control_id="P1-BOLA",
        descripcion="Acceso a recurso ajeno",
        tipo_control="bola",
        source_text="class Controller { Object get(Long id) {} }",
        extension=".java",
        root=root,
    )
    javascript = buscar_conocimiento(
        control_id="P1-BOLA",
        descripcion="Acceso a recurso ajeno",
        tipo_control="bola",
        source_text="router.get('/items/:id', handler)",
        extension=".js",
        root=root,
    )

    assert java
    assert javascript
    assert java[0].knowledge.knowledge_id == javascript[0].knowledge.knowledge_id


def test_registrar_uso_exitoso_acumula_evidencia(tmp_path):
    root = tmp_path / "conocimiento"
    path = guardar_conocimiento(_knowledge(), root=root)

    registrar_uso_conocimiento(
        path,
        exitoso=True,
        caso_exitoso={
            "sistema": "Sistema B",
            "extension": ".java",
        },
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["usos"] == 1
    assert data["usos_exitosos"] == 1
    assert data["verificada"] is True
    assert any(
        item.get("sistema") == "Sistema B"
        for item in data["ejemplos_verificados"]
    )


def test_otro_control_no_recibe_medicina_incorrecta(tmp_path):
    root = tmp_path / "conocimiento"
    guardar_conocimiento(_knowledge(), root=root)

    candidatos = buscar_conocimiento(
        control_id="P2-CORS-001",
        descripcion="CORS inseguro",
        tipo_control="cors",
        source_text="allow_origin = '*'",
        extension=".py",
        root=root,
    )

    assert candidatos == []



def test_medicina_se_recupera_por_familia_aunque_cambie_el_id(tmp_path):
    root = tmp_path / "conocimiento"
    base = _knowledge()
    base.control_id = "P1-BOLA-001"
    guardar_conocimiento(base, root=root)

    candidatos = buscar_conocimiento(
        control_id="P1-BOLA-017",
        descripcion="Acceso indebido a otro objeto",
        tipo_control="bola",
        source_text="Object getById(Long id) { ... }",
        extension=".java",
        root=root,
    )

    assert candidatos
    assert "familia" in " ".join(candidatos[0].razones).lower()


def test_medicina_se_recupera_por_tipo_si_el_perfil_usa_otro_id(tmp_path):
    root = tmp_path / "conocimiento"
    guardar_conocimiento(_knowledge(), root=root)

    candidatos = buscar_conocimiento(
        control_id="ACCESS-OBJECT-42",
        descripcion="Objeto ajeno accesible",
        tipo_control="bola",
        source_text="def update(resource_id): ...",
        extension=".py",
        root=root,
    )

    assert candidatos
    assert "tipo de control" in " ".join(
        candidatos[0].razones
    ).lower()


def test_fallback_verificado_siempre_puede_guardarse(tmp_path):
    root = tmp_path / "conocimiento"
    knowledge = crear_conocimiento_respaldo_verificado(
        control_id="P1-BOLA-NODE-001",
        descripcion="Un usuario no debe acceder a un recurso ajeno",
        tipo_control="bola",
        extension=".js",
    )

    path = guardar_conocimiento(
        knowledge,
        caso_exitoso={
            "sistema": "vulncommerce-node",
            "control_id": "P1-BOLA-NODE-001",
            "tipo_control": "bola",
            "extension": ".js",
        },
        root=root,
    )

    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["verificada"] is True
    assert data["casos_exitosos"] >= 1
    assert data["tipo"] == "conocimiento_correctivo_semantico"
    assert ".js" in data["lenguajes_observados"]
    assert data["estrategia_general"]
    assert data["contrato_verificacion"]
    serializado = json.dumps(data, ensure_ascii=False)
    assert '"buscar"' not in serializado
    assert '"reemplazar"' not in serializado
