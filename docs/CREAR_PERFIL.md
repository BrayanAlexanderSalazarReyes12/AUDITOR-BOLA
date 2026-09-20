# Crear un perfil para cualquier aplicación

El auditor no debe conocer el nombre, lenguaje o framework del sistema objetivo. Para integrar una aplicación nueva se crea un **perfil JSON** y, cuando exista una corrección automática, la receta también vive en ese perfil.

La plantilla base está en `config/plantilla.json`.

## 1. Qué puede cambiar entre aplicaciones

El perfil declara:

- nombre y versión del sistema;
- URL local, si tiene una interfaz HTTP;
- cuentas y roles de prueba;
- tipo de autenticación;
- recursos/objetos que deben respetar propiedad;
- operaciones reservadas por rol;
- controles de arquitectura/configuración;
- comando para iniciar la copia local;
- recetas de corrección opcionales.

El motor Python permanece igual.

## 2. Lenguajes y frameworks

Las inspecciones de archivos y las correcciones declarativas son de texto, por lo que no dependen de Python. Un objetivo puede ser Java/Spring, Node/Express, PHP/Laravel, .NET, Go, Python/Flask, Ruby, etc.

Ejemplos de `runtime.comando_inicio`:

```json
["python", "run.py"]
```

```json
["java", "-jar", "app.jar"]
```

```json
["npm", "start"]
```

```json
["dotnet", "MiAplicacion.dll"]
```

Si el sistema ya está levantado, no es necesario que el auditor administre su proceso.

## 3. Autenticación integrada

Cada cuenta acepta:

### HTTP Basic

```json
{
  "username": "ana",
  "password": "clave",
  "role": "usuario",
  "auth_type": "basic"
}
```

### Bearer token

```json
{
  "username": "api-user",
  "password": null,
  "role": "usuario",
  "auth_type": "bearer",
  "token": "TOKEN"
}
```

### Encabezados personalizados

```json
{
  "username": "servicio",
  "password": null,
  "role": "servicio",
  "auth_type": "header",
  "headers": {
    "X-API-Key": "valor"
  }
}
```

### Sin autenticación

Use `"auth_type": "none"`.

Los sistemas con flujos especiales (OAuth interactivo, SSO, MFA, protocolos no HTTP) requieren un adaptador específico; la arquitectura está preparada para añadirlo sin meter lógica del sistema objetivo en los motores de los pilares.

## 4. Pilar 1

El perfil mantiene un registro canónico explícito:

```json
{
  "chequeos_pilar1": []
}
```

Cada entrada indica `tipo: "bola"`, `tipo: "acceso"` o
`tipo: "alcance_agente"`. Los campos históricos `endpoints`,
`chequeos_acceso` y `chequeos_agente` siguen presentes como vistas
compatibles con el motor, pero `chequeos_pilar1` permite auditar, mostrar y
persistir en un solo lugar todo el Pilar 1.

Durante la auto-configuración Aegis no se limita a descubrir rutas. También
revisa **tests, fixtures, datos semilla y archivos de soporte** para buscar
contratos de seguridad verificables:

- relación explícita `objeto/id -> propietario` para construir BOLA;
- peticiones de prueba con usuario/rol y código HTTP esperado para reconstruir
  RBAC/ABAC;
- pruebas que comparan API directa con asistente/agente para reconstruir
  controles de alcance.

Solo se activa un control cuando existen datos suficientes para ejecutarlo sin
inventar la política. Las coincidencias incompletas permanecen en
`metadata_detectada.candidatos_pilar1` hasta que puedan confirmarse.

### BOLA / propiedad de objetos

```json
{
  "id_control": "P1-BOLA-001",
  "descripcion": "Un usuario no lee objetos ajenos",
  "metodo": "GET",
  "ruta": "/api/recurso/{id}",
  "id_prueba": "10",
  "propietario_esperado": "usuario1"
}
```

El motor cruza todas las cuentas contra el recurso y compara acceso esperado vs. respuesta real.

### RBAC / operaciones reservadas

```json
{
  "id_control": "P1-RBAC-001",
  "nombre": "La operación administrativa está restringida",
  "cuenta": "usuario1",
  "metodo": "POST",
  "ruta": "/api/admin/accion",
  "cuerpo": {},
  "acceso_esperado": false
}
```

### Alcance de agentes/asistentes

Cuando existe un agente que ejecuta herramientas, `chequeos_agente` compara lo que la identidad ve por API directa con lo que obtiene por medio del agente.

## 4.1 Asociación automática con archivos fuente

El Asistente IA puede localizar automáticamente el archivo relacionado con un
hallazgo. La resolución es independiente del lenguaje y usa dos niveles:

1. **Metadatos explícitos del perfil** mediante `archivos_fuente` y
   `pistas_codigo`.
2. **Búsqueda heurística** cuando esos metadatos no existen, usando el método
   HTTP, la ruta, la descripción del control, el nombre/ruta de los archivos y
   patrones comunes de frameworks.

Ejemplo para un endpoint:

```json
{
  "id_control": "P1-BOLA-001",
  "descripcion": "Un usuario no puede modificar reservas ajenas",
  "metodo": "PATCH",
  "ruta": "/reservas/{id}",
  "id_prueba": "10",
  "propietario_esperado": "usuario1",
  "archivos_fuente": [
    "src/main/java/com/app/ReservaController.java"
  ],
  "pistas_codigo": [
    "reserva",
    "autorizar",
    "propietario"
  ]
}
```

Los campos son opcionales. Si `archivos_fuente` no está presente, el auditor
explora archivos de código y configuración comunes, incluyendo Java, Kotlin,
Python, JavaScript/TypeScript, PHP, C#, Go, Ruby, JSP, XML, YAML y properties.

Cuando una misma ID de control se utiliza para GET, PATCH u otros métodos, la
GUI conserva internamente el método y la ruta de la fila seleccionada para
resolver el archivo correcto. Por eso un hallazgo `PATCH /reservas/{id}`
puede apuntar a un archivo diferente del hallazgo
`GET /reservas/{id}`, aunque ambos compartan `P1-BOLA`.

La selección automática no elimina el botón **Elegir archivo**: ese botón
permite anular manualmente la sugerencia cuando una aplicación tiene una
estructura poco convencional.

## 5. Pilar 2

Controles incluidos actualmente:

- `cors_reflection`: detecta reflexión de Origin junto con credenciales.
- `http_status_policy`: exige que una operación sensible sea rechazada con códigos definidos.
- `source_contains`: comprueba patrones inseguros/seguros en archivos.
- `docker_non_root`: verifica que la imagen declare un usuario no root.

Estos controles son declarativos y no dependen del framework del objetivo.

## 6. Correcciones

Las correcciones no se escriben dentro del motor. El perfil indica **qué archivo** y **qué transformación** aplicar.

### Reemplazo exacto

```json
{
  "control_id": "P2-CONFIG-001",
  "archivo": "config/app.properties",
  "operaciones": [
    {
      "estrategia": "replace_exact",
      "buscar": "debug=true",
      "reemplazar": "debug=false"
    }
  ]
}
```

### Expresión regular

```json
{
  "control_id": "P2-CONFIG-002",
  "archivo": "src/config.js",
  "operaciones": [
    {
      "estrategia": "regex_replace",
      "patron": "DEBUG\\s*=\\s*true",
      "sustitucion": "DEBUG = false"
    }
  ]
}
```

Una receta puede tener varias operaciones. Si una operación no encuentra el texto esperado, el auditor se detiene y no declara éxito.

## 7. Ciclo correctivo

```text
diagnóstico
   ↓
hallazgo confirmado
   ↓
línea base + hash
   ↓
backup
   ↓
receta del perfil
   ↓
reinicio opcional
   ↓
misma prueba
   ↓
regresión
   ↓
CORREGIDO / NO CORREGIDO / ERROR
   ↓
rollback automático si falla
```

## 8. Regla de diseño

**Agregar una aplicación nueva no debe requerir editar `engine.py`, `pilar2.py`, `corrective.py`, `cycle.py` ni la GUI.**

Se agrega un perfil JSON. Solo cuando aparece un mecanismo de autenticación, protocolo o clase de control que el auditor todavía no conoce se crea un adaptador/control reutilizable, no código específico de la aplicación.


## Inventario automático de endpoints

Al incorporar una aplicación, Aegis recorre todos los archivos de texto
relevantes del proyecto (excluyendo dependencias y artefactos generados como
`node_modules`, `dist`, `build`, `target`, `venv`, etc.) y construye un
inventario estático de rutas.

El perfil guardado en `config/` incluye:

```json
{
  "endpoints_detectados": [
    {
      "metodo": "GET",
      "ruta": "/api/usuarios/{id}",
      "archivo": "src/UsuarioController.java",
      "framework": "spring",
      "archivos": ["src/UsuarioController.java"],
      "frameworks": ["spring"]
    }
  ]
}
```

`endpoints_detectados` es el inventario automático y no debe confundirse con
`endpoints`, que contiene controles BOLA ya configurados con propietario e ID
de prueba.

El detector no aplica un límite artificial de 300 rutas. Reconoce, entre otros:
Spring, Servlet/WebServlet, web.xml, JAX-RS, Flask/FastAPI, Express/Fastify,
NestJS, Django, Laravel, Symfony, ASP.NET, Go, Rails/Sinatra/Phoenix, Rust,
Play, Next.js y especificaciones OpenAPI/Swagger. También puede registrar
referencias encontradas en formularios, fetch, axios y jQuery cuando ayudan a
descubrir rutas que no tienen una declaración de servidor visible.

Las rutas creadas dinámicamente en tiempo de ejecución, desde plugins externos,
bases de datos o metaprogramación pueden requerir validación en runtime.


## Fuentes documentales y archivos de texto

Además del código fuente, Aegis revisa documentación y archivos de texto que
puedan contener cuentas, roles, URLs o rutas de servicio. Esto incluye, entre
otros:

- `README.md`, `*.md`, `*.markdown`, `*.rst`, `*.adoc`.
- Manuales y guías, incluso archivos sin una extensión conocida si su contenido
  parece texto.
- `.env`, `*.properties`, `*.ini`, `*.conf`, `*.cfg`, YAML, TOML,
  XML, SQL, CSV y JSON.
- Archivos `.http` / `.rest`, ejemplos `curl`, tablas Markdown y
  documentación REST.
- Colecciones JSON con estructuras tipo Postman/Insomnia.
- Referencias de formularios HTML/JSP, `fetch`, `axios` y jQuery.

Las coincidencias conservan trazabilidad mediante `tipo_fuente` y el archivo
de origen. Los archivos binarios y dependencias generadas se excluyen del
escaneo.

Ejemplo de evidencia de cuenta detectada:

```json
{
  "username": "qa.admin",
  "role": "ADMIN",
  "archivo": "README.md",
  "tipo_fuente": "documentacion",
  "confianza": "media"
}
```

Ejemplo de endpoint detectado desde documentación:

```json
{
  "metodo": "POST",
  "ruta": "/api/login",
  "archivos": ["docs/MANUAL_API.md"],
  "frameworks": ["documentation-reference"],
  "tipos_fuente": ["documentacion"]
}
```

El análisis es estático y exhaustivo sobre archivos de texto relevantes, pero
una ruta creada únicamente en tiempo de ejecución, descargada desde un servicio
externo o generada desde base de datos puede requerir validación dinámica.


## Detección de versión de la aplicación

Aegis no asigna una versión ficticia al proyecto. Durante la incorporación
intenta detectar la versión real desde fuentes priorizadas, entre ellas:

- `auditor-package.json`.
- Archivos `VERSION`, `VERSION.txt`, `.version`.
- `package.json`, `composer.json`, `pyproject.toml`, `setup.cfg`,
  `setup.py`, `Cargo.toml`, `pubspec.yaml`.
- `pom.xml`, `build.gradle`, `build.gradle.kts`,
  `gradle.properties`.
- Archivos `*.csproj`, `mix.exs`, `version.php`,
  `META-INF/MANIFEST.MF`.
- Constantes como `__version__`, `APP_VERSION`,
  `APPLICATION_VERSION`, `PROJECT_VERSION` y claves como
  `info.app.version`.
- README, manuales y documentación como fallback cuando no existe una fuente
  de mayor confianza.

El JSON generado conserva tanto la versión elegida como su procedencia:

```json
{
  "version_objetivo": "3.4.1",
  "metadata_detectada": {
    "version_detectada": "3.4.1",
    "version_fuente": "pom.xml",
    "version_confianza": "alta",
    "version_candidatas": []
  }
}
```

Si no existe ninguna versión verificable, Aegis usa `"desconocida"` en lugar
de inventar `1.0.0`.


## Selección y fallback de runtime

Aegis puede guardar más de una estrategia de arranque para una misma
aplicación. Por ejemplo, si existe `docker-compose.yml` pero el proyecto
también puede ejecutarse con `npm start`, el perfil conserva ambas opciones.

Durante el arranque Aegis valida, en orden:

1. que exista el directorio de trabajo;
2. que el comando de inicio esté disponible en el proyecto o en `PATH`;
3. que también estén disponibles los comandos de preparación requeridos.

Si la estrategia principal no está disponible, Aegis intenta la siguiente y
registra cuál descartó y por qué. Cada estrategia puede declarar su propia
`base_url`, de forma que un fallback de Docker a Node.js pueda cambiar, por
ejemplo, de `http://127.0.0.1:8080` a `http://127.0.0.1:3000`.

Ejemplo:

```json
{
  "runtime": {
    "nombre": "Docker Compose",
    "comando_inicio": ["docker", "compose", "up", "-d"],
    "base_url": "http://127.0.0.1:8080",
    "alternativas": [
      {
        "nombre": "Node.js (npm)",
        "comando_inicio": ["npm", "start"],
        "base_url": "http://127.0.0.1:3000"
      }
    ]
  }
}
```

Si un arranque falla antes de iniciar realmente el objetivo, Aegis no ejecuta
un comando de parada para ese runtime. Esto evita errores secundarios como
intentar `docker compose down` cuando Docker ni siquiera está instalado.
