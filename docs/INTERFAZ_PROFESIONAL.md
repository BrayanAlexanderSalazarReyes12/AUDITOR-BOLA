# Interfaz profesional — Aegis Auditor

Aegis Auditor usa **PySide6 / Qt 6** como interfaz de escritorio principal.

La decisión de migrar a Qt separa el motor de auditoría de la presentación y permite una experiencia de producto más cercana a una herramienta empresarial: mejor composición, escalado HiDPI, tablas, layouts responsivos, ventanas, diálogos y empaquetado nativo.

## Interfaz predeterminada

    python -m auditor_bola

o:

    python -m auditor_bola.gui

abren la interfaz Qt.

Para pruebas o compatibilidad todavía existen dos fallbacks:

    AEGIS_UI=ctk

abre la interfaz CustomTkinter anterior.

    AEGIS_LEGACY_UI=1

abre la interfaz Tkinter histórica.

Los ejecutables distribuidos abren Qt por defecto.

## Composición visual

La pantalla Inicio adopta la jerarquía del diseño de referencia:

- sidebar de producto con branding Aegis;
- cabecera de bienvenida;
- stepper horizontal del ciclo completo;
- panel principal de ejecución y diagnóstico;
- consola en tiempo real;
- rail derecho con información del proyecto;
- tarea actual y progreso;
- vista previa del perfil JSON;
- métricas compactas;
- footer de estado.

## Centro de Carga

El botón **Cargar / Importar** abre un diálogo único y profesional para nueva aplicación, perfil JSON, código fuente, auditor-package.json, cuentas y roles, evidencias, recetas/medicinas y proveedor IA.

## Auto-configuración

El wizard Qt analiza la carpeta seleccionada y detecta lenguaje, framework, manifiestos, runtime, URL sugerida, endpoints candidatos, roots de código y auditor-package.json. Después genera un perfil JSON reutilizable.

## Pilar 1 y Pilar 2

La página Auditoría mantiene separados visualmente **Pilar 1 — Identidad y Control de Acceso** y **Pilar 2 — Arquitectura y Configuración**. Los resultados se normalizan en una tabla común sin acoplar la GUI a una tecnología específica.

## Correcciones con IA

La página de IA permite seleccionar un hallazgo y archivo fuente, cargar OpenCode/Gemma, recuperar medicina reutilizable, generar tres propuestas, revisar y aplicar una opción, ejecutar backup + corrección + reinicio + verificación, revertir si falla y guardar medicina semántica cuando queda verificada.

## Evidencias y artículo

La página Evidencias muestra sesiones persistentes y permite exportar una copia redactada para documentación o artículo sin backups de código ni campos sensibles.

## Responsive / HiDPI

Qt 6 gestiona escalado HiDPI de forma nativa. Aegis añade dos composiciones: escritorio con sidebar completa y rail derecho; compacto con sidebar de iconos y rail derecho reubicado bajo el contenido. Cada página usa scroll cuando hace falta.

## Arquitectura

    auditor_bola/
    ├── runner.py
    ├── cycle.py
    ├── process_manager.py
    ├── profile_builder.py
    ├── ai_recipes.py
    ├── remediation_knowledge.py
    └── qt_ui/
        ├── app.py
        ├── controller.py
        ├── dialogs.py
        ├── pages.py
        ├── theme.py
        └── widgets.py

La carpeta qt_ui no contiene reglas de seguridad específicas de una aplicación. El comportamiento de auditoría sigue viviendo en el motor común.

## Distribución

PyInstaller empaqueta la interfaz Qt y el branding para Windows x64, macOS Intel, macOS Apple Silicon, Linux x64 y Linux ARM64. CustomTkinter permanece incluido temporalmente como fallback, pero no es la presentación predeterminada.
