# Requisitos de uso — Aegis Auditor

## Alcance

Aegis Auditor es un auditor correctivo multitecnología basado exclusivamente en dos pilares de seguridad:

- Pilar 1 — Identidad y Control de Acceso: BOLA, RBAC, alcance por identidad y controles equivalentes.
- Pilar 2 — Arquitectura y Configuración: CORS, políticas HTTP, patrones inseguros/seguros, contenedores y controles reutilizables de configuración.

Multitecnología no significa cobertura universal de todas las vulnerabilidades. Una tecnología nueva se integra mediante perfil, runtime o adaptador reutilizable; una clase de control nueva debe pertenecer al Pilar 1 o al Pilar 2.

## Plataforma

- Windows 10/11
- Linux
- macOS

## Requisitos del Auditor

- Python 3.11 o 3.12
- pip
- Tkinter
- acceso de lectura al proyecto
- acceso de escritura cuando se apliquen correcciones
- conectividad HTTP hacia el objetivo para pruebas dinámicas

Instalación:

    python -m venv .venv
    python -m pip install -r requirements.txt

Windows:

    .\.venv\Scripts\Activate.ps1
    python -m auditor_bola.gui

Linux/macOS:

    source .venv/bin/activate
    python -m auditor_bola.gui

En Linux puede ser necesario instalar Tkinter con el gestor del sistema, por ejemplo python3-tk.

## IA

Para generación y adaptación de recetas con Gemma se requiere la configuración local de OpenCode en ~/.config/opencode/opencode.json. Aegis no debe copiar secretos del proveedor en perfiles ni evidencias.

## Proyecto objetivo

Según el control, se necesita:

- copia local autorizada del código
- URL base
- cuentas de prueba
- roles y roles privilegiados
- objetos de prueba y propietario esperado para BOLA
- expectativas de acceso para RBAC
- runtime del proyecto si Aegis administrará el proceso

El asistente puede inferir stack, runtime y rutas candidatas, pero no inventa propiedad de objetos ni políticas de autorización.

## Runtimes

Aegis puede orquestar o convivir con Node, Java, Python, PHP, .NET, Go, Ruby, Rust, Docker y otros runtimes mediante configuración. Si el objetivo ya está desplegado se utiliza runtime.modo = external.

## Reproducibilidad

Para cada experimento conservar: commit/versión, perfil JSON, baseline, diff, verificación, manifest de sesión, medicina aprendida, sistema operativo y runtime.

## Seguridad

Utilizar únicamente sobre aplicaciones, entornos y repositorios con autorización explícita de evaluación y modificación.
