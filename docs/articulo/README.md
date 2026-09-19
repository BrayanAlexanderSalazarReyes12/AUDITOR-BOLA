# Evidencias y figuras para el artículo

Esta carpeta reúne material publicable y una guía para preservar evidencia técnica verificable de Aegis Auditor.

## Figuras recomendadas

| Figura | Archivo | Uso |
|---|---|---|
| 1 | figuras/figura_01_dos_pilares.svg | Alcance conceptual |
| 2 | figuras/figura_02_incorporacion_multitecnologia.svg | Generación automática del perfil |
| 3 | figuras/figura_03_ciclo_correctivo.svg | Diagnóstico, corrección, verificación y rollback |
| 4 | figuras/figura_04_aprendizaje_medicinas.svg | Aprendizaje y reutilización |
| 5 | figuras/figura_05_evidencia_reproducible.svg | Trazabilidad experimental |

Los SVG son figuras explicativas editables. No deben presentarse como evidencia experimental.

## Capturas reales recomendadas

1. Nuevo proyecto después de seleccionar una aplicación.
2. Stack, runtime y endpoints detectados.
3. Perfil JSON generado.
4. Baseline con hallazgos.
5. Tres propuestas de corrección de IA.
6. Diff previo a aplicar.
7. Resultado CORREGIDO después de re-verificación.
8. Medicina almacenada en recetas/conocimiento.
9. Reutilización de una medicina en Java, Node y Python.
10. Estructura de una sesión de evidencias.

Use capturas/README.md como checklist.

## Evidencia mínima por experimento

    evidencias/<sesion>/
      manifest.json
      baseline/resultados.json
      cambios/correccion.json
      cambios/*.diff
      verification/resultados.json

Con IA conservar también contexto_redactado.json, propuestas.json, seleccion.json y conocimiento_aprendido.json.

## Publicación

La interfaz puede exportar una copia destinada al artículo. El paquete excluye backups de código y redacta campos con nombres sensibles como password, token, secret, cookie, Authorization o API key. La evidencia original no se modifica.
