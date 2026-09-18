# TRAMITIA — Auditor Correctivo de Seguridad de Dos Pilares

Auditor determinista para **diagnosticar, corregir, verificar y conservar evidencia** sobre una copia local autorizada de Tramitia.

El proyecto evoluciona el auditor genérico de BOLA original y mantiene su principio central: **la configuración declara qué se espera y el motor observa qué ocurre realmente**. La versión 2 amplía el alcance a los dos primeros pilares del protocolo académico:

1. **Identidad y Control de Acceso**.
2. **Arquitectura y Configuración**.

La integridad de la evidencia —hashes, respaldos, diff y resultados antes/después— es un mecanismo transversal del auditor y **no se presenta como un tercer pilar**.

> Uso académico y local. No dirija el auditor contra sistemas para los que no tenga autorización. Las correcciones automáticas solo escriben dentro de una copia local indicada explícitamente con `--target-root`.

## Mejoras de esta versión

- Conserva la detección genérica de BOLA.
- La GUI ejecuta también el control de **alcance del agente**, igual que la CLI.
- Añade controles RBAC del Pilar 1.
- Incorpora un motor declarativo para el Pilar 2.
- Implementa **respaldo → cambio → verificación → rollback**.
- Conserva evidencia por ejecución y hashes SHA-256.
- Corrige las referencias históricas a YAML: el proyecto usa **JSON**.
- Mantiene compatibilidad con los sistemas simulados Blog y Tickets.

## Controles de Tramitia 2.4.0-rc2

### Pilar 1 — Identidad y Control de Acceso

| ID | Control |
|---|---|
| `P1-BOLA-001` | Un analista no puede leer solicitudes ajenas |
| `P1-BOLA-002` | Un analista no puede modificar solicitudes ajenas |
| `P1-SCOPE-003` | El asistente conserva el alcance del solicitante |
| `P1-RBAC-004` | La auditoría administrativa está restringida por rol |
| `P1-RBAC-005` | Un analista no puede usar la priorización reservada |

### Pilar 2 — Arquitectura y Configuración

| ID | Control |
|---|---|
| `P2-CORS-001` | CORS no refleja orígenes arbitrarios con credenciales |
| `P2-SECRET-002` | Producción no depende del secreto de desarrollo por defecto |
| `P2-LIMIT-003` | La vía urgente no permite saltarse límites sin autorización |
| `P2-DOCKER-004` | El contenedor ejecuta con usuario no privilegiado |

## Estados

Durante el diagnóstico:

- `HALLAZGO`
- `SIN_HALLAZGO`
- `ERROR`

Después de un ciclo correctivo:

- `CORREGIDO`
- `NO_CORREGIDO`
- `SIN_HALLAZGO`
- `ERROR`

El éxito **no** se declara porque el parche pudo escribirse: la prueba original debe dejar de detectar el hallazgo.

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

## Diagnóstico

Levante Tramitia **2.4.0-rc2** únicamente en `127.0.0.1:5050`.

```bash
python -m auditor_bola.cli diagnose \
  --config config/tramitia.json \
  --target-root /ruta/a/tramitia-app \
  --out evidencias/diagnostico.json
```

En PowerShell:

```powershell
python -m auditor_bola.cli diagnose `
  --config config/tramitia.json `
  --target-root C:\ruta\tramitia-app `
  --out evidencias\diagnostico.json
```

`--target-root` permite inspeccionar también controles estáticos del Pilar 2.

## Ciclo correctivo

Ejemplo BOLA:

```bash
python -m auditor_bola.cli correct \
  --config config/tramitia.json \
  --control P1-BOLA-001 \
  --target-root /ruta/a/tramitia-app
```

Para que el auditor inicie/reinicie la copia local:

```bash
python -m auditor_bola.cli correct \
  --config config/tramitia.json \
  --control P1-BOLA-001 \
  --target-root /ruta/a/tramitia-app \
  --manage-target
```

Ciclo:

```text
Diagnosticar
   ↓
Confirmar hallazgo
   ↓
Guardar línea base
   ↓
Respaldar archivo
   ↓
Aplicar corrección
   ↓
Reiniciar
   ↓
Repetir pruebas
   ↓
¿corregido?
   ├─ sí → conservar evidencia
   └─ no → rollback → verificar restauración
```

## Correcciones automáticas disponibles

- `P1-BOLA-001` / `P1-BOLA-002` → `tramitia/api.py`
- `P1-SCOPE-003` → `tramitia/asistente/api.py`
- `P1-RBAC-004` → `tramitia/admin.py`
- `P2-CORS-001` → `tramitia/__init__.py`
- `P2-SECRET-002` → `tramitia/__init__.py`
- `P2-LIMIT-003` → `tramitia/asistente/api.py`

`P2-DOCKER-004` es un control de regresión: el Dockerfile de la versión estudiada ya declara un usuario no privilegiado.

Las correcciones usan reemplazos exactos. Si el archivo ya no coincide con la versión prevista, el auditor se detiene **sin modificarlo**.

## Evidencia

Cada ciclo crea:

```text
evidencias/
└── 20260917T235500Z/
    ├── manifest.json
    ├── baseline/
    │   └── resultados.json
    ├── cambios/
    │   ├── correccion.json
    │   ├── P1-BOLA-001.diff
    │   └── backup/
    └── verification/
        ├── resultados.json
        └── rollback.json
```

La evidencia incluye hashes SHA-256 antes/después, diff y respaldo.

## Interfaz gráfica

```bash
python -m auditor_bola.gui
```

Flujo:

1. Seleccione `config/tramitia.json`.
2. Seleccione la carpeta local de `tramitia-app`.
3. Opcionalmente pulse **Iniciar Tramitia local**.
4. Pulse **Diagnosticar**.
5. Revise P1 y P2 en una sola tabla.
6. Seleccione un hallazgo y pulse **Corregir seleccionado** cuando exista corrección automática.
7. El auditor repite la prueba y conserva evidencia.

## Arquitectura

```text
auditor_bola/
  config.py            configuración JSON de P1/P2
  engine.py            Pilar 1: BOLA + RBAC + alcance del agente
  agent_scope.py       consistencia API directa / agente
  pilar2.py            Arquitectura y Configuración
  runner.py            orquestador común CLI/GUI
  evidence.py          evidencia y hashes
  corrective.py        parches controlados + rollback
  cycle.py             ciclo correctivo
  process_manager.py   proceso local opcional de Tramitia
  cli.py
  gui.py
config/
  blog.json
  tickets.json
  tramitia.json
tests/
```

## Pruebas

```bash
pytest -v
```

La suite conserva el control positivo y negativo BOLA y añade pruebas para configuración de dos pilares y seguridad del corrector.
