# Interfaz profesional — Aegis Auditor

Aegis Auditor usa **CustomTkinter** como capa visual principal y conserva la interfaz Tkinter anterior únicamente como fallback mediante:

    AEGIS_LEGACY_UI=1

La interfaz moderna abre por defecto desde `python -m auditor_bola` y desde los ejecutables de Windows, macOS y Linux.

## Arquitectura visual

    auditor_bola/ui/
    ├── app.py
    ├── theme.py
    ├── router.py
    ├── adapters.py
    ├── project_wizard.py
    ├── components/
    │   ├── sidebar.py
    │   ├── topbar.py
    │   ├── load_center.py
    │   ├── cards.py
    │   ├── progress_steps.py
    │   ├── status_badge.py
    │   └── console.py
    └── pages/
        ├── home.py
        ├── project.py
        ├── audit.py
        ├── knowledge.py
        ├── reports.py
        └── settings.py

La capa visual reutiliza el motor de diagnóstico, corrección, rollback, evidencias y recetas existente; no contiene reglas específicas de una aplicación.

## Navegación

- Inicio
- Nuevo proyecto
- Cargar / Importar
- Auto-configuración
- Auditoría P1 + P2
- Correcciones con IA
- Recetas y conocimiento
- Evidencias
- Reportes
- Registro
- Configuración

## Centro de Carga

El botón **Cargar / Importar** abre un centro único para incorporar:

1. nueva aplicación;
2. perfil JSON;
3. código fuente;
4. `auditor-package.json`;
5. cuentas y roles;
6. evidencias;
7. recetas y medicinas;
8. proveedor IA.

El centro es scrollable y se adapta a pantallas pequeñas.

## Nuevo proyecto / Auto-configuración

El wizard moderno está dividido en Proyecto, Runtime, Pilar 1, Pilar 2 y Perfil JSON. Detecta lenguaje, framework, manifiestos, runtime y endpoints candidatos. Permite completar cuentas, roles privilegiados, pruebas BOLA/RBAC y controles de Pilar 2 antes de guardar el perfil.

## Auditoría

La vista distingue explícitamente **Pilar 1 — Identidad y Control de Acceso** y **Pilar 2 — Arquitectura y Configuración**, con métricas separadas y una tabla única de controles normalizados.

## Remediación IA

La página de Correcciones con IA conserva control seleccionado, archivo fuente, proveedor/modelo, medicinas compatibles, parches exactos, tres propuestas, vista previa del diff, aplicación y verificación.

## Responsive

La interfaz responde al redimensionamiento de la ventana: escritorio, portátil y modo ultra compacto. Está pensada para funcionar desde 1024×600 hasta 4K.

## Distribución

CustomTkinter y sus recursos se incluyen dentro de los paquetes PyInstaller. Los builds nativos siguen generándose para Windows, macOS Intel/ARM y Linux x64/ARM.
