"""Punto de entrada estable de Aegis Auditor."""

from __future__ import annotations

import os

from auditor_bola.app_paths import configure_packaged_environment


def main() -> None:
    configure_packaged_environment()

    if os.getenv("AEGIS_LEGACY_UI", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        from auditor_bola.gui import AuditorGUI

        app = AuditorGUI()
    else:
        from auditor_bola.ui.app import ModernAuditorGUI

        app = ModernAuditorGUI()

    app.mainloop()


if __name__ == "__main__":
    main()
