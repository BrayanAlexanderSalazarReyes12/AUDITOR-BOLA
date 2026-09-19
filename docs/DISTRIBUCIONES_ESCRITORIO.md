# Distribuciones de escritorio — Aegis Auditor

GitHub Actions construye Aegis de manera nativa en cada sistema operativo. PyInstaller no realiza compilación cruzada, por lo que cada artefacto se genera en el runner correspondiente.

## Artefactos

### Windows x64
- AegisAuditor.exe
- AegisAuditor-Setup.exe
- archivos SHA-256

### macOS Intel
- AegisAuditor.app
- AegisAuditor-macOS-x64.dmg
- SHA-256

### macOS Apple Silicon
- AegisAuditor.app
- AegisAuditor-macOS-arm64.dmg
- SHA-256

### Linux x64
- AegisAuditor
- AegisAuditor-Linux-x64.tar.gz
- AegisAuditor-Linux-x64.deb
- SHA-256

### Linux arm64
- AegisAuditor
- AegisAuditor-Linux-arm64.tar.gz
- AegisAuditor-Linux-arm64.deb
- SHA-256

## Dónde se descargan

En GitHub:
    Actions → Build desktop executables → ejecución → Artifacts

Los nombres de artefactos son:
- Aegis-Auditor-Windows-x64
- Aegis-Auditor-macOS-x64
- Aegis-Auditor-macOS-arm64
- Aegis-Auditor-Linux-x64
- Aegis-Auditor-Linux-arm64

## Construcción manual

Instale las dependencias de build:
    python -m pip install -r requirements-build.txt
    python scripts/generate_app_icons.py
    pyinstaller --clean --noconfirm AegisAuditor.spec

El binario generado es específico del sistema operativo y arquitectura donde se ejecutó PyInstaller.

## Seguridad de distribución

Cada artefacto incluye SHA-256. Para distribución pública estable conviene añadir en una fase posterior:
- firma Authenticode para Windows;
- certificado Developer ID + notarización para macOS;
- firma de paquetes/repository metadata para Linux;
- releases versionadas y SBOM.
