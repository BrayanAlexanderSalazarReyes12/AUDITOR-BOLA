# Requisitos de la aplicación — Aegis Auditor

## Opción recomendada: Windows con instalador

- Windows 10 u 11 de 64 bits.
- 4 GB de RAM mínimo; 8 GB o más recomendado.
- Aproximadamente 500 MB libres para aplicación, evidencias y sesiones.
- Resolución mínima recomendada: 1280×720.
- Conectividad hacia la aplicación que se auditará.
- Permiso de lectura del proyecto y escritura cuando se apliquen correcciones.

Para AegisAuditor-Setup.exe o AegisAuditor.exe no se requiere instalar Python.

## Ejecución desde código fuente

- Python 3.11 o 3.12.
- pip.
- Tkinter.
- Dependencias de requirements-runtime.txt.

Instalación:

    python -m venv .venv
    python -m pip install -r requirements-runtime.txt
    python -m auditor_bola

Para desarrollo y pruebas:

    python -m pip install -r requirements.txt
    pytest -v

Para construir el .exe:

    python -m pip install -r requirements-build.txt
    pyinstaller --clean --noconfirm AegisAuditor.spec

## Requisitos de IA

Las correcciones generadas o adaptadas con Gemma requieren una configuración OpenCode válida. Aegis puede seguir ejecutando controles deterministas y correcciones existentes sin ese proveedor.

## Requisitos del proyecto objetivo

Aegis está diseñado para proyectos de distintas tecnologías. El proyecto debe aportar lo necesario según su stack:

- código fuente local autorizado;
- URL base para pruebas dinámicas;
- cuentas y roles cuando el Pilar 1 los requiera;
- runtime instalado si Aegis administrará el proceso;
- dependencias y servicios externos necesarios para levantar la aplicación.

Ejemplos de runtimes que pueden ser necesarios: Node.js, Java, Maven, Gradle, Python, PHP, Composer, .NET SDK, Go, Ruby, Rust, Docker, Apache, Nginx, Tomcat o IIS.

Si el objetivo ya está ejecutándose en otro servidor puede configurarse runtime.modo = external.

## Alcance de seguridad

La compatibilidad tecnológica no cambia el modelo metodológico. Aegis trabaja sobre los dos pilares del proyecto:

Pilar 1 — Identidad y Control de Acceso
- BOLA/IDOR;
- RBAC;
- identidad, propiedad y alcance;
- controles equivalentes expresados por perfil.

Pilar 2 — Arquitectura y Configuración
- CORS;
- políticas HTTP;
- configuración insegura;
- patrones de fuente;
- contenedores y runtime;
- capacidades adicionales implementadas dentro de este pilar.

Aegis no debe presentarse como un escáner universal de cualquier CWE; una nueva tecnología se integra mediante adaptadores o perfiles y una nueva clase de control debe pertenecer al Pilar 1 o Pilar 2.
