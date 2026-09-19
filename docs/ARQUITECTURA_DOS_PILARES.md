# Arquitectura multitecnología basada en dos pilares

## Principio

    Tecnología del proyecto
             ↓
      Perfil / adaptadores
             ↓
       Motor de Aegis
             ↓
      Pilar 1 + Pilar 2

La tecnología determina cómo localizar, iniciar y probar la aplicación. Los pilares determinan qué propiedad de seguridad se evalúa.

## Pilar 1 — Identidad y Control de Acceso

Razona sobre identidad, propiedad de recursos, roles, acceso esperado y alcance de agentes.

Una falta de autorización puede aparecer en Java Servlet, Node/Express, Python/Flask, PHP, .NET u otro stack. La implementación cambia; la propiedad de seguridad pertenece al mismo Pilar 1.

## Pilar 2 — Arquitectura y Configuración

Evalúa propiedades de seguridad de la construcción/configuración: CORS, respuestas HTTP, patrones de código/configuración, contenedores y controles adicionales reutilizables.

## Qué significa cualquier tecnología

Aegis utiliza tres niveles:

1. detección automática conocida: stack reconocido y perfil sugerido;
2. configuración guiada/adaptador reusable: tecnología no detectada automáticamente;
3. modo external: Aegis prueba un objetivo ya desplegado sin administrar su runtime.

Nunca se debe agregar lógica específica como 'si sistema == moodle'. Se agregan capacidades reutilizables: runtime, transporte, autenticación, localización de fuente, controles de Pilar 1/Pilar 2 y contratos de verificación.

## Tecnologías

El detector puede evolucionar. Actualmente existe soporte o integración por perfil para JavaScript/TypeScript, Node/Express, Python/Flask/Django/FastAPI, Java/Servlet/Spring, PHP/Laravel/Moodle, .NET, Go, Ruby y Docker/Compose. Los stacks desconocidos deben caer a configuración guiada en vez de ser rechazados.

## Límite científico

El artículo debe describir la cobertura en términos de los controles implementados bajo Pilar 1 y Pilar 2, no como un escáner universal de todos los CWE.
