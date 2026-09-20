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


def test_carga_llmlab_desde_opencode(tmp_path, monkeypatch):
    cfg_path = tmp_path / "opencode.json"
    cfg_path.write_text(
        json.dumps(
            {
                "provider": {
                    "llmlab": {
                        "name": "Laboratorio UTB",
                        "options": {
                            "baseURL": "https://lab.example/llm/v1",
                            "apiKey": "{env:UTB_TEST_KEY}",
                        },
                        "models": {
                            "lab-coder": {
                                "name": "Gemma Lab"
                            }
                        },
                    }
                },
                "model": "llmlab/lab-coder",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENCODE_CONFIG", str(cfg_path))
    monkeypatch.setenv("UTB_TEST_KEY", "clave-local-de-prueba")

    provider = ai.cargar_configuracion_opencode()

    assert provider.provider_id == "llmlab"
    assert provider.provider_name == "Laboratorio UTB"
    assert provider.model_id == "lab-coder"
    assert provider.model_name == "Gemma Lab"
    assert provider.api_key == "clave-local-de-prueba"
    assert provider.base_url == "https://lab.example/llm/v1"
    assert "api_key" not in provider.public_dict()


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


def test_genera_tres_recetas_con_chat_completions(monkeypatch):
    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(_payload_propuestas()),
                }
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

    provider = ai.AIProviderConfig(
        provider_id="llmlab",
        provider_name="Laboratorio UTB",
        model_id="lab-coder",
        model_name="Gemma Lab",
        base_url="https://lab.example/llm/v1",
        api_key="clave-prueba",
        config_path="/tmp/opencode.json",
    )

    proposals, context, used = ai.generar_tres_recetas(
        _cfg(),
        control_id="P1-X",
        descripcion="Validar rol",
        detalle="esperado=false real=true",
        source_relative="src/App.java",
        source_text='String api_key = "secret";\nreturn true;\n',
        provider=provider,
    )

    assert len(proposals) == 3
    assert {p.enfoque for p in proposals} == {
        "MINIMA",
        "ESTRUCTURAL",
        "ALTERNATIVA",
    }
    assert "secret" not in context["codigo_relevante_redactado"]
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "lab-coder"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert used.provider_id == "llmlab"


def test_extrae_json_envuelto_en_markdown():
    raw = "```json\n" + json.dumps(_payload_propuestas()) + "\n```"
    data = ai._extraer_json(raw)
    assert len(data["propuestas"]) == 3


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



def test_contexto_ia_incluye_fila_objetivo_matriz_y_feedback_redactado(monkeypatch):
    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(_payload_propuestas()),
                }
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
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(ai.requests, "post", fake_post)

    provider = ai.AIProviderConfig(
        provider_id="llmlab",
        provider_name="Laboratorio UTB",
        model_id="lab-coder",
        model_name="Gemma Lab",
        base_url="https://lab.example/llm/v1",
        api_key="clave-prueba",
        config_path="/tmp/opencode.json",
    )

    _, context, _ = ai.generar_tres_recetas(
        _cfg(),
        control_id="P1-BOLA",
        descripcion="BOLA PATCH /reservas/{id}",
        detalle="HTTP 200 · esperado=False real=True",
        source_relative="src/App.java",
        source_text="return true;\n",
        provider=provider,
        metadata_hallazgo={
            "cuenta": "lucia",
            "metodo": "PATCH",
            "ruta": "/reservas/{id}",
            "estado": "HALLAZGO",
        },
        matriz_pruebas=[
            {
                "cuenta": "carlos",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "estado": "SIN_HALLAZGO",
            },
            {
                "cuenta": "lucia",
                "metodo": "PATCH",
                "ruta": "/reservas/{id}",
                "estado": "HALLAZGO",
            },
        ],
        intento_anterior={
            "resultado": {"estado_final": "NO_CORREGIDO"},
            "api_key": "NO-DEBE-SALIR",
            "correccion_aplicada": {
                "diff": 'String token = "secreto";'
            },
        },
    )

    assert context["hallazgo_objetivo"]["cuenta"] == "lucia"
    assert len(context["matriz_de_pruebas_del_mismo_control"]) == 2
    assert (
        context["intento_anterior_fallido"]["resultado"]["estado_final"]
        == "NO_CORREGIDO"
    )
    assert (
        context["intento_anterior_fallido"]["api_key"]
        == "<REDACTED>"
    )
    serialized = json.dumps(context, ensure_ascii=False)
    assert "NO-DEBE-SALIR" not in serialized
    assert "secreto" not in serialized

    system_prompt = captured["json"]["messages"][0]["content"]
    assert "NO repitas la misma solución" in system_prompt
    assert "SIN_HALLAZGO" in system_prompt



def test_generacion_puede_recibir_medicina_semantica(monkeypatch):
    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(_payload_propuestas()),
                }
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
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(ai.requests, "post", fake_post)

    provider = ai.AIProviderConfig(
        provider_id="llmlab",
        provider_name="Laboratorio UTB",
        model_id="lab-coder",
        model_name="Gemma Lab",
        base_url="https://lab.example/llm/v1",
        api_key="clave-prueba",
        config_path="/tmp/opencode.json",
    )

    medicina = {
        "control_id": "P1-BOLA",
        "titulo": "Autorización por recurso",
        "causa_raiz": "Falta autorización sobre el objeto concreto.",
        "invariante_seguridad": (
            "El sujeto debe estar autorizado para el recurso solicitado."
        ),
        "estrategia_general": [
            "cargar recurso",
            "evaluar política",
            "rechazar antes de operar",
        ],
        "contrato_verificacion": [
            "propietario permitido",
            "no propietario rechazado",
        ],
    }

    _, context, _ = ai.generar_tres_recetas(
        _cfg(),
        control_id="P1-BOLA",
        descripcion="BOLA PATCH /pedidos/{id}",
        detalle="esperado=False real=True",
        source_relative="src/PedidoController.java",
        source_text="return true;\n",
        provider=provider,
        conocimiento_reutilizable=medicina,
    )

    assert (
        context["conocimiento_correctivo_reutilizable"]["titulo"]
        == "Autorización por recurso"
    )
    system = captured["json"]["messages"][0]["content"]
    assert "medicina semántica previamente verificada" in system
    assert "ADÁPTALA al código actual" in system


def test_generaliza_correccion_exitosa_sin_guardar_parche_literal(monkeypatch):
    semantic = {
        "titulo": "Autorización a nivel de objeto",
        "causa_raiz": "Falta una decisión de autorización sobre el recurso.",
        "invariante_seguridad": (
            "Toda operación debe comprobar permiso sobre el recurso concreto."
        ),
        "estrategia_general": [
            "identificar sujeto",
            "cargar recurso",
            "evaluar autorización",
            "rechazar antes de operar",
        ],
        "señales_aplicabilidad": [
            "endpoint recibe id de recurso",
            "otro usuario accede al objeto",
        ],
        "requisitos_implementacion": [
            "validación en servidor",
        ],
        "anti_patrones": [
            "comprobar solo autenticación",
        ],
        "contrato_verificacion": [
            "propietario permitido",
            "otro usuario rechazado",
        ],
        "consideraciones": [
            "preservar respuestas seguras existentes",
        ],
        "lenguajes_observados": [".java"],
        "frameworks_observados": ["spring"],
    }

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(semantic),
                        }
                    }
                ]
            }

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(ai.requests, "post", fake_post)

    provider = ai.AIProviderConfig(
        provider_id="llmlab",
        provider_name="Laboratorio UTB",
        model_id="lab-coder",
        model_name="Gemma Lab",
        base_url="https://lab.example/llm/v1",
        api_key="clave-prueba",
        config_path="/tmp/opencode.json",
    )

    proposal = ai.AIRecipeProposal(
        id="IA-1",
        titulo="Validar propietario",
        enfoque="MINIMA",
        explicacion="Valida el dueño.",
        riesgo="BAJO",
        estrategia="replace_exact",
        buscar="return true;",
        reemplazar="return autorizado;",
        requiere_reinicio=True,
        consideraciones="Compilar.",
    )

    knowledge, context, _ = ai.generalizar_correccion_exitosa(
        _cfg(),
        control_id="P1-BOLA",
        descripcion="BOLA PATCH /pedidos/{id}",
        detalle="antes vulnerable",
        metadata_hallazgo={
            "cuenta": "lucia",
            "metodo": "PATCH",
            "ruta": "/pedidos/{id}",
        },
        matriz_pruebas=[],
        source_relative="src/PedidoController.java",
        codigo_antes='String token = "secreto";\nreturn true;\n',
        codigo_despues='String token = "secreto";\nreturn autorizado;\n',
        diff="- return true;\n+ return autorizado;\n",
        propuesta=proposal,
        provider=provider,
    )

    assert knowledge.control_id == "P1-BOLA"
    assert knowledge.invariante_seguridad
    assert knowledge.estrategia_general
    assert "return true;" not in knowledge.invariante_seguridad
    serialized = json.dumps(context, ensure_ascii=False)
    assert "secreto" not in serialized
    prompt = captured["json"]["messages"][0]["content"]
    assert "NO es guardar el parche literal" in prompt
    assert "independiente de nombres concretos" in prompt



def test_configuracion_ia_propia_de_aegis_no_depende_de_opencode(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )
    monkeypatch.delenv("AEGIS_AI_BASE_URL", raising=False)
    monkeypatch.delenv("AEGIS_AI_API_KEY", raising=False)
    monkeypatch.delenv("AEGIS_AI_MODEL", raising=False)
    monkeypatch.setenv(
        "OPENCODE_CONFIG",
        str(tmp_path / "opencode-inexistente.json"),
    )

    saved = ai.guardar_configuracion_aegis_ai(
        base_url="https://lab.example/llm/v1",
        model_id="lab-coder",
        api_key="clave-local",
    )
    provider = ai.cargar_configuracion_ia()

    assert saved.config_path == str(config_path.resolve())
    assert provider.base_url == "https://lab.example/llm/v1"
    assert provider.model_id == "lab-coder"
    assert provider.api_key == "clave-local"
    assert "api_key" not in provider.public_dict()


def test_guardar_ia_con_clave_vacia_conserva_clave_local(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )

    ai.guardar_configuracion_aegis_ai(
        base_url="https://lab.example/v1",
        model_id="lab-coder",
        api_key="secreto-existente",
    )
    ai.guardar_configuracion_aegis_ai(
        base_url="https://lab2.example/v1",
        model_id="modelo-nuevo",
        api_key=None,
    )

    provider = ai.cargar_configuracion_aegis_ai()
    assert provider.base_url == "https://lab2.example/v1"
    assert provider.model_id == "modelo-nuevo"
    assert provider.api_key == "secreto-existente"


def test_configuracion_ia_desde_variables_funciona_sin_archivo(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: tmp_path / "no-existe.json",
    )
    monkeypatch.setenv(
        "AEGIS_AI_BASE_URL",
        "https://env.example/v1",
    )
    monkeypatch.setenv("AEGIS_AI_MODEL", "coder-env")
    monkeypatch.setenv("AEGIS_AI_API_KEY", "key-env")

    provider = ai.cargar_configuracion_ia()

    assert provider.base_url == "https://env.example/v1"
    assert provider.model_id == "coder-env"
    assert provider.api_key == "key-env"



def test_varios_perfiles_ia_se_pueden_guardar_y_seleccionar(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )

    first = ai.guardar_perfil_ia(
        profile_name="UTB - Gemma",
        base_url="https://utb.example/v1",
        model_id="lab-coder",
        api_key="key-utb",
    )
    second = ai.guardar_perfil_ia(
        profile_name="Ollama local",
        base_url="http://127.0.0.1:11434/v1",
        model_id="qwen2.5-coder",
        api_key="",
    )

    profiles = ai.listar_perfiles_ia()
    assert len(profiles) == 2
    assert sum(bool(item["active"]) for item in profiles) == 1
    assert second.profile_id != first.profile_id
    assert ai.cargar_configuracion_aegis_ai().profile_id == second.profile_id

    selected = ai.seleccionar_perfil_ia(first.profile_id)
    assert selected.profile_name == "UTB - Gemma"
    assert selected.api_key == "key-utb"
    assert ai.cargar_configuracion_aegis_ai().profile_id == first.profile_id


def test_lista_perfiles_ia_no_expone_api_keys(tmp_path, monkeypatch):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )

    ai.guardar_perfil_ia(
        profile_name="Proveedor privado",
        base_url="https://private.example/v1",
        model_id="coder",
        api_key="NO-DEBE-SALIR",
    )

    profiles = ai.listar_perfiles_ia()
    serialized = json.dumps(profiles)
    assert "NO-DEBE-SALIR" not in serialized
    assert profiles[0]["has_api_key"] is True


def test_perfil_ia_se_puede_duplicar_y_eliminar(tmp_path, monkeypatch):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )

    original = ai.guardar_perfil_ia(
        profile_name="LM Studio",
        base_url="http://127.0.0.1:1234/v1",
        model_id="local-model",
        api_key="local-key",
    )
    duplicate = ai.duplicar_perfil_ia(original.profile_id)

    assert duplicate.profile_id != original.profile_id
    assert duplicate.profile_name == "LM Studio copia"
    assert duplicate.api_key == "local-key"
    assert len(ai.listar_perfiles_ia()) == 2

    active_after_delete = ai.eliminar_perfil_ia(duplicate.profile_id)
    assert active_after_delete == original.profile_id
    assert ai.cargar_configuracion_aegis_ai().profile_id == original.profile_id
    assert len(ai.listar_perfiles_ia()) == 1


def test_editar_perfil_ia_conserva_clave_si_campo_vacio(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )

    provider = ai.guardar_perfil_ia(
        profile_name="Proveedor editable",
        base_url="https://one.example/v1",
        model_id="modelo-1",
        api_key="clave-existente",
    )
    updated = ai.guardar_perfil_ia(
        profile_id=provider.profile_id,
        profile_name="Proveedor editado",
        base_url="https://two.example/v1",
        model_id="modelo-2",
        api_key=None,
    )

    assert updated.profile_id == provider.profile_id
    assert updated.profile_name == "Proveedor editado"
    assert updated.base_url == "https://two.example/v1"
    assert updated.model_id == "modelo-2"
    assert updated.api_key == "clave-existente"


def test_migra_configuracion_ia_antigua_a_perfiles(tmp_path, monkeypatch):
    config_path = tmp_path / "ai-provider.json"
    config_path.write_text(
        json.dumps(
            {
                "provider_id": "llmlab",
                "provider_name": "Laboratorio UTB",
                "model_id": "lab-coder",
                "model_name": "Gemma Lab",
                "base_url": "https://lab.example/v1",
                "api_key": "legacy-key",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )

    provider = ai.cargar_configuracion_aegis_ai()
    stored = json.loads(config_path.read_text(encoding="utf-8"))

    assert provider.base_url == "https://lab.example/v1"
    assert provider.api_key == "legacy-key"
    assert stored["schema_version"] == 2
    assert len(stored["profiles"]) == 1
    assert stored["active_profile_id"] == stored["profiles"][0]["id"]



def test_perfil_activo_de_aegis_tiene_prioridad_sobre_variables(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "ai-provider.json"
    monkeypatch.setattr(
        ai,
        "default_ai_config_path",
        lambda: config_path,
    )
    ai.guardar_perfil_ia(
        profile_name="Perfil seleccionado",
        base_url="https://profile.example/v1",
        model_id="profile-model",
        api_key="profile-key",
    )
    monkeypatch.setenv(
        "AEGIS_AI_BASE_URL",
        "https://env.example/v1",
    )
    monkeypatch.setenv("AEGIS_AI_MODEL", "env-model")

    provider = ai.cargar_configuracion_ia()

    assert provider.profile_name == "Perfil seleccionado"
    assert provider.base_url == "https://profile.example/v1"
    assert provider.model_id == "profile-model"
