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
