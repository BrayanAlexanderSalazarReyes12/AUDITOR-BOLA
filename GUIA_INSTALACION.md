# Guía completa — Auditor genérico de BOLA

Todo lo necesario para instalar, probar y ejecutar el auditor en una máquina
nueva, desde cero. Sin IA en ningún punto del motor: todo lo que decide si
algo es una falla o no es comparación de código HTTP contra lo que declaraste
en un archivo JSON.

## 0. Qué vas a instalar (una sola vez)

| Programa | Para qué | Dónde conseguirlo |
|---|---|---|
| Python 3.11 o superior | Correr todo el proyecto | https://www.python.org/downloads/ (marca "tcl/tk and IDLE" en el instalador, si no ya la GUI no abre) |
| Git (opcional) | Si van a versionarlo en GitHub | https://git-scm.com/downloads |

No se necesita ninguna base de datos, servidor externo, ni cuenta en la nube.
Todo corre en tu máquina.

## 1. Estructura del proyecto (lo que te entrego)

```
auditor-generico-bola/
├── auditor_bola/              <- el paquete (el "backend")
│   ├── __init__.py
│   ├── config.py              <- lee y valida el JSON del sistema a auditar
│   ├── engine.py               <- el motor: BOLA + alcance del agente
│   ├── agent_scope.py          <- lógica del chequeo de alcance del agente
│   ├── cli.py                  <- interfaz de línea de comandos
│   └── gui.py                  <- interfaz gráfica (Tkinter)
├── config/                     <- 3 sistemas de ejemplo, listos para usar
│   ├── blog.json                (con un bug BOLA a propósito)
│   ├── tickets.json              (sin bugs, control negativo)
│   └── tramitia.json             (el sistema real de la materia)
├── tests/
│   ├── sistema_falso_blog.py    <- mini API Flask con el bug
│   ├── sistema_falso_tickets.py <- mini API Flask sin bugs
│   └── test_engine.py           <- pruebas automatizadas (pytest)
├── requirements.txt
├── .gitignore
└── README.md
```

## 2. Instalación (una sola vez por máquina)

```bash
# 1. Ubícate en la carpeta del proyecto
cd auditor-generico-bola

# 2. Crea el entorno virtual
python -m venv .venv
# (en Windows con "python" bloqueado por el alias de la tienda, usa: py -3.12 -m venv .venv)

# 3. Actívalo
source .venv/Scripts/activate      # Git Bash en Windows
# .venv\Scripts\activate           # cmd o PowerShell
# source .venv/bin/activate        # Linux / Mac

# 4. Instala las dependencias
pip install -r requirements.txt
```

`requirements.txt` instala: `requests` (para las peticiones HTTP),
`flask` (solo para los sistemas de prueba falsos) y `pytest` (para las
pruebas). Tkinter **no** aparece ahí porque no se instala con pip: viene
incluido en el propio Python.

## 3. Verificar que todo quedó bien instalado

```bash
pytest -v
```

Debe mostrar `3 passed`. Si falla aquí, algo del paso 2 no quedó bien —
no sigas hasta que esto pase en verde.

## 4. Probarlo contra los sistemas de ejemplo (sin tocar Tramitia)

Necesitas **dos terminales**: una para el "sistema falso" y otra para el
auditor.

**Terminal A** (deja esto corriendo, no la cierres):
```bash
source .venv/Scripts/activate
python -c "from tests.sistema_falso_blog import crear_app_blog; crear_app_blog().run(port=5100)"
```

**Terminal B**:
```bash
source .venv/Scripts/activate
python -m auditor_bola.cli --config config/blog.json --out reportes/evidencia.json
```

Salida esperada: `BOLA confirmados: 2` (el bug de `maria` accediendo a los
posts de `juan`). Si ves eso, el motor funciona correctamente.

## 5. Auditar Tramitia de verdad

**Terminal A** (Tramitia, no el auditor):
```bash
cd tramitia-app
source .venv/Scripts/activate
python run.py
```

**Terminal B** (el auditor, en su propia carpeta):
```bash
cd auditor-generico-bola
source .venv/Scripts/activate
python -m auditor_bola.cli --config config/tramitia.json --out reportes/evidencia_tramitia.json
```

Salida esperada contra la versión sin parchar: `BOLA confirmados: 2` y
`[VULNERABLE] escalada via agente (H-04)`.

## 6. Usar la interfaz gráfica en vez de la terminal

Con el sistema objetivo corriendo (Tramitia o uno de los falsos, igual que
en los pasos 4 y 5):

```bash
python -m auditor_bola.gui
```

1. Botón **"Elegir configuración (.json)"** → elige el archivo de
   `config/` que corresponda al sistema que dejaste corriendo.
2. Botón **"Ejecutar auditoría"**.
3. La tabla se llena sola: filas rosadas = BOLA confirmado.
4. Botón **"Guardar evidencia (.json)"** para exportar el resultado.

## 7. Auditar un sistema nuevo que no sea ninguno de los tres

No se toca ningún archivo `.py`. Solo se escribe un JSON nuevo en `config/`:

```json
{
  "sistema": "nombre-libre",
  "base_url": "http://host:puerto",
  "cuentas": [
    {"username": "user_bajo", "password": "clave1", "role": "normal"},
    {"username": "user_alto", "password": "clave2", "role": "admin"}
  ],
  "roles_privilegiados": ["admin"],
  "endpoints": [
    {
      "metodo": "GET",
      "ruta": "/api/recurso/{id}",
      "id_prueba": "1",
      "propietario_esperado": "user_bajo"
    }
  ]
}
```

Guárdalo como `config/mi_sistema.json` y corre:
```bash
python -m auditor_bola.cli --config config/mi_sistema.json --out reportes/evidencia.json
```

Si el sistema también tiene un agente conversacional que pudiera exponer
más de lo debido, agrega además la sección `"chequeos_agente"` (ver
`config/tramitia.json` como ejemplo real ya funcional).

## 8. Errores comunes y qué hacer

| Error en pantalla | Causa | Solución |
|---|---|---|
| `ConnectionRefusedError` / `Max retries exceeded` | El sistema objetivo no está corriendo, o el puerto de `base_url` no coincide | Verifica que el Terminal A esté realmente arriba (`curl base_url/health` o similar) |
| `No module named _tkinter` | Python instalado sin soporte de Tk | Reinstala Python desde python.org marcando "tcl/tk and IDLE" |
| `No module named 'auditor_bola'` | No estás parado en la carpeta del proyecto, o el venv no está activado | `cd auditor-generico-bola` y vuelve a activar el entorno |
| `FileNotFoundError` al elegir el JSON | Ruta con espacios o caracteres raros | Usa rutas simples, sin tildes ni espacios, para la carpeta del proyecto |
| Todos los hallazgos salen `BOLA confirmado` incluso para el propietario legítimo | El `username` en `config/*.json` no coincide exactamente con `propietario_esperado` | Revisa mayúsculas/minúsculas y espacios en el JSON |
