# Asistente IA para generar recetas correctivas

El Asistente IA amplía el auditor cuando un hallazgo no tiene receta o cuando el usuario quiere comparar alternativas antes de corregir.

## Principio de seguridad

Gemma **no modifica código directamente**. El flujo es:

```text
HALLAZGO
   ↓
Generar 3 propuestas con IA
   ↓
MINIMA | ESTRUCTURAL | ALTERNATIVA
   ↓
Usuario selecciona una
   ↓
Preview del diff sin escribir
   ↓
Confirmación humana
   ↓
Motor determinista
   ↓
backup → aplicar → reiniciar → verificar → rollback
```

La decisión final permanece en el usuario.

## Proveedor IA: Gemma del Laboratorio UTB

El auditor reutiliza la configuración ya existente de OpenCode. Por defecto
busca:

```text
~/.config/opencode/opencode.json
```

y utiliza el proveedor:

```text
llmlab
```

con el modelo:

```text
lab-coder
```

No es necesario volver a pegar una API key en la interfaz.

Si en OpenCode la clave está declarada mediante una variable:

```json
"apiKey": "{env:UTB_LLM_API_KEY}"
```

esa variable debe existir en la misma sesión desde la que se ejecuta el
auditor. Si OpenCode tiene una clave literal en su archivo local, el auditor
puede leerla localmente, pero no la imprime ni la almacena en las evidencias.

El endpoint usado por el auditor es:

```text
<baseURL>/chat/completions
```

Puede sobrescribir la ruta del archivo de OpenCode para pruebas con:

```powershell
$env:OPENCODE_CONFIG="C:\ruta\a\opencode.json"
```

Luego ejecute:

```powershell
python -m auditor_bola.gui
```

## Carga automática del archivo relacionado

Cuando se selecciona un resultado, la GUI conserva el método, la ruta y el
tipo de control de esa fila. Con esos datos intenta resolver automáticamente
el archivo fuente correspondiente.

Ejemplo:

```text
P1-BOLA
PATCH /reservas/{id}
        ↓
selección del hallazgo
        ↓
src/.../ReservaController.java
        ↓
archivo cargado automáticamente en Asistente IA
```

Si el perfil declara `archivos_fuente`, esa asociación tiene prioridad.
Cuando no existe, el auditor utiliza una búsqueda genérica sobre el código.
El botón **Elegir archivo** permanece disponible para sobrescribir la
selección automática.

## Uso desde la interfaz

1. Cargue un perfil.
2. Seleccione la carpeta local del código.
3. Ejecute **Diagnosticar P1 + P2**.
4. Seleccione un hallazgo.
5. Pulse **Generar recetas con IA**.
6. El auditor intenta cargar automáticamente el archivo relacionado. Si no encuentra uno adecuado, pulse **Elegir archivo**.
7. Pulse **Generar 3 recetas con Gemma**.
8. Se abrirá automáticamente una ventana independiente con tres pestañas:
   - **MINIMA**;
   - **ESTRUCTURAL**;
   - **ALTERNATIVA**.
9. En cada pestaña puede revisar:
   - explicación y riesgo;
   - consideraciones;
   - **código resultante completo**;
   - diff antes/después con scroll horizontal y vertical.
10. Cambiar de pestaña selecciona esa receta también en la ventana principal.
11. Desde la ventana independiente puede pulsar **Aplicar receta seleccionada** o **Guardar receta seleccionada en perfil**.
12. Si cierra la ventana, puede volver a abrirla con **Ver propuestas en ventana**.
13. El auditor ejecutará su ciclo normal de respaldo, corrección, verificación y rollback.

## Protección de información

Antes de enviar código a la IA, el módulo intenta redactar patrones comunes de:

- contraseñas;
- tokens;
- API keys;
- encabezados Bearer;
- claves privadas.

No se envían las cuentas ni las contraseñas declaradas en el perfil.

Para archivos grandes se recorta el contexto y se priorizan zonas relacionadas con el hallazgo.

## Evidencia IA

Cada generación crea:

```text
evidencias/
└── ia/
    └── <sesion>/
        ├── contexto_redactado.json
        ├── propuestas.json
        ├── seleccion.json
        ├── perfil_antes.json      (si se guarda en perfil)
        └── perfil_despues.json    (si se guarda en perfil)
```

La evidencia del ciclo correctivo sigue guardándose en las sesiones normales del auditor.

## Importante

Una propuesta IA no se considera correcta por haber sido generada. Solo puede terminar como `CORREGIDO` si:

1. el preview coincide con el código actual;
2. el usuario la selecciona;
3. el motor crea el backup;
4. la receta se aplica;
5. el objetivo se reinicia cuando corresponde;
6. el mismo control se vuelve a ejecutar;
7. el hallazgo desaparece.

Si falla la verificación, se conserva el comportamiento de rollback del auditor.
