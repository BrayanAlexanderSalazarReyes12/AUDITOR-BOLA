# Guía de instalación — Auditor Correctivo de Seguridad de Dos Pilares

Esta guía instala y ejecuta el auditor contra cualquier aplicación que tenga un perfil JSON compatible. Tramitia, Blog y Tickets son ejemplos; el motor no depende de ninguno.

## 1. Requisitos

| Programa | Uso |
|---|---|
| Python 3.11+ | Ejecutar el auditor |
| Git | Opcional, para clonar/versionar |
| Tk/Tcl | Interfaz gráfica; viene con la instalación oficial de Python |

## 2. Instalación

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 3. Verificación

```bash
pytest -v
```

También existe CI para Python 3.11 y 3.12.

## 4. Estructura

```text
auditor_bola/
  config.py
  transport.py
  engine.py
  agent_scope.py
  pilar2.py
  runner.py
  corrective.py
  evidence.py
  cycle.py
  process_manager.py
  cli.py
  gui.py

config/
  plantilla.json
  blog.json
  tickets.json
  tramitia.json

docs/
  CREAR_PERFIL.md
```

## 5. Diagnosticar una aplicación

Primero prepare un perfil. Para una aplicación nueva copie:

```text
config/plantilla.json
```

y complete sus cuentas, roles, rutas y controles.

Después:

```bash
python -m auditor_bola.cli diagnose \
  --config config/mi-aplicacion.json \
  --target-root /ruta/al/codigo \
  --out evidencias/diagnostico.json
```

`--target-root` es necesario para controles estáticos y correcciones. Si el perfil solo contiene controles HTTP, puede omitirse.

## 6. Corregir un hallazgo

Una corrección automática debe estar declarada en `correcciones` dentro del perfil.

```bash
python -m auditor_bola.cli correct \
  --config config/mi-aplicacion.json \
  --control P2-CONFIG-001 \
  --target-root /ruta/al/codigo
```

El auditor:

1. repite el hallazgo;
2. guarda línea base;
3. hace backup;
4. calcula hash;
5. aplica la receta;
6. repite las pruebas;
7. conserva evidencia;
8. revierte el cambio si la verificación falla.

## 7. Administrar el proceso objetivo

El perfil puede declarar:

```json
{
  "runtime": {
    "comando_inicio": ["npm", "start"],
    "directorio_trabajo": ".",
    "espera_inicio": 2,
    "variables": {}
  }
}
```

Entonces puede usar:

```bash
python -m auditor_bola.cli correct \
  --config config/mi-aplicacion.json \
  --control P1-BOLA-001 \
  --target-root /ruta/al/codigo \
  --manage-target
```

El comando puede ser Python, Java, Node, .NET u otro ejecutable disponible en la máquina.

## 8. Interfaz gráfica

```bash
python -m auditor_bola.gui
```

En la ventana:

1. **Perfil de aplicación (.json)**.
2. **Carpeta de código local**.
3. **Iniciar objetivo local**, si el perfil declara runtime.
4. **Diagnosticar**.
5. Seleccionar un control.
6. **Corregir seleccionado**, si existe receta.
7. Guardar evidencia.

## 9. Autenticación

El perfil soporta:

- `basic`
- `bearer`
- `header`
- `none`

Consulte `docs/CREAR_PERFIL.md` para ejemplos.

## 10. Probar con los sistemas simulados

Los mocks Blog y Tickets siguen siendo controles del propio auditor.

Ejecute:

```bash
pytest -v
```

Las pruebas levantan los sistemas simulados automáticamente.

## 11. Caso de estudio Tramitia

Para el laboratorio:

```bash
python -m auditor_bola.cli diagnose \
  --config config/tramitia.json \
  --target-root /ruta/a/tramitia-app
```

Tramitia es un **perfil de ejemplo**. Sus rutas, cuentas, runtime y correcciones viven en `config/tramitia.json`, no dentro del motor.

## 12. Integrar otra aplicación

No edite `engine.py`, `pilar2.py` o `corrective.py`.

Cree:

```text
config/mi-aplicacion.json
```

a partir de la plantilla.

Si aparece un tipo de autenticación, protocolo o control que todavía no existe, se implementa como capacidad reusable del auditor y luego puede utilizarse en cualquier perfil.

## Errores frecuentes

| Error | Acción |
|---|---|
| `ConnectionRefusedError` | Verifique `base_url` y que el objetivo esté arriba |
| `No module named _tkinter` | Instale Python oficial con Tcl/Tk |
| `No module named auditor_bola` | Ejecute desde la raíz del proyecto y active el venv |
| `ERROR` en un control estático | Compruebe `--target-root` y las rutas del perfil |
| Corrección no disponible | Declare una receta para el control en el perfil |
| Una receta no encuentra el texto | La versión del código no coincide con la receta; el auditor no modifica el archivo |
