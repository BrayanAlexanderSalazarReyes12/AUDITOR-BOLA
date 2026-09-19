# Requisitos técnicos multiplataforma — Aegis Auditor

Este documento define los requisitos técnicos de las distribuciones de escritorio y del modo desarrollo.

## Windows

Distribuciones:
- AegisAuditor.exe — portable x64.
- AegisAuditor-Setup.exe — instalador x64.

Requisitos recomendados:
- Windows 10 22H2 o Windows 11 de 64 bits.
- CPU x64 de 2 núcleos o más.
- 4 GB RAM mínimo; 8 GB recomendado.
- 500 MB libres para la aplicación; espacio adicional según evidencias.
- Resolución mínima 1280×720; 1920×1080 recomendada.
- Acceso de red a la aplicación auditada.
- Permisos de lectura sobre el código y escritura cuando se apliquen correcciones.

El ejecutable incluye Python y las dependencias Python del Auditor. No requiere una instalación aparte de Python.

## macOS

Distribuciones:
- AegisAuditor-macOS-x64.dmg — equipos Intel.
- AegisAuditor-macOS-arm64.dmg — Apple Silicon M1/M2/M3/M4 y posteriores.

Requisitos recomendados:
- macOS 12 Monterey o posterior.
- 4 GB RAM mínimo; 8 GB recomendado.
- 500 MB libres más espacio para evidencias.
- Resolución mínima aproximada 1280×720.
- Acceso de lectura/escritura al proyecto según la operación.

Las compilaciones automáticas usan firma ad-hoc. Mientras el proyecto no tenga certificado Apple Developer y notarización, macOS puede pedir confirmación adicional al abrir una versión descargada.

## Linux

Distribuciones:
- AegisAuditor-Linux-x64.tar.gz.
- AegisAuditor-Linux-x64.deb.
- AegisAuditor-Linux-arm64.tar.gz.
- AegisAuditor-Linux-arm64.deb.

Base de compatibilidad x64:
- compilado sobre Ubuntu 22.04 para maximizar compatibilidad;
- glibc 2.35 o superior recomendado;
- entorno gráfico X11/XWayland con librerías Tk/X11 disponibles.

Dependencias del paquete DEB:
- libc6;
- libx11-6;
- libxext6;
- libxrender1;
- libxft2;
- libfontconfig1.

Distribuciones objetivo recomendadas:
- Ubuntu 22.04 / 24.04;
- Debian 12 o compatible;
- derivados con glibc igual o superior al entorno de compilación.

Para otras distribuciones puede ejecutarse desde código fuente si el binario no es compatible con su glibc.

## Arquitecturas generadas por CI

| Sistema | Arquitectura | Formato |
|---|---|---|
| Windows | x64 | .exe + Setup.exe |
| macOS | Intel x64 | .app + .dmg |
| macOS | Apple Silicon arm64 | .app + .dmg |
| Linux | x64 | binario + .tar.gz + .deb |
| Linux | arm64 | binario + .tar.gz + .deb |

## Requisitos de las aplicaciones auditadas

Aegis puede analizar proyectos de diferentes tecnologías, pero si debe iniciar o reiniciar el objetivo, el runtime correspondiente debe estar instalado en el sistema donde se ejecuta Aegis.

Ejemplos:
- Node.js / npm / yarn / pnpm;
- Java / Maven / Gradle;
- Python / pip;
- PHP / Composer;
- .NET SDK;
- Go;
- Ruby / Bundler;
- Rust / Cargo;
- Docker / Docker Compose;
- Apache, Nginx, Tomcat, IIS u otros servidores externos.

Si el sistema objetivo ya está levantado, use runtime.modo = external y Aegis no intentará administrar su proceso.

## IA

Gemma/OpenCode es opcional para el motor determinista. Se necesita cuando se desea generar o adaptar nuevas recetas con IA.

## Datos persistentes

Windows:
    %LOCALAPPDATA%\AegisAuditor\

macOS:
    ~/Library/Application Support/AegisAuditor/

Linux:
    $XDG_DATA_HOME/AegisAuditor/
o, si XDG_DATA_HOME no está definido:
    ~/.local/share/AegisAuditor/

Dentro se crean config, evidencias, recetas/conocimiento y articulo.

## Alcance metodológico

Independientemente del sistema operativo o tecnología, Aegis conserva exactamente los dos pilares del proyecto:

1. Pilar 1 — Identidad y Control de Acceso.
2. Pilar 2 — Arquitectura y Configuración.

La portabilidad del ejecutable no amplía artificialmente la cobertura de seguridad: los controles deben pertenecer a uno de estos pilares y estar implementados de forma reusable.
