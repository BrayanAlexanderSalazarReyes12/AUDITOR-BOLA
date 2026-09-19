# Ejecutable Windows — Aegis Auditor

Aegis Auditor se distribuye para Windows de dos formas:

1. AegisAuditor.exe — versión portable de un solo archivo.
2. AegisAuditor-Setup.exe — instalador recomendado.

## Descargar

Cada compilación de GitHub Actions publica el artefacto Aegis-Auditor-Windows.

Contenido esperado:

    AegisAuditor.exe
    AegisAuditor-Setup.exe
    AegisAuditor.exe.sha256
    AegisAuditor-Setup.exe.sha256

Ruta en GitHub:

    Actions → Build Windows EXE → ejecución más reciente → Artifacts

## ¿Necesito Python?

Para ejecutar AegisAuditor.exe no se necesita instalar Python. PyInstaller incluye el intérprete y las dependencias Python requeridas.

Los runtimes de las aplicaciones auditadas sí deben existir cuando Aegis deba administrarlas. Ejemplos: Node.js, Java, Maven, Docker, PHP, .NET, Go, etc.

## Datos persistentes

La versión instalada no escribe dentro de Program Files. Utiliza:

    %LOCALAPPDATA%\AegisAuditor\
      config\
      evidencias\
      recetas\
        conocimiento\
      articulo\

Puede cambiarse con la variable AEGIS_DATA_HOME.

## Construcción local

En Windows:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements-build.txt
    pyinstaller --clean --noconfirm AegisAuditor.spec

Resultado: dist\AegisAuditor.exe

Para construir el instalador se requiere Inno Setup 6:

    iscc installer\AegisAuditor.iss
