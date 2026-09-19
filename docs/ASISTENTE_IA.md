# Asistente IA para generar recetas correctivas

El Asistente IA amplía el auditor cuando un hallazgo no tiene receta o cuando el usuario quiere comparar alternativas antes de corregir.

## Principio de seguridad

La IA **no modifica código directamente**. El flujo es:

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

## Configurar la API

La clave no se guarda en el perfil JSON ni en el repositorio.

En PowerShell:

```powershell
$env:OPENAI_API_KEY="TU_CLAVE"
```

Opcionalmente puede cambiar el modelo:

```powershell
$env:AUDITOR_AI_MODEL="gpt-6-astra"
```

También puede cambiar el endpoint base:

```powershell
$env:AUDITOR_AI_BASE_URL="https://api.openai.com/v1"
```

Luego ejecute:

```powershell
python -m auditor_bola.gui
```

## Uso desde la interfaz

1. Cargue un perfil.
2. Seleccione la carpeta local del código.
3. Ejecute **Diagnosticar P1 + P2**.
4. Seleccione un hallazgo.
5. Pulse **Generar recetas con IA**.
6. Si el auditor conoce el archivo relacionado lo propondrá automáticamente. Si no, pulse **Elegir archivo**.
7. Pulse **Generar 3 recetas con IA**.
8. Compare las propuestas:
   - **MINIMA**: cambio pequeño y localizado.
   - **ESTRUCTURAL**: mejora de diseño o centralización.
   - **ALTERNATIVA**: solución distinta al mismo problema.
9. Seleccione una propuesta para ver:
   - explicación;
   - riesgo declarado;
   - si requiere reinicio;
   - receta normalizada;
   - diff previo.
10. Si el preview es válido, pulse **Aplicar receta seleccionada**.
11. El auditor ejecutará su ciclo normal de respaldo, corrección, verificación y rollback.
12. Si desea reutilizar la receta después, pulse **Guardar receta en perfil**.

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
