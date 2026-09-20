from auditor_bola.language_detection import (
    detect_language_context,
    detect_source_language,
    requires_service_restart,
)


def test_detecta_python_y_flask_por_archivo_y_codigo():
    result = detect_source_language(
        "app/routes.py",
        "from flask import Flask\n@app.get('/orders')\ndef orders():\n    pass\n",
    )

    assert result.language == "Python"
    assert result.confidence == "alta"
    assert "Flask" in result.frameworks


def test_detecta_java_spring_y_jsp_sin_mezclar_sintaxis():
    java = detect_source_language(
        "src/OrderController.java",
        "package demo;\n"
        "import org.springframework.web.bind.annotation.RestController;\n"
        "@RestController\npublic class OrderController {}\n",
    )
    jsp = detect_source_language(
        "web/order.jsp",
        "<%@ page language=\"java\" %>\n<html></html>\n",
    )

    assert java.language == "Java"
    assert "Spring" in java.frameworks
    assert jsp.language == "JSP/Java"


def test_contexto_incluye_lenguaje_principal_y_frameworks_relacionados():
    result = detect_language_context(
        "routes.py",
        "def route():\n    return service.load()\n",
        {
            "service.py": "from flask import abort\ndef load():\n    return 1\n",
            "static/app.js": "const x = 1;\n",
        },
    )

    assert result["principal"]["language"] == "Python"
    assert result["archivos_relacionados"]["static/app.js"]["language"] == "JavaScript"
    assert "Flask" in result["frameworks_contexto"]



def test_python_y_configuracion_ejecutable_requieren_reinicio():
    assert requires_service_restart(["tramitia/auth.py"]) is True
    assert requires_service_restart(["src/App.java"]) is True
    assert requires_service_restart(["config/application.properties"]) is True


def test_documentacion_estatica_no_fuerza_reinicio():
    assert requires_service_restart(["README.md"]) is False
