"""Punto de entrada estable para desarrollo y ejecutable de Aegis Auditor."""

from auditor_bola.app_paths import configure_packaged_environment


def main() -> None:
    configure_packaged_environment()

    # Importar la GUI después de configurar rutas persistentes garantiza que
    # las bibliotecas de recetas/medicinas utilicen la carpeta del usuario en
    # la versión empaquetada.
    from auditor_bola.gui import AuditorGUI

    app = AuditorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
