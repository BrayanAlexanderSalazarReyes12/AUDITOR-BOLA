# Asistente IA para generar recetas correctivas

El Asistente IA amplía el auditor cuando un hallazgo no tiene receta o cuando el usuario quiere comparar alternativas antes de corregir.

## Principio de seguridad

Ningún proveedor IA **modifica código directamente**. El flujo es:

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

## Proveedores IA configurables

Aegis ya no depende de que OpenCode esté instalado o configurado en el equipo.
Desde **Configuración → Inteligencia artificial** se pueden administrar varios
perfiles de proveedor.

Cada perfil conserva:

- nombre visible;
- URL base;
- modelo;
- API key local cuando el proveedor la requiere.

La pantalla permite **crear, editar, duplicar, eliminar y activar** perfiles.
Cada perfil puede tener un rol. Aegis usa esos roles para routing automático:
`coder_primary` → `analyst_secondary` → `fallback`. El perfil activo sigue
sirviendo como preferencia/compatibilidad cuando no existe una cadena completa.

Configuración rápida recomendada:

```text
Qwen3-Coder Free · OpenRouter
  base_url: https://openrouter.ai/api/v1
  model: qwen/qwen3-coder:free
  role: coder_primary

Gemini 2.5 Flash · Google AI
  base_url: https://generativelanguage.googleapis.com/v1beta/openai
  model: gemini-2.5-flash
  role: analyst_secondary

UTB / lab-coder
  role: fallback
```

También se conservan perfiles para Ollama, LM Studio u otros endpoints
compatibles con `/chat/completions`.

El endpoint esperado continúa siendo compatible con:

```text
<baseURL>/chat/completions
```

La configuración local se guarda en `config/ai-provider.json` dentro de los
datos persistentes de Aegis. El archivo usa un esquema con una lista de
perfiles y un `active_profile_id`. Las versiones anteriores que tenían un
único proveedor se migran automáticamente al nuevo formato.

La API key no se copia a perfiles de aplicaciones auditadas ni a evidencias.
En la interfaz se muestra solo si un perfil tiene o no una clave; nunca se
devuelve la clave en los listados públicos de perfiles.

También se soportan las variables:

```text
AEGIS_AI_BASE_URL
AEGIS_AI_MODEL
AEGIS_AI_API_KEY
```

Estas variables se usan cuando todavía no existe un perfil local seleccionado.

### Importación opcional desde OpenCode

Si el equipo ya tiene OpenCode configurado, Aegis puede importar su proveedor
como un perfil adicional mediante **Importar desde OpenCode**.

Por compatibilidad se busca:

```text
~/.config/opencode/opencode.json
```

y se puede sobrescribir la ruta con:

```powershell
$env:OPENCODE_CONFIG="C:\ruta\a\opencode.json"
```

La importación crea un perfil independiente; después Aegis puede usarlo sin
depender de OpenCode para seleccionarlo.


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
7. Pulse **Generar 3 recetas con IA**. Aegis selecciona automáticamente el
   proveedor según rol, disponibilidad y fallos previos.
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
11. Desde la ventana independiente puede pulsar **Aplicar receta seleccionada** o **Guardar propuesta en perfil**. La medicina reusable solo se aprende después de una verificación `CORREGIDO`.
12. Si cierra la ventana, puede volver a abrirla con **Ver propuestas en ventana**.
13. El auditor ejecutará su ciclo normal de respaldo, corrección, verificación y rollback.

## Cuando una receta no corrige el hallazgo

El auditor verifica la fila exacta que originó la corrección. La identidad de
la prueba incluye, cuando están disponibles:

```text
control_id + cuenta + método + ruta + tipo_control
```

Esto evita tratar como una sola prueba todas las filas que comparten
`P1-BOLA`.

Además de comprobar la fila objetivo, el auditor vigila regresiones. Una fila
que antes estaba en `SIN_HALLAZGO` no puede convertirse en
`HALLAZGO` o `ERROR` por efecto de la receta.

Si la receta no funciona:

```text
aplicar
  ↓
verificar fila exacta
  ↓
NO_CORREGIDO
  ↓
rollback
  ↓
¿Generar 3 nuevas recetas con el fallo?
  ↓
el motor multimodelo recibe el intento anterior + resultado de verificación
```

La segunda ronda incluye la matriz de pruebas del mismo control para que el modelo
conozca qué combinaciones ya eran seguras y cuál debe corregir. También recibe
el diff de la receta fallida y se le indica que no repita la misma solución ni
una variante superficial.

El feedback enviado al proveedor IA pasa por la misma redacción de secretos utilizada
para el código fuente.

## Aprendizaje de una medicina reutilizable

Una propuesta guardada en el perfil todavía no se considera conocimiento
reutilizable.

El aprendizaje ocurre únicamente cuando el ciclo termina en `CORREGIDO`.
En ese momento el auditor toma:

- hallazgo original;
- matriz de pruebas;
- código antes;
- código después;
- diff;
- propuesta que funcionó;
- resultado de verificación.

El proveedor IA transforma ese caso concreto en una medicina semántica que evita nombres
propios del sistema origen.

Se guarda en:

```text
recetas/conocimiento/<familia_control>/<knowledge_id>.json
```

La medicina contiene causa raíz, invariante de seguridad, estrategia general,
señales de aplicabilidad, requisitos, anti-patrones y contrato de
verificación.

### Uso en otro aplicativo

Al seleccionar un hallazgo y resolver su archivo, la GUI muestra:

```text
Medicinas conocidas: N
[ Ver medicinas ]
```

Una medicina puede encontrarse por ID exacto, por familia de control
(`P1-BOLA-001` y `P1-BOLA-017`, por ejemplo) o por `tipo_control`.

Al pulsar **Adaptar esta medicina al aplicativo**, el proveedor IA no copia el parche
original. Recibe la medicina verificada y el código actual y produce tres
implementaciones específicas para ese sistema.

Luego se mantiene el mismo flujo:

```text
medicina conocida
    ↓
adaptar al código actual
    ↓
3 implementaciones
    ↓
preview
    ↓
selección humana
    ↓
aplicar
    ↓
verificar
    ↓
CORREGIDO / ROLLBACK
```

Los parches exactos ya verificados se siguen conservando como instancias
concretas, pero son secundarios frente al conocimiento semántico.

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


## Routing multimodelo y presupuesto de contexto

Aegis calcula el `max_tokens` de cada petición usando la ventana de contexto
del perfil y una estimación conservadora del prompt. Ya no solicita siempre
8.192 tokens de salida.

Para `lab-coder` se usa por defecto una ventana de 20.480 tokens y un máximo
de 4.096 tokens de salida. Si el contexto no cabe, Aegis compacta código,
historial y evidencia antes de enviar. Si el proveedor todavía responde con
un error de ventana de contexto, se ejecuta una segunda compactación más
agresiva con una salida menor antes de pasar al siguiente proveedor.

Con Qwen3-Coder y Gemini 2.5 Flash los presets declaran ventanas grandes de
contexto, pero Aegis mantiene la misma disciplina: solo envía código relevante,
redacta secretos y conserva trazabilidad del proveedor realmente utilizado.

El orden normal es:

```text
generación de parche:
Qwen3-Coder → Gemini → fallback

diagnóstico tras fallos:
Gemini → Qwen3-Coder → fallback
```

Cada sesión IA registra `provider_trace`, incluyendo proveedor, modelo,
estimación de tokens, compactación y fallos de routing, sin almacenar API keys.
