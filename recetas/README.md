# Biblioteca de recetas reutilizables

Esta carpeta contiene recetas correctivas aceptadas por el auditor para poder
reutilizarlas en otros sistemas cuando el mismo patrón de vulnerabilidad pueda
resolverse de la misma forma.

Las recetas se organizan por `control_id`:

```text
recetas/
├── P1-BOLA/
│   └── <recipe_id>.json
├── P1-RBAC-004/
│   └── <recipe_id>.json
└── P2-CORS-001/
    └── <recipe_id>.json
```

Una receta de biblioteca no se aplica solo porque tenga el mismo control.
Antes de ofrecerla al usuario el auditor:

1. adapta la receta al archivo actual;
2. ejecuta un preview en memoria;
3. descarta la receta si el patrón no coincide;
4. muestra el código resultante y el diff;
5. requiere confirmación humana;
6. aplica el ciclo normal de backup, verificación y rollback.

Las recetas marcadas como `verificada: true` ya han corregido al menos una
instancia y tienen prioridad sobre recetas no verificadas.

No deben almacenarse credenciales, API keys ni archivos fuente completos en
esta carpeta.
