# Auditor Correctivo de Seguridad — Dos Pilares

Motor determinista para **diagnosticar, corregir, verificar y conservar evidencia** sobre aplicaciones y repositorios de código autorizados.

El repositorio nació como `AUDITOR-BOLA`, pero la versión actual ya no está limitada a BOLA ni a Tramitia. El diseño separa:

- **motor genérico**: lógica reutilizable;
- **perfil JSON**: lo que cambia entre aplicaciones;
- **evidencia**: línea base, hashes, diff, verificación y rollback.

Los dos pilares cubiertos son:

1. **Identidad y Control de Acceso**.
2. **Arquitectura y Configuración**.

La integridad de la evidencia es transversal y no se presenta como un tercer pilar.

## Objetivo final

Para auditar otra aplicación **no se modifica el motor**. Se crea un perfil, por ejemplo:

```text
config/
  plantilla.json
  tramitia.json
  blog.json
  tickets.json
  mi-aplicacion.json
```

El perfil describe cuentas, roles, autenticación, endpoints, controles, arranque local y, opcionalmente, recetas correctivas.

Tramitia 2.4.0-rc2 es el caso de estudio principal, no una dependencia del auditor.

## Qué es genérico

- BOLA basado en propiedad de objetos.
- RBAC/ABAC basado en acceso esperado vs. acceso real.
- Comparación de alcance entre API directa y agente/asistente.
- CORS.
- Políticas de códigos HTTP.
- Inspección de patrones en código/configuración.
- Contenedores con usuario no root.
- Autenticación Basic, Bearer, headers personalizados o ninguna.
- Arranque/reinicio mediante comando configurable.
- Correcciones de texto `replace_exact` y `regex_replace`.
- Backup, SHA-256, diff, verificación y rollback.

Las inspecciones y correcciones de archivos son independientes del lenguaje: pueden trabajar sobre Java, JavaScript, PHP, C#, Go, Python, configuración, Dockerfiles, etc.

Para flujos especializados como SSO/MFA interactivo o protocolos no HTTP se añade un adaptador reusable; no se codifica una excepción para una aplicación concreta.

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

## Interfaz gráfica

```bash
python -m auditor_bola.gui
```

Flujo:

1. Seleccionar el perfil JSON de la aplicación.
2. Seleccionar la copia local del código cuando se usarán controles estáticos/correcciones.
3. Iniciar opcionalmente el objetivo con el comando declarado en el perfil.
4. Diagnosticar P1 y P2.
5. Seleccionar un hallazgo.
6. Aplicar una receta correctiva, si está declarada.
7. Verificar y conservar evidencia.

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

Si el perfil declara `runtime.comando_inicio`, el auditor puede administrar el proceso:

```bash
python -m auditor_bola.cli correct \
  --config config/mi-aplicacion.json \
  --control P1-BOLA-001 \
  --target-root /ruta/al/codigo \
  --manage-target
```

## Estados

Diagnóstico:

- `HALLAZGO`
- `SIN_HALLAZGO`
- `ERROR`

Ciclo correctivo:

- `CORREGIDO`
- `NO_CORREGIDO`
- `SIN_HALLAZGO`
- `ERROR`

Un parche escrito no equivale a una corrección: la prueba original debe pasar después del cambio.

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
  plantilla.json       base para cualquier aplicación
  tramitia.json        caso de estudio
  blog.json            sistema simulado
  tickets.json         sistema simulado

docs/
  CREAR_PERFIL.md
```

## Caso Tramitia

`config/tramitia.json` demuestra que los detalles de Tramitia viven en el perfil: rutas, cuentas, comandos y parches. Los motores no contienen rutas `tramitia/*.py` ni reglas específicas de ese sistema.

## Crear un perfil nuevo

Use:

```text
config/plantilla.json
docs/CREAR_PERFIL.md
```

La regla es: **una nueva aplicación se integra con configuración; una nueva capacidad universal se integra como extensión reusable.**

## Pruebas

```bash
pytest -v
```

La suite incluye sistemas simulados distintos, controles del Pilar 2, autenticación configurable y pruebas del corrector/rollback.
