# Aegis Auditor v1.4.1

## Correcciones IA adaptativas

- El flujo de corrección prueba automáticamente la propuesta seleccionada y las alternativas válidas de la misma ronda.
- Cada intento queda asociado a attempt_number, propuesta, estrategia, hipótesis y resultado de verificación.
- Si dos intentos consecutivos no eliminan el hallazgo, Aegis activa strategy_reset y solicita a la IA un enfoque sustancialmente diferente.
- El presupuesto máximo del ciclo adaptativo es de 6 intentos; un intento fallido conserva la evidencia y el ciclo correctivo ejecuta rollback cuando corresponde.
- El criterio de éxito continúa siendo dinámico: el hallazgo objetivo debe pasar a SIN_HALLAZGO y no deben romperse las filas legítimas previamente seguras.
- Las recetas verificadas continúan alimentando la biblioteca concreta y la medicina semántica reutilizable.

## Interfaz de verificación

Después de una corrección verificada se muestra una ventana dedicada con:

1. identificación del lenguaje;
2. aplicación del parche;
3. reinicio del servicio;
4. verificación de seguridad;
5. código antes y después con números de línea;
6. diff completo;
7. historial de intentos adaptativos.

El código se presenta con desplazamiento vertical y horizontal para evitar que el usuario pierda contexto en archivos largos.

## QA

Se agrega cobertura para la orquestación adaptativa y el cambio de estrategia después de dos fallos.

## Seguridad

La IA no decide por sí sola que un parche es correcto. El estado PATCH_VERIFIED / PATCH_VERIFIED_WITH_WARNINGS continúa dependiendo de la evidencia producida por el ciclo de validación, reinicio, reescaneo y QA.