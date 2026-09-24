# Uso con VulnDesk, VulnCommerce, VulnPort y Tramitia

Los perfiles incluidos en `config/` describen las cuentas ficticias de los
laboratorios y los controles de identidad/acceso y configuración que el motor
puede ejecutar. No representan cobertura de todas las vulnerabilidades del
catálogo LAB (SQLi, XSS, SSRF, etc.). Una corrección sigue requiriendo una receta
aplicable, verificación y rollback si falla.

| Aplicación | Perfil | URL predeterminada | Autenticación |
|---|---|---|---|
| VulnDesk Python | `config/vulndesk-python.json` | `http://127.0.0.1:5000` | Formulario `/api/login` + cookie |
| VulnCommerce Node | `config/vulncommerce-node.json` | `http://127.0.0.1:3000` | JSON `/api/login` + token |
| VulnPort Java | `config/vulnport-java.json` | `http://127.0.0.1:8080/vulnport-java` | Formulario `/login` + cookie |
| Tramitia | `config/tramitia-compatible.json` | `http://127.0.0.1:5050` | HTTP Basic |

En la interfaz, cargue el perfil y la carpeta correspondiente. Python y Node
pueden iniciarse desde el auditor; necesitan sus runtimes y dependencias.
VulnPort es un WAR Servlet, no una aplicación Spring Boot: compile con Maven,
despliegue en Tomcat 9 y configure la URL completa, incluido el contexto del WAR.
El perfil Java usa administración externa del servidor.

El perfil anterior `config/tramitia-app.json` se conserva. Use el perfil nuevo
para obtener cuentas, puerto y controles actualizados. Las relaciones de
propiedad que requieren datos vivos se resuelven al diagnosticar; inicie primero
el objetivo si quiere incorporarlas a un perfil nuevo.

## Generar perfiles para otras copias o puertos

```powershell
python -m auditor_bola.cli autoconfig --target-root ../vulndesk-python --out config/mi-vulndesk.json
python -m auditor_bola.cli autoconfig --target-root ../vulncommerce-node --out config/mi-commerce.json
python -m auditor_bola.cli autoconfig --target-root ../vulnport-java --base-url http://127.0.0.1:8080/vulnport-java --out config/mi-java.json
python -m auditor_bola.cli autoconfig --target-root ../tramitia-app --out config/mi-tramitia.json --resolve-live
```

`--resolve-live` requiere el servidor iniciado. `--force` permite reemplazar
explícitamente el archivo de salida. Sin esa opción, se conserva un perfil ya
existente.

```powershell
python -m auditor_bola.cli diagnose --config config/vulndesk-python.json --target-root ../vulndesk-python --manage-target --out evidencias/vulndesk.json
python -m auditor_bola.cli diagnose --config config/vulnport-java.json --target-root ../vulnport-java --out evidencias/vulnport.json
```

El diagnóstico devuelve código 0 sin hallazgos ni errores, 1 con hallazgos y 2
con errores de ejecución/configuración. Un fallo de login, red o servidor no
equivale a una prueba de autorización superada. Las redirecciones se conservan
como respuestas de la ruta probada, sin seguirlas a una página de login.

## Login configurable

Ejemplo de cuenta con sesión:

```json
{
  "username": "user",
  "password": "user123",
  "role": "USER",
  "auth_type": "session",
  "login": {
    "ruta": "/api/login",
    "formato": "form",
    "campo_usuario": "username",
    "campo_password": "password",
    "codigos_exito": [200]
  }
}
```

Para un token obtenido por login, use `auth_type: "login_bearer"`,
`formato: "json"` y `token_json_path: "token"` (también admite `data.token`).
`login.ruta` se agrega a `base_url`, conservando el contexto Java. Puede declarar
campos adicionales mediante `login.campos`. Cada solicitud usa una sesión
aislada, por lo que no mezcla cuentas ni conserva tokens anteriores al reinicio.
Los esquemas Basic, Bearer estático y cabeceras personalizadas siguen disponibles.
El editor de cuentas conserva tokens, cabeceras y parámetros de login existentes.

La detección automática reconoce los contratos de login presentes en estos
proyectos. Flujos con MFA, CSRF de login o proveedores externos requieren una
integración adicional; no se infieren credenciales ni tokens inexistentes.

## Verificación local

```powershell
python -m pytest -q
python scripts/prepare_java_validation.py
python scripts/validate_local_apps.py
```

La validación utiliza copias bajo `evidencias/integracion`, puertos loopback
temporales y las dependencias Node instaladas en `../vulncommerce-node`.
Necesita Python con las dependencias de los objetivos, Node y un JDK. El script
Java descarga Tomcat 9 y H2 desde Maven Central, verifica los checksums y compila
los servlets de la copia. Los resultados se guardan por aplicación. Puede usar
`--only tramitia-app` (o el nombre de otro proyecto) para una prueba individual.

Esta prueba real ejercita los controles configurados de P1/P2; la matriz
exploratoria de endpoints se valida por separado en la suite automatizada.

Resultado de la validación del 24 de septiembre de 2026: 291 pruebas del auditor
aprobadas. En las copias reales se ejecutaron 8 controles para VulnDesk, 8 para
VulnCommerce, 8 para VulnPort y 17 para Tramitia; los cuatro diagnósticos terminaron
sin errores de ejecución y detectaron acceso indebido a objetos. Los originales
de las aplicaciones no se modificaron.

En este equipo, Java 17 presentó un fallo al inicializar el selector NIO de
Windows. La prueba se ejecutó en Tomcat 9.0.122 con el conector HTTP NIO2; el
script de validación configura ese conector y desactiva el puerto de apagado
para no interferir con otros Tomcat instalados.
