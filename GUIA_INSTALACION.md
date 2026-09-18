# Guía de uso — Auditor Correctivo de Seguridad de Dos Pilares

## 1. Instalación

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

Compruebe:

```bash
pytest -v
```

## 2. Abrir la interfaz

```bash
python -m auditor_bola.gui
```

La GUI ya permite ejecutar el ciclo completo.

## 3. Preparar el objetivo

En la parte superior seleccione:

1. **Perfil de aplicación (.json)**.
2. **Carpeta de código local**.
3. **Carpeta de evidencias**.

Para una aplicación nueva use `config/plantilla.json`.

## 4. Administrar la aplicación

Si el perfil contiene `runtime.comando_inicio`, estarán disponibles:

- **Iniciar objetivo**
- **Detener**
- **Reiniciar**

La opción **Gestionar reinicio automáticamente al corregir** hace que el auditor inicie/reinicie el objetivo durante el ciclo correctivo. Si el sistema ya está levantado externamente y no desea que el auditor lo administre, desmarque esa casilla.

## 5. Diagnosticar

Pulse:

**Diagnosticar P1 + P2**

La tabla muestra:

- Pilar.
- ID del control.
- Descripción.
- Cuenta.
- Estado.
- Si existe corrección automática.
- Detalle observado.

Colores:

- rojo/rosado: `HALLAZGO`;
- verde: `SIN_HALLAZGO`;
- amarillo: `ERROR`.

## 6. Revisar una corrección

Seleccione una fila.

La pestaña **Detalle / Corrección** muestra:

- control;
- estado;
- detalle;
- receta declarada;
- archivo que será modificado;
- operaciones configuradas.

## 7. Corregir un hallazgo

Seleccione un hallazgo que tenga **Corrección = Sí** y pulse:

**Corregir seleccionado**

El auditor:

1. repite el diagnóstico;
2. confirma el hallazgo;
3. crea una sesión de evidencia;
4. guarda línea base;
5. hace backup del archivo;
6. registra SHA-256;
7. aplica la receta;
8. reinicia si corresponde;
9. repite la prueba;
10. marca `CORREGIDO` si pasa;
11. si falla, restaura el backup automáticamente.

## 8. Corregir todos

Pulse:

**Corregir todos los hallazgos corregibles**

El auditor obtiene los controles únicos en estado `HALLAZGO` que tengan receta y ejecuta los ciclos uno por uno.

Si una corrección falla, las siguientes continúan; el resultado final indica cada estado.

## 9. Verificar manualmente

Seleccione cualquier control y pulse:

**Verificar seleccionado**

Se repite el diagnóstico y se guarda una nueva evidencia de verificación sin modificar código.

## 10. Evidencias

Abra la pestaña **Evidencias**.

Allí puede:

- listar todas las sesiones;
- ver `manifest.json`;
- ver `correccion.json`;
- ver el diff;
- abrir la carpeta en el sistema operativo;
- comprobar rollbacks anteriores.

## 11. Revertir manualmente

Seleccione una sesión correctiva en **Evidencias** y pulse:

**Revertir esta corrección**

El auditor restaura el backup, reinicia opcionalmente y compara el SHA-256 restaurado contra el hash de la línea base.

El resultado queda en:

```text
verification/manual_rollback.json
```

## 12. Guardar reporte

Después de un diagnóstico pulse:

**Guardar reporte actual**

Esto exporta el resultado completo visible a JSON.

## 13. Sistemas nuevos

Para integrar otra aplicación no edite los motores Python.

Copie:

```text
config/plantilla.json
```

y configure:

- `base_url`;
- cuentas y autenticación;
- roles;
- endpoints;
- controles;
- runtime;
- recetas.

Consulte `docs/CREAR_PERFIL.md`.

## 14. Nota sobre correcciones

Una corrección automática existe únicamente cuando el perfil declara una receta. El auditor no inventa cambios sobre código desconocido.

Si un hallazgo aparece con **Corrección = No**, puede seguir diagnosticándose y verificándose, pero para corregirlo automáticamente debe agregarse una receta reutilizable/segura al perfil.

## 15. Tramitia

Para el caso de estudio seleccione:

```text
config/tramitia.json
```

y como carpeta de código la copia local de `tramitia-app` correspondiente a la versión prevista por el perfil.

Tramitia es solo un perfil de ejemplo; la GUI y el motor son genéricos.
