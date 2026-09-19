# Aegis Auditor — Security Remediation Studio

Aegis Auditor es un estudio de remediación de seguridad para **incorporar, diagnosticar, corregir, verificar, revertir y aprender** sobre aplicaciones y repositorios de código autorizados.

El repositorio nació como `AUDITOR-BOLA`, pero la versión actual ya no está limitada a BOLA ni a Tramitia. El diseño separa:

- **motor genérico**: lógica reutilizable;
- **perfil JSON**: lo que cambia entre aplicaciones;
- **ciclo correctivo**: diagnóstico → backup → corrección → verificación → rollback;
- **evidencia**: línea base, hashes, diff, verificación y restauración.

Los dos pilares cubiertos son:

1. **Identidad y Control de Acceso**.
2. **Arquitectura y Configuración**.

La integridad de la evidencia es transversal y no se presenta como un tercer pilar.


## Nuevo flujo profesional de incorporación

La interfaz principal ya no obliga a preparar manualmente un perfil antes de comenzar. Use **Archivo → Nuevo proyecto / Auto-configurar** o el botón **＋ Nuevo proyecto**.

Aegis analiza la carpeta seleccionada y construye un borrador compatible con `config/*.json` detectando, cuando es posible:

- lenguaje y framework;
- manifiestos y raíces de código;
- `auditor-package.json`;
- comandos de preparación y arranque;
- estrategia `process`, `service` o `external`;
- endpoints candidatos en Flask, Express, Servlet/Spring y Django;
- configuración base multiplataforma.

El asistente permite además registrar cuentas, roles privilegiados y convertir endpoints detectados en controles **BOLA** o **RBAC** antes de guardar el perfil. Las decisiones que no pueden inferirse con seguridad —por ejemplo, propietario real de un objeto o acceso esperado de un rol— requieren confirmación humana.

La navegación de la aplicación se organiza en:

```text
Inicio
Hallazgos
Detalle / Corrección
IA / Medicinas
Evidencias
Registro
```

El menú superior separa **Archivo**, **Proyecto**, **Auditoría**, **Conocimiento** y **Ayuda**. Una barra de progreso indica las operaciones en curso y el dashboard muestra proyecto, perfil, proceso y número de hallazgos.

## Interfaz moderna

Aegis Auditor abre por defecto su interfaz profesional **PySide6 / Qt 6**, con dashboard, sidebar, Centro de Carga, auto-configuración, Auditoría P1/P2, remediación IA, conocimiento, evidencias y reportes. `AEGIS_UI=ctk` conserva la interfaz CustomTkinter como fallback y `AEGIS_LEGACY_UI=1` abre la interfaz histórica.

## Aplicaciones de escritorio

Aegis Auditor se compila de forma nativa para los principales sistemas operativos:

| Sistema | Distribución |
|---|---|
| Windows x64 | `AegisAuditor.exe` y `AegisAuditor-Setup.exe` |
| macOS Intel | `AegisAuditor.app` y `AegisAuditor-macOS-x64.dmg` |
| macOS Apple Silicon | `AegisAuditor.app` y `AegisAuditor-macOS-arm64.dmg` |
| Linux x64 | binario, `.tar.gz` y `.deb` |
| Linux arm64 | binario, `.tar.gz` y `.deb` |

El workflow `Build desktop executables` genera los artefactos mediante GitHub Actions. Consulte `docs/DISTRIBUCIONES_ESCRITORIO.md` y `docs/REQUISITOS_TECNICOS_MULTIPLATAFORMA.md`.

La aplicación empaquetada guarda perfiles, evidencias, recetas y material del artículo en la carpeta de datos del usuario, no dentro de la instalación.

## Documentación clave

- Requisitos de uso: `docs/REQUISITOS_USO.md`
- Requisitos técnicos multiplataforma: `docs/REQUISITOS_TECNICOS_MULTIPLATAFORMA.md`
- Distribuciones de escritorio: `docs/DISTRIBUCIONES_ESCRITORIO.md`
- Ejecutable Windows: `docs/EJECUTABLE_WINDOWS.md`
- Arquitectura de los dos pilares: `docs/ARQUITECTURA_DOS_PILARES.md`
- Creación manual de perfiles: `docs/CREAR_PERFIL.md`
- Evidencias y figuras para artículo: `docs/articulo/README.md`
- Registro de implementación: `docs/articulo/REGISTRO_IMPLEMENTACION.md`

## Guía paso a paso

Para utilizar la interfaz y aplicar correcciones, consulte:

```text
docs/GUIA_INTERFAZ_CORRECCIONES.md
```

La guía cubre carga del perfil, diagnóstico, corrección individual y múltiple, verificación, evidencias y rollback manual.

## Asistente IA de recetas

La versión actual usa **Gemma `lab-coder` del Laboratorio UTB** reutilizando
la configuración local de OpenCode. El auditor busca automáticamente:

```text
~/.config/opencode/opencode.json
```

y toma del proveedor `llmlab` la `baseURL`, el modelo `lab-coder` y la
referencia local de la API key. No es necesario copiar credenciales al perfil
del auditor.

Para un hallazgo seleccionado, la GUI solicita tres alternativas
—**MINIMA, ESTRUCTURAL y ALTERNATIVA**— mediante el endpoint compatible:

```text
<baseURL>/chat/completions
```

Luego abre automáticamente una **ventana independiente y redimensionable**
con una pestaña para cada alternativa. En ella se puede revisar el **código
resultante completo** y el diff antes de escribir, seleccionar la receta,
aplicarla o guardarla en el perfil. La ventana principal conserva el botón
**Ver propuestas en ventana** para volver a abrirla.

Después, la receta seleccionada se somete al ciclo determinista de backup,
aplicación, reinicio, verificación y rollback.

**Gemma propone; el usuario decide; el auditor verifica.**

Ejecute normalmente:

```powershell
python -m auditor_bola.gui
```

La pestaña **Asistente IA** mostrará el proveedor, modelo y ruta de OpenCode
detectados. La API key nunca se guarda en las evidencias del auditor.

Consulte:

```text
docs/ASISTENTE_IA.md
```

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

## Verificación granular y reformulación de recetas IA

Los controles pueden compartir el mismo `control_id` y aun así representar
pruebas distintas. Por ejemplo:

```text
P1-BOLA | GET   /reservas/{id} | carlos
P1-BOLA | PATCH /reservas/{id} | lucia
P1-BOLA | PATCH /reservas/{id} | recepcion
```

Cuando se corrige una fila seleccionada, el auditor conserva su cuenta,
método, ruta y tipo de control y verifica **esa fila exacta**. Al mismo tiempo
compara las demás filas del mismo control para detectar regresiones.

Una receta solo queda en `CORREGIDO` cuando:

1. la fila objetivo pasa a `SIN_HALLAZGO`; y
2. ninguna fila que antes estaba en `SIN_HALLAZGO` pasa a
   `HALLAZGO` o `ERROR`.

Si una receta no soluciona la fila objetivo o introduce una regresión, se hace
rollback y se marca `NO_CORREGIDO`.

Para mejorar una receta fallida, Gemma recibe en la siguiente ronda:

- la fila objetivo exacta;
- la matriz de pruebas del mismo control;
- el resultado esperado y observado;
- la receta anterior;
- el diff que se intentó aplicar;
- el resultado de verificación y las regresiones detectadas.

La GUI pregunta si se desean generar **3 nuevas recetas reformuladas** usando
esa retroalimentación, evitando repetir la misma solución fallida.

## Conocimiento correctivo reutilizable

El auditor distingue entre **medicina semántica** y **parche concreto**.

El parche concreto es la implementación que funcionó en una aplicación
determinada. Puede contener nombres, estructuras y fragmentos propios de ese
proyecto, por lo que no se considera universal.

La medicina semántica describe:

- causa raíz;
- invariante de seguridad que debe restaurarse;
- estrategia general;
- señales de aplicabilidad;
- requisitos de implementación;
- anti-patrones;
- contrato de verificación.

Solo se aprende una medicina cuando una implementación termina en
`CORREGIDO`.

```text
hallazgo nuevo
    ↓
buscar medicina por familia/tipo
    ↓
¿hay conocimiento verificado?
    ├── sí → Gemma adapta la medicina al código actual
    │          ↓
    │       3 implementaciones concretas
    │          ↓
    │       preview + selección humana
    │          ↓
    │       aplicar + verificar + rollback
    │
    └── no → Gemma genera 3 propuestas desde cero
               ↓
            si una funciona
               ↓
        extraer medicina semántica
               ↓
        recetas/conocimiento/
```

La biblioteca queda separada:

```text
recetas/
├── conocimiento/
│   └── <familia_control>/
│       └── <knowledge_id>.json
│
└── <control_id>/
    └── <recipe_id>.json
```

Los archivos bajo `recetas/<control_id>/` son instancias concretas
verificadas y sirven como evidencia o atajo cuando el código coincide. El
conocimiento bajo `recetas/conocimiento/` es el componente diseñado para
reutilizar la solución en otros aplicativos.

La búsqueda semántica no depende únicamente del ID literal. Agrupa variantes
como `P1-BOLA-001`, `P1-BOLA-017` y `P1-BOLA` dentro de la misma familia,
y también puede utilizar `tipo_control` cuando otro perfil emplea una
nomenclatura diferente.

No existe un parche textual que pueda garantizarse para cualquier código. Lo
reutilizable es la **estrategia de remediación verificada**, que debe
instanciarse para el código actual y volver a superar las pruebas.

## Resolución automática del archivo fuente

Al seleccionar una fila del diagnóstico, el auditor intenta cargar
automáticamente el archivo relacionado con el hallazgo en la pestaña
**Asistente IA**.

La resolución funciona en este orden:

```text
receta existente
    ↓
archivos_fuente del perfil
    ↓
archivo estático del control
    ↓
búsqueda por método + ruta + pistas + contenido
```

La búsqueda no depende de un framework concreto y contempla archivos Java,
Kotlin, Python, JavaScript/TypeScript, PHP, C#, Go, Ruby, JSP, XML, YAML,
properties y otros archivos de texto usados por aplicaciones web.

Si el auditor no puede resolverlo con suficiente información, mantiene
**Elegir archivo** como alternativa manual.

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
  recipe_library.py     instancias concretas verificadas
  remediation_knowledge.py conocimiento correctivo semántico
  cli.py
  gui.py

config/
  plantilla.json
  tramitia.json
  blog.json
  tickets.json

recetas/
  README.md
  conocimiento/
    <familia_control>/
      <knowledge_id>.json
  <control_id>/
    <recipe_id>.json

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


## Licencia

Aegis Auditor se distribuye bajo la **Apache License 2.0**.

Esto permite usar, estudiar, modificar y redistribuir el software, incluyendo
uso comercial, siempre que se conserven la licencia y los avisos aplicables.

Consulte:

- `LICENSE`: texto completo de Apache License 2.0.
- `NOTICE`: atribución y avisos del proyecto.

Las dependencias de terceros conservan sus propias licencias. La licencia del
código no concede por sí sola derechos adicionales sobre marcas, nombres o
identidad visual del proyecto.
