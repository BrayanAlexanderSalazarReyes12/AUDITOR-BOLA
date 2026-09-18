# Guía de uso de la interfaz y aplicación de correcciones

Esta guía explica cómo utilizar la interfaz gráfica del **Auditor Correctivo de Seguridad — Dos Pilares** para diagnosticar, corregir, verificar y revertir hallazgos sobre una copia local autorizada de una aplicación.

> El auditor trabaja sobre una copia local del código. Antes de corregir, siempre crea evidencia y respaldo. Si una corrección no elimina el hallazgo, ejecuta rollback automático.

---

## 1. Requisitos previos

Desde la raíz del proyecto:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Actualice la copia local del auditor:

```powershell
git checkout main
git pull origin main
```

Compruebe las pruebas:

```powershell
pytest -v
```

Abra la interfaz:

```powershell
python -m auditor_bola.gui
```

---

## 2. Qué debe tener preparado

Necesita tres elementos:

1. **Perfil JSON de la aplicación**.
2. **Carpeta local del código de la aplicación**.
3. **Carpeta donde guardar las evidencias**.

Para Tramitia use:

```text
config/tramitia.json
```

Para otra aplicación puede partir de:

```text
config/plantilla.json
```

El perfil define cuentas, roles, endpoints, controles, forma de inicio y recetas de corrección.

---

## 3. Cargar el objetivo en la interfaz

En la sección **Objetivo**:

### 3.1 Perfil de aplicación (.json)

Pulse:

```text
Perfil de aplicación (.json)
```

Seleccione el JSON correspondiente.

Ejemplo:

```text
config/tramitia.json
```

Si el archivo es válido, la interfaz mostrará el nombre y versión del sistema.

### 3.2 Carpeta de código local

Pulse:

```text
Carpeta de código local
```

Seleccione la raíz del proyecto que será auditado.

Ejemplo para Tramitia:

```text
C:\Users\Brayan Salazar\Downloads\tramitia-app
```

La ruta debe corresponder a la versión prevista por el perfil.

### 3.3 Carpeta de evidencias

Pulse:

```text
Carpeta de evidencias
```

Seleccione dónde quiere guardar resultados, respaldos, diffs y verificaciones.

Si no cambia esta carpeta, el auditor usa:

```text
<carpeta-del-auditor>\evidencias
```

---

## 4. Iniciar la aplicación desde la interfaz

Si el perfil declara `runtime.comando_inicio`, la interfaz habilita:

- **Iniciar objetivo**
- **Detener**
- **Reiniciar**

Para Tramitia el perfil declara:

```json
"runtime": {
  "comando_inicio": ["python", "run.py"],
  "directorio_trabajo": "."
}
```

### Recomendación

Deje marcada:

```text
Gestionar reinicio automáticamente al corregir
```

Así el auditor reinicia la aplicación cuando una corrección modifica código que necesita volver a cargarse.

Si usted ya arrancó la aplicación desde otra consola y no quiere que el auditor la controle, desmarque esa opción.

---

## 5. Ejecutar el diagnóstico

Pulse:

```text
Diagnosticar P1 + P2
```

El auditor ejecutará los controles configurados para:

### Pilar 1

- BOLA / acceso a objetos ajenos.
- RBAC / permisos por rol.
- Alcance del agente o asistente.

### Pilar 2

- CORS.
- Políticas HTTP.
- Configuraciones inseguras en archivos.
- Contenedores ejecutándose como usuario privilegiado.
- Otros controles declarados en el perfil.

---

## 6. Interpretar la tabla de resultados

La pestaña **Resultados** contiene:

| Columna | Significado |
|---|---|
| Pilar | P1 o P2 |
| Control | ID del control |
| Descripción | Qué se está verificando |
| Cuenta | Usuario usado en la prueba |
| Estado | Resultado |
| Corrección | Si existe receta automática |
| Detalle | Evidencia observada |

### Estados

```text
HALLAZGO
```

Se encontró una condición insegura.

```text
SIN_HALLAZGO
```

El control pasó.

```text
ERROR
```

No fue posible ejecutar correctamente la prueba.

Colores:

- rojo/rosado: **HALLAZGO**;
- verde: **SIN_HALLAZGO**;
- amarillo: **ERROR**.

La columna **Corrección** indica:

```text
Sí
```

Existe una receta automática.

```text
No
```

El auditor puede detectar el problema, pero no tiene una receta declarada para modificarlo automáticamente.

---

## 7. Revisar la corrección antes de aplicarla

Seleccione una fila con:

```text
Estado = HALLAZGO
Corrección = Sí
```

Luego abra la pestaña:

```text
Detalle / Corrección
```

Allí verá:

- control seleccionado;
- descripción;
- estado;
- archivo que será modificado;
- receta correctiva;
- operación que se aplicará.

Ejemplo:

```text
control: P1-BOLA-001
archivo: tramitia/api.py
estrategia: replace_exact
```

Revise esta información antes de modificar el código.

---

## 8. Aplicar una corrección individual

Con el hallazgo seleccionado pulse:

```text
Corregir seleccionado
```

La interfaz mostrará una confirmación indicando el control y archivo que se modificarán.

Al aceptar, el auditor ejecuta este proceso:

```text
1. Diagnosticar nuevamente
2. Confirmar que el hallazgo sigue existiendo
3. Guardar línea base
4. Calcular SHA-256 del archivo
5. Crear backup
6. Aplicar la receta
7. Reiniciar el objetivo si corresponde
8. Repetir el diagnóstico
9. Comprobar el control
10. Guardar el resultado
```

### Si la corrección funciona

El estado final será:

```text
CORREGIDO
```

### Si no funciona

El auditor restaura el backup automáticamente y el resultado será:

```text
NO_CORREGIDO
```

o:

```text
ERROR
```

según el caso.

---

## 9. Corregir todos los hallazgos corregibles

Después del diagnóstico puede pulsar:

```text
Corregir todos los hallazgos corregibles
```

El auditor toma todos los controles que cumplan:

```text
Estado = HALLAZGO
Corrección = Sí
```

y los procesa uno por uno.

Cada control tiene su propio:

- diagnóstico;
- backup;
- hash;
- cambio;
- verificación;
- rollback si falla.

Si un control produce error, el auditor continúa con los demás.

---

## 10. Verificar manualmente un control

Seleccione cualquier fila y pulse:

```text
Verificar seleccionado
```

Esto no modifica código.

Sirve para repetir el control y guardar evidencia adicional.

Ejemplos de uso:

- comprobar manualmente que una corrección sigue funcionando;
- volver a probar después de un cambio realizado por un desarrollador;
- generar una evidencia posterior independiente.

---

## 11. Consultar las evidencias

Abra la pestaña:

```text
Evidencias
```

En la izquierda aparecen las sesiones guardadas.

Seleccione una sesión para ver:

- `manifest.json`;
- `correccion.json`;
- diff generado;
- resultado de rollback manual, si existe.

Una sesión correctiva normalmente contiene:

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
        └── resultados.json
```

---

## 12. Abrir la carpeta de una evidencia

En la pestaña **Evidencias**:

1. seleccione una sesión;
2. pulse **Abrir carpeta**.

Se abrirá la carpeta física en Windows, macOS o Linux.

---

## 13. Revertir manualmente una corrección

Si desea volver al estado original después de una corrección exitosa:

1. abra **Evidencias**;
2. seleccione una sesión correctiva;
3. pulse:

```text
Revertir esta corrección
```

El auditor:

```text
restaura el backup
        ↓
reinicia el objetivo si corresponde
        ↓
calcula SHA-256
        ↓
compara con el hash original
```

Si coincide, mostrará:

```text
RESTAURADO
```

La evidencia del rollback queda en:

```text
verification/manual_rollback.json
```

---

## 14. Guardar el reporte actual

Después de diagnosticar puede pulsar:

```text
Guardar reporte actual
```

Elija un archivo JSON.

Ese archivo contiene el resultado completo del diagnóstico visible en la tabla.

---

## 15. Consultar el perfil activo

Pulse:

```text
Ver perfil JSON
```

La interfaz abre una ventana con el perfil que está utilizando.

Esto permite revisar:

- URL;
- usuarios;
- roles;
- endpoints;
- controles;
- runtime;
- correcciones.

---

## 16. Ejemplo completo con Tramitia

Flujo recomendado:

```text
1. Abrir auditor:
   python -m auditor_bola.gui

2. Perfil:
   config/tramitia.json

3. Código local:
   carpeta de tramitia-app 2.4.0-rc2

4. Mantener activa:
   Gestionar reinicio automáticamente al corregir

5. Iniciar objetivo

6. Diagnosticar P1 + P2

7. Revisar las filas rojas

8. Seleccionar:
   P1-BOLA-001

9. Revisar:
   Detalle / Corrección

10. Pulsar:
    Corregir seleccionado

11. Esperar la verificación

12. Confirmar estado:
    CORREGIDO

13. Revisar:
    Evidencias

14. Repetir con los demás controles o usar:
    Corregir todos los hallazgos corregibles
```

---

## 17. Ejemplo de lo que ocurre con BOLA

Antes:

```text
Bruno solicita el objeto de Ana
        ↓
HTTP 200
        ↓
HALLAZGO
```

El auditor aplica la receta sobre el archivo configurado.

Después:

```text
Bruno solicita el objeto de Ana
        ↓
HTTP 403
        ↓
SIN_HALLAZGO
        ↓
CORREGIDO
```

Al mismo tiempo, el diagnóstico vuelve a comprobar los accesos legítimos.

---

## 18. Qué hacer si "Corregir seleccionado" está deshabilitado

Compruebe:

1. que seleccionó una fila;
2. que el estado sea `HALLAZGO`;
3. que la columna **Corrección** diga `Sí`;
4. que haya seleccionado **Carpeta de código local**;
5. que el perfil tenga una receta para ese control.

Si la columna dice:

```text
Corrección = No
```

el auditor no puede modificar automáticamente ese hallazgo hasta que se agregue una receta segura al perfil.

---

## 19. Qué hacer si aparece ERROR

Revise la pestaña:

```text
Registro
```

Las causas comunes son:

- aplicación no iniciada;
- `base_url` incorrecta;
- credenciales inválidas;
- archivo no encontrado;
- versión del código distinta de la esperada;
- patrón de la receta no coincide;
- ruta local incorrecta.

Si una receta no encuentra el texto exacto esperado, el auditor se detiene y no modifica el archivo.

---

## 20. Recomendación de uso

Para una demostración o entrega académica, conserve por cada control:

```text
diagnóstico inicial
+ evidencia del hallazgo
+ backup/hash
+ diff de la corrección
+ diagnóstico posterior
+ estado CORREGIDO
```

Así puede demostrar no solo que el auditor detectó el problema, sino también que:

```text
detectó
→ corrigió
→ verificó
→ conservó evidencia
```

---

## 21. Flujo resumido

```text
CARGAR PERFIL
      ↓
SELECCIONAR CÓDIGO
      ↓
INICIAR OBJETIVO
      ↓
DIAGNOSTICAR
      ↓
REVISAR HALLAZGOS
      ↓
SELECCIONAR CONTROL
      ↓
REVISAR RECETA
      ↓
CORREGIR
      ↓
BACKUP + HASH
      ↓
APLICAR CAMBIO
      ↓
REINICIAR
      ↓
VERIFICAR
      ↓
┌─────────────────┐
│ ¿SE CORRIGIÓ?   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
   SÍ         NO
    │         │
CORREGIDO   ROLLBACK
    │         │
    └────┬────┘
         ↓
     EVIDENCIA
```
