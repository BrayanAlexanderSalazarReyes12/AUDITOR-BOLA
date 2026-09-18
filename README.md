# Auditor Correctivo de Seguridad — Dos Pilares

Motor determinista para **diagnosticar, corregir, verificar, revertir y conservar evidencia** sobre aplicaciones y repositorios de código autorizados.

El repositorio nació como `AUDITOR-BOLA`, pero la versión actual ya no está limitada a BOLA ni a Tramitia. El diseño separa:

- **motor genérico**: lógica reutilizable;
- **perfil JSON**: lo que cambia entre aplicaciones;
- **ciclo correctivo**: diagnóstico → backup → corrección → verificación → rollback;
- **evidencia**: línea base, hashes, diff, verificación y restauración.

Los dos pilares cubiertos son:

1. **Identidad y Control de Acceso**.
2. **Arquitectura y Configuración**.

La integridad de la evidencia es transversal y no se presenta como un tercer pilar.

## Guía paso a paso

Para utilizar la interfaz y aplicar correcciones, consulte:

```text
docs/GUIA_INTERFAZ_CORRECCIONES.md
```

La guía cubre carga del perfil, diagnóstico, corrección individual y múltiple, verificación, evidencias y rollback manual.

## Interfaz gráfica completa

Ejecute:

```bash
python -m auditor_bola.gui
```

La ventana permite realizar todo el ciclo sin usar la terminal:

1. **Perfil de aplicación (.json)**: carga la definición del sistema.
2. **Carpeta de código local**: selecciona la copia autorizada que puede inspeccionarse/corregirse.
3. **Carpeta de evidencias**: elige dónde guardar línea base, backups, diff y resultados.
4. **Iniciar objetivo**: inicia el sistema usando `runtime.comando_inicio` del perfil.
5. **Detener / Reiniciar**: administra el proceso local.
6. **Diagnosticar P1 + P2**: ejecuta todos los controles.
7. **Verificar seleccionado**: repite un control y guarda evidencia de verificación.
8. **Corregir seleccionado**: aplica la receta, reinicia opcionalmente, verifica y hace rollback automático si falla.
9. **Corregir todos los hallazgos corregibles**: procesa de forma secuencial todos los controles con receta.
10. **Evidencias**: muestra manifest, corrección, diff y rollback.
11. **Revertir esta corrección**: restaura manualmente el backup de una sesión y valida el SHA-256.
12. **Guardar reporte actual**: exporta el diagnóstico visible.
13. **Ver perfil JSON**: permite revisar desde la GUI la configuración usada.

La tabla indica explícitamente si cada hallazgo tiene **Corrección: Sí/No**.

## Ciclo correctivo

```text
DIAGNOSTICAR
    ↓
CONFIRMAR HALLAZGO
    ↓
GUARDAR LÍNEA BASE
    ↓
BACKUP + SHA-256
    ↓
APLICAR RECETA
    ↓
REINICIAR (opcional)
    ↓
VERIFICAR
    ↓
¿EL HALLAZGO DESAPARECIÓ?
   /                 \
 SÍ                   NO
 ↓                     ↓
CORREGIDO          ROLLBACK
                       ↓
                 VALIDAR HASH
```

Estados:

- `HALLAZGO`
- `SIN_HALLAZGO`
- `CORREGIDO`
- `NO_CORREGIDO`
- `ERROR`

Un parche escrito **no** equivale a una corrección: el control debe pasar después del cambio.

## Objetivo genérico

Para auditar otra aplicación **no se modifica el motor**. Se crea un perfil:

```text
config/
  plantilla.json
  tramitia.json
  blog.json
  tickets.json
  mi-aplicacion.json
```

El perfil describe:

- cuentas;
- roles;
- autenticación;
- endpoints;
- controles;
- archivos a inspeccionar;
- comando de arranque;
- recetas correctivas.

Tramitia 2.4.0-rc2 es un caso de estudio, no una dependencia del auditor.

## Capacidades reutilizables

- BOLA basado en propiedad de objetos.
- RBAC/ABAC basado en acceso esperado vs. real.
- Comparación de alcance API directa vs. agente/asistente.
- CORS.
- Políticas de códigos HTTP.
- Inspección de patrones en código/configuración.
- Contenedores con usuario no root.
- Autenticación Basic, Bearer, headers personalizados o ninguna.
- Runtime configurable para Python, Java, Node, .NET u otros.
- Correcciones de texto `replace_exact` y `regex_replace`.
- Backup, SHA-256, diff, verificación y rollback.
- Corrección múltiple desde GUI.
- Rollback manual desde evidencia.

Las inspecciones y correcciones de archivos son independientes del lenguaje: pueden trabajar con Java, JavaScript, PHP, C#, Go, Python, Dockerfiles y archivos de configuración.

## Instalación

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Después:

```bash
pytest -v
python -m auditor_bola.gui
```

## CLI

Diagnóstico:

```bash
python -m auditor_bola.cli diagnose \
  --config config/mi-aplicacion.json \
  --target-root /ruta/al/codigo \
  --out evidencias/diagnostico.json
```

Corrección:

```bash
python -m auditor_bola.cli correct \
  --config config/mi-aplicacion.json \
  --control P1-BOLA-001 \
  --target-root /ruta/al/codigo
```

Si el perfil declara `runtime.comando_inicio`:

```bash
python -m auditor_bola.cli correct \
  --config config/mi-aplicacion.json \
  --control P1-BOLA-001 \
  --target-root /ruta/al/codigo \
  --manage-target
```

## Evidencia generada

```text
evidencias/
└── <sesion>/
    ├── manifest.json
    ├── baseline/
    │   └── resultados.json
    ├── cambios/
    │   ├── correccion.json
    │   ├── <control>.diff
    │   └── backup/
    └── verification/
        ├── resultados.json
        ├── manual.json
        ├── rollback.json
        └── manual_rollback.json
```

Cada sesión usa un identificador temporal con microsegundos para evitar colisiones durante correcciones múltiples.

## Arquitectura

```text
auditor_bola/
  config.py            esquema del perfil
  transport.py         autenticación/transporte HTTP
  engine.py            Pilar 1
  agent_scope.py       API directa vs. agente
  pilar2.py            Pilar 2
  runner.py            orquestador común CLI/GUI
  corrective.py        recetas genéricas
  evidence.py          hashes y evidencia
  cycle.py             diagnóstico/corrección/verificación/rollback
  process_manager.py   proceso local configurable
  cli.py
  gui.py

config/
  plantilla.json
  tramitia.json
  blog.json
  tickets.json

docs/
  CREAR_PERFIL.md
```

## Crear un perfil nuevo

Use:

```text
config/plantilla.json
docs/CREAR_PERFIL.md
```

La regla es: **una nueva aplicación se integra con configuración; una nueva capacidad universal se integra como extensión reusable**.

## Pruebas y CI

```bash
pytest -v
```

La suite incluye:

- BOLA positivo y negativo;
- Pilar 2;
- configuración;
- autenticación configurable;
- corrector genérico;
- ciclo completo de corrección;
- verificación manual;
- rollback por evidencia;
- no colisión entre sesiones.

GitHub Actions ejecuta la suite en Python 3.11 y 3.12.
