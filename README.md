# Auditor genérico de BOLA (Broken Object Level Authorization)

Motor determinista (sin IA) que prueba si un sistema HTTP con autenticación
Basic respeta la propiedad de sus recursos: si el usuario A puede leer o
editar un recurso que le pertenece a B, sin tener un rol privilegiado que
lo autorice, queda marcado como BOLA confirmado.

**No está atado a ningún sistema.** Todo lo que cambia entre auditar un
blog, un sistema de tickets, o Tramitia, vive en un archivo **JSON** — el
código de `auditor_bola/` es idéntico para los tres (ver `config/*.json`
para los tres ejemplos ya probados). Se eligió JSON en vez de YAML a
propósito: es de la librería estándar de Python (`json`), no depende de
instalar nada extra, y es el formato que más sistemas ya hablan de forma
nativa (casi cualquier API expone o consume JSON).

## Ver la interfaz gráfica en tu PC (Windows)

No hace falta instalar nada nuevo para la ventana en sí — **Tkinter viene
incluido con Python** en la instalación oficial de python.org (no en la
del Microsoft Store, que a veces lo omite). Pasos:

```bash
cd auditor-generico-bola
python -m venv .venv
.venv\Scripts\activate          # PowerShell / cmd
# o: source .venv/Scripts/activate   # Git Bash
pip install -r requirements.txt
python -m auditor_bola.gui
```

Si al ejecutar `python -m auditor_bola.gui` te sale `No module named
_tkinter`, significa que tu Python se instaló sin Tk (pasa con algunas
instalaciones mínimas o del Microsoft Store). Solución: instala Python
desde https://www.python.org/downloads/ marcando la opción "tcl/tk and
IDLE" durante la instalación (viene marcada por defecto en el instalador
oficial), o reinstala con `py -3.12` si ya tienes el instalador completo.

Primer uso, paso a paso una vez abierta la ventana:
1. Clic en **"Elegir configuración (.json)"** → selecciona `config/blog.json`.
2. Clic en **"Ejecutar auditoría"**.
3. Deberías ver la tabla con 2 filas en rosado (el BOLA de `maria`) — pero
   para eso el sistema falso tiene que estar corriendo (ver abajo).

## Uso por línea de comandos

```bash
python -m auditor_bola.cli --config config/tramitia.json --out reportes/evidencia.json
```

## Escribir un config nuevo para OTRO sistema

```json
{
  "sistema": "nombre-libre",
  "base_url": "http://host:puerto",
  "cuentas": [
    {"username": "user1", "password": "pass1", "role": "rol_bajo"},
    {"username": "user2", "password": "pass2", "role": "rol_alto"}
  ],
  "roles_privilegiados": ["rol_alto"],
  "endpoints": [
    {
      "metodo": "GET",
      "ruta": "/cualquier/ruta/{id}",
      "id_prueba": "1",
      "propietario_esperado": "user1"
    }
  ]
}
```

El motor prueba automáticamente TODAS las cuentas contra TODOS los
endpoints, cruzando quién debería tener acceso (según el YAML) contra
quién de verdad lo tiene (según la respuesta HTTP real).

## Interfaz gráfica

```bash
python -m auditor_bola.gui
```

Se abre una ventana de escritorio (Tkinter, ya incluido con Python — sin
dependencias nuevas):

1. **"Elegir configuración (.json)"** — abre cualquiera de los JSON de
   `config/` (o uno que armes tú para otro sistema).
2. **"Ejecutar auditoría"** — corre el mismo motor de `engine.py` contra
   la `base_url` del YAML y llena la tabla en vivo.
3. Cada fila con **fondo rosado** y `SÍ — BOLA` es un hallazgo confirmado;
   verde es una prueba que pasó bien.
4. **"Guardar evidencia (.json)"** — exporta exactamente lo mismo que
   produce la CLI, para meterlo al informe o al Threat Dragon.

No hace falta escribir ni una línea de código para auditar un sistema
nuevo: solo un YAML y un clic.

## Pruebas

```bash
pytest -v
```

Corre el motor contra dos sistemas simulados (`tests/sistema_falso_*.py`)
con Flask: uno con un BOLA real a propósito (para confirmar que lo
detecta) y otro sin bug (para confirmar que no da falsos positivos).

## Estructura

```
auditor_bola/
  config.py   -> carga y valida el YAML del objetivo
  engine.py   -> el motor genérico (no conoce ningún sistema)
  cli.py      -> interfaz de línea de comandos
  gui.py      -> interfaz gráfica de escritorio (Tkinter)
config/
  blog.json, tickets.json, tramitia.json  -> 3 sistemas de ejemplo
tests/
  sistema_falso_blog.py, sistema_falso_tickets.py -> mocks para pytest
  test_engine.py -> pruebas automatizadas
```
