import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from auditor_bola.qt_ui.app import Topbar
from auditor_bola.qt_ui.dialogs import AccountManagerDialog
from auditor_bola.qt_ui.theme import QSS


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    return app


def test_account_manager_can_add_manual_accounts():
    app = _app()
    dialog = AccountManagerDialog(
        [
            {
                "username": "admin",
                "password": "secret",
                "role": "ADMIN",
                "auth_type": "basic",
                "token": None,
                "headers": {},
            }
        ],
        ["ADMIN"],
    )
    dialog.show()
    app.processEvents()

    accounts, privileged = dialog.data()

    assert accounts[0]["username"] == "admin"
    assert accounts[0]["password"] == "secret"
    assert accounts[0]["role"] == "ADMIN"
    assert accounts[0]["auth_type"] == "basic"
    assert "ADMIN" in privileged

    dialog.close()


def test_fullscreen_topbar_has_explicit_exit_button():
    app = _app()
    called = []

    topbar = Topbar(
        lambda: None,
        lambda: None,
        lambda: called.append(True),
    )
    topbar.show()
    app.processEvents()

    assert topbar.exit_btn.text() == "✕ Salir"
    assert topbar.exit_btn.objectName() == "ExitButton"

    topbar.exit_btn.click()
    assert called == [True]

    topbar.close()


def test_editing_accounts_preserves_login_token_and_headers():
    _app()
    original = {"username": "user", "password": "pw", "role": "USER",
                "auth_type": "session", "login": {"ruta": "/api/login"},
                "token": "existing-token", "headers": {"X-Tenant": "tenant"}}
    dialog = AccountManagerDialog([original], [])
    accounts, _ = dialog.data()
    assert accounts == [original]
    dialog.close()
