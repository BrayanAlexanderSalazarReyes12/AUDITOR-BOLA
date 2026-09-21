from auditor_bola.project_validation import qa_failure_signature


def test_qa_failure_signature_is_stable_for_pytest():
    before = """
=========================== short test summary info ============================
FAILED tests/test_panel.py::AuditoriaTest::test_registra_la_creacion_de_solicitudes
1 failed, 12 passed
"""
    after = """
=========================== short test summary info ============================
FAILED tests/test_panel.py::AuditoriaTest::test_registra_la_creacion_de_solicitudes
1 failed, 12 passed
"""
    assert qa_failure_signature(before) == qa_failure_signature(after)


def test_qa_failure_signature_detects_new_test_failure():
    before = "FAILED tests/test_old.py::test_existing\n1 failed"
    after = (
        "FAILED tests/test_old.py::test_existing\n"
        "FAILED tests/test_panel.py::AuditoriaTest::test_new\n2 failed"
    )
    old = qa_failure_signature(before)
    new = qa_failure_signature(after)
    assert "tests/test_panel.py::AuditoriaTest::test_new" in [
        item for item in new if item not in old
    ]
