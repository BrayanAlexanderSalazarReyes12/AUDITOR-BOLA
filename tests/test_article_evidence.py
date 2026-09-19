import json

from auditor_bola.article_evidence import export_article_package


def test_exporta_evidencia_redactada_y_excluye_backup(tmp_path):
    session = tmp_path / "evidencias" / "sesion-1"
    (session / "baseline").mkdir(parents=True)
    (session / "cambios" / "backup").mkdir(parents=True)
    (session / "verification").mkdir(parents=True)

    (session / "manifest.json").write_text(
        json.dumps({
            "control": "P1-BOLA-001",
            "token": "NO_PUBLICAR",
            "nested": {"password": "NO_PUBLICAR"},
        }),
        encoding="utf-8",
    )
    (session / "baseline" / "resultados.json").write_text(
        json.dumps({"estado": "HALLAZGO"}),
        encoding="utf-8",
    )
    (session / "verification" / "resultados.json").write_text(
        json.dumps({"estado": "SIN_HALLAZGO"}),
        encoding="utf-8",
    )
    (session / "cambios" / "P1.diff").write_text("diff demo", encoding="utf-8")
    (session / "cambios" / "backup" / "secret.py").write_text(
        "PASSWORD = \"secret\"", encoding="utf-8"
    )

    out = export_article_package(session, tmp_path / "articulo")

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["token"] == "[REDACTADO]"
    assert manifest["nested"]["password"] == "[REDACTADO]"
    assert (out / "baseline" / "resultados.json").exists()
    assert (out / "verification" / "resultados.json").exists()
    assert (out / "cambios" / "P1.diff").exists()
    assert not (out / "cambios" / "backup").exists()
    assert (out / "RESUMEN_ARTICULO.md").exists()
