# Biblioteca correctiva

Esta carpeta conserva dos tipos de conocimiento diferentes.

## 1. Conocimiento semántico

```text
recetas/
└── conocimiento/
    └── <familia_control>/
        └── <knowledge_id>.json
```

Este es el nivel reusable entre aplicativos. No almacena un `buscar` /
`reemplazar` como solución universal.

Cada medicina contiene conceptos como:

- causa raíz;
- invariante de seguridad;
- estrategia general;
- señales de aplicabilidad;
- requisitos de implementación;
- anti-patrones;
- contrato de verificación;
- tecnologías donde ya fue observada;
- cantidad de usos exitosos.

La medicina se crea únicamente después de que una implementación concreta
termina en `CORREGIDO`.

Cuando aparece el mismo problema en otro aplicativo, Gemma recibe esa medicina
junto con el código actual y genera una implementación nueva adaptada al
proyecto.

## 2. Instancias concretas

```text
recetas/
└── <control_id>/
    └── <recipe_id>.json
```

Son parches exactos que ya funcionaron en un sistema. Se conservan para
trazabilidad y para reutilización directa cuando el código nuevo realmente
coincide con el patrón.

No se consideran universales.

## Regla

```text
Parche concreto = cómo se corrigió un caso.
Medicina semántica = qué propiedad hay que restaurar y cómo comprobarla.
```

El auditor siempre ejecuta preview, confirmación humana, backup, verificación
y rollback. Compartir el mismo nombre de control nunca basta para modificar un
archivo automáticamente.

No deben almacenarse credenciales, API keys ni archivos fuente completos en
esta carpeta.
