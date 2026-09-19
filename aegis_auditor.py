"""Punto de entrada estable de Aegis Auditor."""

from __future__ import annotations

import os

from auditor_bola.app_paths import configure_packaged_environment


def main() -> None:
    configure_packaged_environment()

    ui = os.getenv("AEGIS_UI", "qt").strip().lower()

    if os.getenv("AEGIS_LEGACY_UI", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        ui = "legacy"

    if ui == "legacy":
        from auditor_bola.gui import AuditorGUI

        AuditorGUI().mainloop()
        return

    if ui in {"ctk", "customtkinter"}:
        from auditor_bola.ui.app import ModernAuditorGUI

        ModernAuditorGUI().mainloop()
        return

    from auditor_bola.qt_ui.app import run_qt_app

    raise SystemExit(run_qt_app())


if __name__ == "__main__":
    main()
