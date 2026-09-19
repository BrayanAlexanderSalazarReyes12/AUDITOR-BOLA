# Arquitectura de conocimiento correctivo

## Problema que resuelve

Un parche literal no es una receta universal. Dos aplicaciones con el mismo
hallazgo pueden usar lenguajes, frameworks, nombres y arquitecturas
completamente diferentes.

Por eso el auditor separa tres niveles:

```text
HALLAZGO
   ↓
MEDICINA SEMÁNTICA
   ↓
IMPLEMENTACIÓN CONCRETA
   ↓
VERIFICACIÓN DINÁMICA
```

## Medicina semántica

Representa el conocimiento que puede transferirse entre aplicativos:

- qué causa el fallo;
- qué propiedad de seguridad debe cumplirse;
- qué señales indican que la medicina aplica;
- qué estrategia seguir;
- qué anti-patrones evitar;
- qué pruebas deben pasar.

No contiene una ruta fija ni exige que existan los mismos nombres de variables.

## Implementación concreta

Es el parche específico producido para el código actual. Actualmente el motor
lo normaliza a las operaciones declarativas soportadas por `Correccion`.

La implementación nunca se considera conocimiento universal.

## Aprendizaje

Cuando una implementación termina en `CORREGIDO`, el auditor conserva la
evidencia concreta y solicita a Gemma una generalización del caso exitoso.

El resultado se almacena en:

```text
recetas/conocimiento/<familia_control>/<knowledge_id>.json
```

## Transferencia

Para un nuevo aplicativo:

1. se detecta el hallazgo;
2. se localiza el código relacionado;
3. se recupera conocimiento por control, familia o tipo;
4. Gemma adapta la medicina al código actual;
5. el usuario revisa tres implementaciones;
6. el motor aplica una;
7. se repite la prueba exacta;
8. se comprueban regresiones;
9. si falla se ejecuta rollback.

Cada éxito adicional incrementa el historial del conocimiento y confirma que
la medicina funciona en más de un contexto.

## Límite deliberado

El sistema no promete que un mismo texto de parche funcione en cualquier
aplicación. Esa promesa sería técnicamente incorrecta. Lo que se reutiliza es
el conocimiento de remediación y su contrato de seguridad; la implementación
se vuelve a generar para cada código.
