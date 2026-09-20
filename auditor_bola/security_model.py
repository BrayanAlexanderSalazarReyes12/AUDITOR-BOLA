"""Modelo de seguridad, familias y consolidación semántica de Aegis.

Este módulo mantiene separado:
- evidencia observada;
- hipótesis/candidatos;
- casos de prueba;
- hallazgos confirmados.

No contiene nombres, rutas, usuarios ni vulnerabilidades de una aplicación
concreta. Toda clasificación se deriva del perfil o de resultados runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable


VALID_STATES = {
    "candidato",
    "evidencia_insuficiente",
    "por_confirmar",
    "prueba_preparada",
    "confirmado",
    "descartado",
    "no_aplicable",
    "no_ejecutable",
    "ejecutable",
    "ejecutado",
    "vulnerable",
    "seguro",
    "bloqueado",
    "error",
    "correccion_pendiente",
    "corregido",
    "correccion_fallida",
}


@dataclass(frozen=True)
class FamilyDefinition:
    code: str
    pillar: str
    name: str
    evidence_requirements: tuple[str, ...]
    confirmation_strategy: str
    false_positive_guards: tuple[str, ...]
    dedup_dimensions: tuple[str, ...]
    remediation_context: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in (
            "evidence_requirements",
            "false_positive_guards",
            "dedup_dimensions",
            "remediation_context",
        ):
            data[key] = list(data[key])
        return data


class FamilyRegistry:
    """Registro extensible de familias de controles.

    Agregar una familia no obliga a modificar el motor de consolidación:
    cada definición declara evidencia, confirmación, deduplicación y contexto
    necesario para una futura reparación.
    """

    def __init__(self, families: Iterable[FamilyDefinition] | None = None):
        self._families: dict[str, FamilyDefinition] = {}
        for family in families or ():
            self.register(family)

    def register(self, family: FamilyDefinition) -> None:
        self._families[family.code.upper()] = family

    def get(self, code: str) -> FamilyDefinition | None:
        return self._families.get(str(code or "").upper())

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {
            code: family.as_dict()
            for code, family in sorted(self._families.items())
        }


DEFAULT_FAMILIES = FamilyRegistry(
    (
        FamilyDefinition(
            "BOLA",
            "P1",
            "Autorización a nivel de objeto",
            ("endpoint_objeto", "identidad", "recurso", "propiedad"),
            "Comparar el mismo objeto con su propietario y otra identidad; "
            "confirmar solo cuando la política de propiedad esté sustentada.",
            (
                "no inferir propiedad solo por un nombre de ruta",
                "no tratar HTTP 200 aislado como vulnerabilidad",
            ),
            ("familia", "endpoint", "metodo", "recurso", "causa_raiz"),
            ("punto_autorizacion", "campo_propiedad", "rol_privilegiado"),
        ),
        FamilyDefinition(
            "RBAC_ABAC",
            "P1",
            "Separación de privilegios RBAC/ABAC",
            ("identidades", "roles_o_atributos", "operacion", "politica"),
            "Comparar identidades con diferente privilegio sobre la misma "
            "operación y contrastar el resultado con una política inferible.",
            (
                "una palabra como admin solo crea candidato",
                "no asumir acceso esperado sin política o evidencia correlacionada",
            ),
            ("familia", "endpoint", "metodo", "causa_raiz"),
            ("punto_autorizacion", "roles", "atributos", "politica"),
        ),
        FamilyDefinition(
            "AGENT_SCOPE",
            "P1",
            "Propagación de identidad a agentes y herramientas",
            ("identidad", "api_directa", "agente", "herramienta"),
            "Comparar el alcance de la API directa con la misma operación a "
            "través del agente para la misma identidad.",
            (
                "comparar la misma identidad y operación",
                "no inferir escalamiento por diferencia de formato",
            ),
            ("familia", "endpoint", "recurso", "causa_raiz"),
            ("agente", "herramienta", "contexto_identidad", "autorizacion"),
        ),
        FamilyDefinition(
            "LIMIT_BYPASS",
            "P2",
            "Bypass de límites u opciones excepcionales",
            ("parametro_o_rama", "limite", "identidad", "autorizacion"),
            "Comparar operación normal, opción especial con bajo privilegio y "
            "opción especial con identidad autorizada.",
            (
                "una coincidencia textual solo crea candidato",
                "exigir relación con un límite o validación",
            ),
            ("familia", "endpoint", "metodo", "parametro", "causa_raiz"),
            ("parametro", "guardia_autorizacion", "limite_afectado"),
        ),
        FamilyDefinition(
            "CORS",
            "P2",
            "Política CORS",
            ("configuracion_o_headers", "origin_de_prueba"),
            "Enviar Origin no autorizado y validar combinación de ACAO y "
            "credenciales; consolidar configuración global equivalente.",
            ("no confirmar solo por presencia de la palabra CORS",),
            ("familia", "componente", "causa_raiz"),
            ("middleware_cors", "allowlist", "credenciales"),
        ),
        FamilyDefinition(
            "SECRET",
            "P2",
            "Gestión insegura de secretos",
            ("valor", "fuente", "contexto_uso"),
            "Distinguir placeholder/test de secreto realmente utilizado o "
            "fallback desplegable.",
            ("no marcar cualquier cadena parecida a token",),
            ("familia", "componente", "archivo", "causa_raiz"),
            ("origen_secreto", "mecanismo_configuracion"),
        ),
        FamilyDefinition(
            "CONTAINER",
            "P2",
            "Privilegios de contenedor",
            ("dockerfile_o_manifiesto", "usuario_efectivo"),
            "Resolver usuario efectivo y privilegios de ejecución.",
            ("no asumir root solo porque falte USER sin considerar imagen/contexto",),
            ("familia", "componente", "archivo", "causa_raiz"),
            ("imagen", "usuario", "capabilities", "mounts"),
        ),
        FamilyDefinition(
            "DEBUG",
            "P2",
            "Modo debug",
            ("configuracion", "valor_efectivo"),
            "Confirmar que el modo de depuración es efectivo en el contexto "
            "analizado.",
            ("distinguir ejemplo/test de configuración desplegable",),
            ("familia", "componente", "archivo", "causa_raiz"),
            ("configuracion_debug", "entorno"),
        ),
        FamilyDefinition(
            "SESSION",
            "P2",
            "Cookies y sesión",
            ("configuracion_sesion",),
            "Evaluar Secure, HttpOnly, SameSite, transporte, duración y secretos.",
            ("no confundir ejemplo documental con configuración efectiva",),
            ("familia", "componente", "archivo", "causa_raiz"),
            ("configuracion_cookie", "sesion", "transporte"),
        ),
    )
)


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def normalize_route(route: str) -> str:
    value = str(route or "").strip()
    value = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", "{id}", value)
    value = re.sub(r"\{[^{}]+\}", "{id}", value)
    value = re.sub(
        r":(?:id|[A-Za-z_][A-Za-z0-9_]*_id)(?=/|$)",
        "{id}",
        value,
        flags=re.I,
    )
    value = re.sub(r"/[0-9]{1,18}(?=/|$)", "/{id}", value)
    value = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f-]{27,}(?=/|$)",
        "/{id}",
        value,
        flags=re.I,
    )
    return value or "/"


def infer_resource(route: str) -> str | None:
    parts = [
        part for part in normalize_route(route).split("/")
        if part and part != "{id}" and not part.startswith("{")
    ]
    if not parts:
        return None
    ignored = {"api", "v1", "v2", "v3", "rest", "internal"}
    filtered = [part for part in parts if _norm(part) not in ignored]
    return (filtered or parts)[-1]


def _family_from_control(raw: dict[str, Any]) -> str:
    explicit = str(raw.get("familia") or "").upper().strip()
    if explicit:
        aliases = {
            "RBAC": "RBAC_ABAC",
            "ABAC": "RBAC_ABAC",
            "SCOPE": "AGENT_SCOPE",
            "AGENT": "AGENT_SCOPE",
            "BYPASS": "LIMIT_BYPASS",
            "COOKIE": "SESSION",
            "DOCKER": "CONTAINER",
        }
        return aliases.get(explicit, explicit)

    tipo = _norm(raw.get("tipo") or raw.get("tipo_control"))
    control_id = str(
        raw.get("id_control")
        or raw.get("id_control_referencia")
        or ""
    ).upper()

    if tipo in {"bola", "object_access", "object_ownership"} or "BOLA" in control_id:
        return "BOLA"
    if tipo in {"acceso", "rbac", "abac", "rbac_abac"} or any(
        token in control_id for token in ("RBAC", "ACCESS", "ABAC")
    ):
        return "RBAC_ABAC"
    if tipo in {"alcance_agente", "agent_scope", "scope"} or any(
        token in control_id for token in ("SCOPE", "AGENT")
    ):
        return "AGENT_SCOPE"
    if "CORS" in control_id or tipo.startswith("cors"):
        return "CORS"
    if "SECRET" in control_id:
        return "SECRET"
    if "DOCKER" in control_id or tipo == "docker_non_root":
        return "CONTAINER"
    if "DEBUG" in control_id:
        return "DEBUG"
    if "COOKIE" in control_id or "SESSION" in control_id:
        return "SESSION"
    if "BYPASS" in control_id or "LIMIT" in control_id:
        return "LIMIT_BYPASS"
    return "GENERIC"


def _pillar(family: str, raw: dict[str, Any] | None = None) -> str:
    definition = DEFAULT_FAMILIES.get(family)
    if definition:
        return definition.pillar
    raw = raw or {}
    explicit = str(raw.get("pilar") or "").upper()
    if explicit in {"P1", "P2"}:
        return explicit
    return "P2" if str(raw.get("id_control") or "").upper().startswith("P2") else "P1"


def _root_cause(family: str) -> str:
    return {
        "BOLA": "autorizacion_objeto",
        "RBAC_ABAC": "separacion_privilegios",
        "AGENT_SCOPE": "propagacion_identidad",
        "LIMIT_BYPASS": "autorizacion_excepcion_limites",
        "CORS": "politica_cors",
        "SECRET": "gestion_secretos",
        "CONTAINER": "privilegios_contenedor",
        "DEBUG": "configuracion_debug",
        "SESSION": "configuracion_sesion",
    }.get(family, "condicion_seguridad")


def _stable_number(parts: Iterable[Any]) -> int:
    payload = "|".join(_norm(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % 999999 + 1


def stable_finding_id(
    family: str,
    *,
    endpoint: str | None = None,
    method: str | None = None,
    component: str | None = None,
    resource: str | None = None,
    root_cause: str | None = None,
) -> str:
    pillar = _pillar(family)
    number = _stable_number(
        (
            family,
            normalize_route(endpoint or ""),
            method or "",
            component or "",
            resource or "",
            root_cause or _root_cause(family),
        )
    )
    short_family = {
        "RBAC_ABAC": "RBAC",
        "AGENT_SCOPE": "AGENT",
        "LIMIT_BYPASS": "BYPASS",
        "CONTAINER": "CONTAINER",
        "SESSION": "SESSION",
        "GENERIC": "GEN",
    }.get(family, family)
    return f"{pillar}-{short_family}-{number:06d}"


def _sources(raw: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("fuentes_evidencia", "archivos_fuente"):
        current = raw.get(key)
        if isinstance(current, list):
            values.extend(str(item) for item in current if item)
    archivo = raw.get("archivo")
    if archivo:
        values.append(str(archivo))
    return list(dict.fromkeys(values))


def _evidence_summary(raw: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for source in _sources(raw):
        evidence.append(
            {
                "tipo": "fuente_estatica",
                "fuente": source,
            }
        )
    for clue in raw.get("pistas_codigo") or []:
        evidence.append(
            {
                "tipo": "pista",
                "valor": str(clue),
            }
        )
    motive = raw.get("motivo")
    if motive:
        evidence.append({"tipo": "hipotesis_origen", "valor": str(motive)})
    structured = raw.get("evidencia")
    if isinstance(structured, list):
        for item in structured:
            if isinstance(item, dict) and item not in evidence:
                evidence.append(dict(item))
    return evidence


def _test_case(raw: dict[str, Any], family: str, state: str) -> dict[str, Any]:
    route = (
        raw.get("ruta")
        or raw.get("ruta_detectada")
        or raw.get("agent_ruta")
        or raw.get("direct_ruta")
    )
    method = (
        raw.get("metodo")
        or raw.get("direct_metodo")
        or ("POST" if raw.get("agent_ruta") else None)
    )
    return {
        "id_control": raw.get("id_control"),
        "tipo": raw.get("tipo") or raw.get("tipo_control"),
        "familia": family,
        "estado": state,
        "endpoint": route,
        "metodo": str(method).upper() if method else None,
        "cuenta": raw.get("cuenta"),
        "recurso": raw.get("recurso") or infer_resource(str(route or "")),
        "propietario": raw.get("propietario_esperado"),
        "parametro": raw.get("parametro"),
        "fuentes_evidencia": _sources(raw),
    }


def _group_key(item: dict[str, Any]) -> tuple[str, ...]:
    family = item["familia"]
    endpoint = normalize_route(str(item.get("endpoint") or ""))
    method = str(item.get("metodo") or "").upper()
    resource = str(item.get("recurso") or "")
    component = str(item.get("componente") or "")
    root = str(item.get("causa_raiz") or _root_cause(family))

    # Configuraciones globales como CORS deben consolidarse aunque hayan sido
    # probadas contra varias rutas.
    if family == "CORS":
        endpoint = ""
        method = ""
        resource = ""
    return family, endpoint, method, resource, component, root


def _state_rank(state: str) -> int:
    return {
        "evidencia_insuficiente": 0,
        "candidato": 1,
        "no_ejecutable": 1,
        "bloqueado": 1,
        "error": 1,
        "por_confirmar": 2,
        "correccion_pendiente": 2,
        "ejecutable": 3,
        "ejecutado": 3,
        "prueba_preparada": 3,
        "descartado": 4,
        "seguro": 4,
        "corregido": 4,
        "confirmado": 5,
        "vulnerable": 5,
        "correccion_fallida": 5,
    }.get(state, 0)


def _severity_rank(severity: str | None) -> int:
    return {
        "BAJA": 1,
        "MEDIA": 2,
        "ALTA": 3,
        "CRITICA": 4,
        "CRÍTICA": 4,
    }.get(str(severity or "").upper(), 0)


def consolidate_hypotheses(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], dict[str, Any]] = {}

    for item in items:
        key = _group_key(item)
        group = groups.get(key)
        if group is None:
            (
                family,
                semantic_endpoint,
                semantic_method,
                semantic_resource,
                semantic_component,
                semantic_root,
            ) = key
            group = {
                "familia": family,
                "id_hallazgo": stable_finding_id(
                    family,
                    endpoint=semantic_endpoint,
                    method=semantic_method,
                    component=semantic_component,
                    resource=semantic_resource,
                    root_cause=semantic_root,
                ),
                "estado": item.get("estado") or "candidato",
                "confianza": item.get("confianza") or "media",
                "endpoint": item.get("endpoint"),
                "metodo": item.get("metodo"),
                "componente": item.get("componente"),
                "recurso": item.get("recurso"),
                "propietario": item.get("propietario"),
                "hipotesis": item.get("hipotesis"),
                "causa_raiz": item.get("causa_raiz") or _root_cause(family),
                "severidad": item.get("severidad"),
                "recomendacion": item.get("recomendacion"),
                "evidencias": [],
                "casos_prueba": [],
                "relacionado_con": [],
            }
            groups[key] = group

        state = str(item.get("estado") or "candidato")
        if _state_rank(state) > _state_rank(str(group["estado"])):
            group["estado"] = state

        if _severity_rank(item.get("severidad")) > _severity_rank(
            group.get("severidad")
        ):
            group["severidad"] = item.get("severidad")
        if not group.get("recomendacion") and item.get("recomendacion"):
            group["recomendacion"] = item.get("recomendacion")

        for evidence in item.get("evidencia") or []:
            if evidence not in group["evidencias"]:
                group["evidencias"].append(evidence)

        case = item.get("caso_prueba")
        if case and case not in group["casos_prueba"]:
            group["casos_prueba"].append(case)

        control_id = item.get("id_control")
        if control_id and control_id not in group["relacionado_con"]:
            group["relacionado_con"].append(control_id)

    return sorted(
        groups.values(),
        key=lambda item: (item["familia"], item["id_hallazgo"]),
    )


def _explain_control(
    raw: dict[str, Any],
    *,
    state: str,
    role_by_user: dict[str, str],
) -> dict[str, Any]:
    family = _family_from_control(raw)
    route = (
        raw.get("ruta")
        or raw.get("ruta_detectada")
        or raw.get("agent_ruta")
        or raw.get("direct_ruta")
    )
    method = (
        raw.get("metodo")
        or raw.get("direct_metodo")
        or ("POST" if raw.get("agent_ruta") else None)
    )
    resource = raw.get("recurso") or infer_resource(str(route or ""))
    account = raw.get("cuenta")
    evidence = _evidence_summary(raw)
    hypothesis = raw.get("motivo") or raw.get("descripcion") or raw.get("nombre")
    if not hypothesis:
        definition = DEFAULT_FAMILIES.get(family)
        hypothesis = (
            f"Evaluar {definition.name.lower()}"
            if definition
            else "Evaluar la condición de seguridad observada"
        )

    return {
        "familia": family,
        "id_control": raw.get("id_control"),
        "id_control_semantico": stable_finding_id(
            family,
            endpoint=str(route or ""),
            method=str(method or ""),
            resource=str(resource or ""),
            root_cause=_root_cause(family),
        ),
        "autogenerado": bool(raw.get("autogenerado", True)),
        "confianza": raw.get("confianza") or (
            "media" if state == "candidato" else "alta"
        ),
        "fuentes_evidencia": _sources(raw),
        "archivos_fuente": list(raw.get("archivos_fuente") or []),
        "endpoint": route,
        "metodo": str(method).upper() if method else None,
        "cuenta": account,
        "rol": role_by_user.get(str(account or "")),
        "recurso": resource,
        "propietario": raw.get("propietario_esperado"),
        "hipotesis": str(hypothesis),
        "evidencia": evidence,
        "estado": state if state in VALID_STATES else "candidato",
        "causa_raiz": _root_cause(family),
        "relacionado_con": [],
        "casos_prueba": [_test_case(raw, family, state)],
    }


def build_security_model(profile: dict[str, Any]) -> dict[str, Any]:
    accounts = [
        item for item in profile.get("cuentas") or []
        if isinstance(item, dict)
    ]
    endpoints = [
        item for item in profile.get("endpoints_detectados") or []
        if isinstance(item, dict)
    ]
    privileged = {
        str(item).strip()
        for item in profile.get("roles_privilegiados") or []
        if str(item).strip()
    }

    identities: list[dict[str, Any]] = []
    roles: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []

    for account in accounts:
        username = str(account.get("username") or "").strip()
        role = str(account.get("role") or "").strip()
        if not username:
            continue
        identities.append(
            {
                "identidad": username,
                "rol": role or None,
                "tipo_autenticacion": account.get("auth_type") or "none",
                "credencial_disponible": bool(
                    account.get("password")
                    or account.get("token")
                    or account.get("headers")
                ),
            }
        )
        if role:
            role_item = roles.setdefault(
                role,
                {
                    "rol": role,
                    "privilegiado": role in privileged,
                    "identidades": [],
                },
            )
            role_item["identidades"].append(username)
            relations.append(
                {
                    "tipo": "identidad_rol",
                    "origen": username,
                    "destino": role,
                }
            )

    resources: dict[str, dict[str, Any]] = {}
    normalized_endpoints: list[dict[str, Any]] = []
    for endpoint in endpoints:
        route = str(endpoint.get("ruta") or "")
        method = str(endpoint.get("metodo") or "ANY").upper()
        resource = infer_resource(route)
        ep = {
            "metodo": method,
            "ruta": route,
            "ruta_normalizada": normalize_route(route),
            "recurso": resource,
            "archivos_fuente": list(endpoint.get("archivos") or []),
            "tipos_fuente": list(endpoint.get("tipos_fuente") or []),
            "frameworks": list(endpoint.get("frameworks") or []),
        }
        normalized_endpoints.append(ep)
        if resource:
            resources.setdefault(
                resource,
                {"recurso": resource, "endpoints": []},
            )["endpoints"].append(
                {"metodo": method, "ruta": route}
            )
            relations.append(
                {
                    "tipo": "endpoint_recurso",
                    "origen": f"{method} {route}",
                    "destino": resource,
                }
            )

    return {
        "version_modelo": 1,
        "identidades": identities,
        "roles": sorted(roles.values(), key=lambda item: item["rol"].lower()),
        "recursos": sorted(resources.values(), key=lambda item: item["recurso"]),
        "endpoints": normalized_endpoints,
        "relaciones": relations,
        "contrato_conceptual": (
            "Identidad -> Rol/Atributos -> Endpoint -> Accion -> Recurso -> "
            "Propiedad, inferido por evidencia y no por nombres fijos"
        ),
    }


def enrich_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Añade modelo, explicación y deduplicación sin alterar ejecutables."""

    role_by_user = {
        str(item.get("username") or ""): str(item.get("role") or "")
        for item in profile.get("cuentas") or []
        if isinstance(item, dict)
    }

    explained: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []

    for raw in profile.get("chequeos_pilar1") or []:
        if not isinstance(raw, dict):
            continue
        item = _explain_control(
            raw,
            state="prueba_preparada",
            role_by_user=role_by_user,
        )
        explained.append(item)
        hypotheses.append(
            {
                **{key: item.get(key) for key in (
                    "familia", "estado", "confianza", "endpoint", "metodo",
                    "recurso", "propietario", "hipotesis", "causa_raiz",
                    "id_control",
                )},
                "evidencia": item["evidencia"],
                "caso_prueba": item["casos_prueba"][0],
            }
        )

    for raw in profile.get("chequeos_pilar2") or []:
        if not isinstance(raw, dict):
            continue
        item = _explain_control(
            raw,
            state="prueba_preparada",
            role_by_user=role_by_user,
        )
        explained.append(item)
        hypotheses.append(
            {
                **{key: item.get(key) for key in (
                    "familia", "estado", "confianza", "endpoint", "metodo",
                    "recurso", "propietario", "hipotesis", "causa_raiz",
                    "id_control",
                )},
                "componente": raw.get("componente") or raw.get("archivo"),
                "evidencia": item["evidencia"],
                "caso_prueba": item["casos_prueba"][0],
            }
        )

    for raw in profile.get("candidatos_pilar1") or []:
        if not isinstance(raw, dict):
            continue
        missing = list(raw.get("requiere_confirmacion") or [])
        state = "evidencia_insuficiente" if missing else "candidato"
        item = _explain_control(
            raw,
            state=state,
            role_by_user=role_by_user,
        )
        item["campos_pendientes"] = missing
        explained.append(item)
        hypotheses.append(
            {
                **{key: item.get(key) for key in (
                    "familia", "estado", "confianza", "endpoint", "metodo",
                    "recurso", "propietario", "hipotesis", "causa_raiz",
                    "id_control",
                )},
                "evidencia": item["evidencia"],
                "caso_prueba": item["casos_prueba"][0],
            }
        )

    for raw in profile.get("candidatos_pilar2") or []:
        if not isinstance(raw, dict):
            continue
        raw_state = str(raw.get("estado") or "candidato").lower()
        state = (
            raw_state
            if raw_state in VALID_STATES
            else "candidato"
        )
        item = _explain_control(
            raw,
            state=state,
            role_by_user=role_by_user,
        )
        item["componente"] = raw.get("componente")
        item["estrategia_correccion"] = raw.get(
            "estrategia_correccion"
        )
        explained.append(item)
        hypotheses.append(
            {
                **{key: item.get(key) for key in (
                    "familia", "estado", "confianza", "endpoint", "metodo",
                    "recurso", "propietario", "hipotesis", "causa_raiz",
                    "id_control",
                )},
                "componente": raw.get("componente"),
                "evidencia": _evidence_summary(raw),
                "caso_prueba": (
                    (raw.get("casos_prueba") or [None])[0]
                    if isinstance(raw.get("casos_prueba"), list)
                    else None
                ),
            }
        )

    profile["modelo_seguridad"] = build_security_model(profile)
    profile["familias_controles"] = DEFAULT_FAMILIES.as_dict()
    profile["controles_explicados"] = explained
    profile["hallazgos_modelados"] = consolidate_hypotheses(hypotheses)

    metadata = profile.setdefault("metadata_detectada", {})
    engine = dict(metadata.get("motor_evidencia") or {})
    engine.update(
        {
            "version": 4,
            "modo": "evidencia-correlacionada-iterativa",
            "separa_hallazgo_evidencia_caso": True,
            "deduplicacion_semantica": True,
            "ids_hallazgo_dinamicos": True,
            "arquitectura_familias_extensible": True,
            "estados": sorted(VALID_STATES),
            "ciclo": [
                "descubrir",
                "construir_modelo",
                "formular_hipotesis",
                "generar_pruebas",
                "obtener_evidencia",
                "actualizar_modelo",
                "generar_pruebas_adicionales",
                "consolidar",
                "proponer_correccion_contextual",
                "reprobar",
                "regresion",
                "aprender_receta_abstracta",
            ],
        }
    )
    metadata["motor_evidencia"] = engine
    metadata["modelo_seguridad_construido"] = True
    metadata["total_controles_explicados"] = len(explained)
    metadata["total_familias_hallazgo_modeladas"] = len(
        profile["hallazgos_modelados"]
    )
    return profile


def _runtime_item(
    *,
    family: str,
    state: str,
    control_id: str | None,
    endpoint: str | None,
    method: str | None,
    account: str | None,
    role: str | None,
    detail: Any,
    evidence: dict[str, Any],
    resource: str | None = None,
    component: str | None = None,
    confidence: str | None = None,
    severity: str | None = None,
    recommendation: str | None = None,
    root_cause: str | None = None,
) -> dict[str, Any]:
    return {
        "familia": family,
        "estado": state,
        "confianza": (
            confidence
            or ("alta" if state == "confirmado" else "media")
        ),
        "id_control": control_id,
        "endpoint": endpoint,
        "metodo": method,
        "cuenta": account,
        "rol": role,
        "recurso": resource or infer_resource(str(endpoint or "")),
        "componente": component,
        "propietario": None,
        "hipotesis": str(detail or ""),
        "causa_raiz": root_cause or _root_cause(family),
        "severidad": severity,
        "recomendacion": recommendation,
        "evidencia": [{"tipo": "runtime", **evidence}],
        "caso_prueba": {
            "id_control": control_id,
            "familia": family,
            "endpoint": endpoint,
            "metodo": method,
            "cuenta": account,
            "rol": role,
            "estado": state,
        },
    }


def consolidate_runtime_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Deduplica resultados runtime en hallazgos únicos por causa raíz."""

    items: list[dict[str, Any]] = []
    p1 = result.get("pilar1") or {}

    for raw in p1.get("bola") or []:
        if not raw.get("confirmado_bola"):
            continue
        items.append(
            _runtime_item(
                family="BOLA",
                state="confirmado",
                control_id=raw.get("id_control"),
                endpoint=raw.get("endpoint"),
                method=raw.get("metodo"),
                account=raw.get("cuenta"),
                role=raw.get("rol"),
                detail=raw.get("descripcion") or "Acceso a objeto fuera de política",
                evidence={
                    "http_status": raw.get("http_status"),
                    "acceso_esperado": raw.get("acceso_esperado"),
                    "acceso_real": raw.get("acceso_real"),
                },
            )
        )

    for raw in p1.get("acceso") or []:
        if not raw.get("vulnerable"):
            continue
        items.append(
            _runtime_item(
                family="RBAC_ABAC",
                state="confirmado",
                control_id=raw.get("id_control"),
                endpoint=raw.get("endpoint"),
                method=raw.get("metodo"),
                account=raw.get("cuenta"),
                role=raw.get("rol"),
                detail=raw.get("nombre") or "Separación de privilegios incumplida",
                evidence={
                    "http_status": raw.get("http_status"),
                    "acceso_esperado": raw.get("acceso_esperado"),
                    "acceso_real": raw.get("acceso_real"),
                },
            )
        )

    for raw in p1.get("alcance_agente") or []:
        outcome = raw.get("resultado") or {}
        if not outcome.get("vulnerable"):
            continue
        items.append(
            _runtime_item(
                family="AGENT_SCOPE",
                state="confirmado",
                control_id=raw.get("id_control"),
                endpoint=None,
                method=None,
                account=raw.get("cuenta"),
                role=None,
                detail=raw.get("nombre_chequeo") or "El agente amplía el alcance",
                evidence={
                    "cantidad_api_directa": outcome.get("cantidad_api_directa"),
                    "cantidad_agente": outcome.get("cantidad_agente"),
                    "exceso": outcome.get("exceso"),
                },
            )
        )

    for raw in p1.get("matriz_acceso") or []:
        classification = str(raw.get("clasificacion") or "")
        vulnerable = raw.get("vulnerable") is True
        if not vulnerable and classification not in {
            "HALLAZGO_CONFIRMADO",
            "POSIBLE_HALLAZGO",
        }:
            continue
        family = _family_from_control(raw)
        if family == "GENERIC":
            source = str(raw.get("fuente_politica") or "").lower()
            family = "BOLA" if "bola" in source else "RBAC_ABAC"
        items.append(
            _runtime_item(
                family=family,
                # Si el propio motor de matriz determinó vulnerable=True,
                # el resultado forma parte de los hallazgos. La confianza de
                # la política queda registrada por separado como evidencia.
                state=(
                    "confirmado"
                    if vulnerable or classification == "HALLAZGO_CONFIRMADO"
                    else "por_confirmar"
                ),
                control_id=raw.get("id_control_referencia"),
                endpoint=raw.get("endpoint_detectado"),
                method=raw.get("metodo"),
                account=raw.get("cuenta"),
                role=raw.get("rol"),
                detail=raw.get("detalle"),
                confidence=raw.get("confianza"),
                evidence={
                    "vulnerable": vulnerable,
                    "clasificacion": classification,
                    "confianza": raw.get("confianza"),
                    "http_status": raw.get("http_status"),
                    "acceso_esperado": raw.get("acceso_esperado"),
                    "acceso_real": raw.get("acceso_real"),
                    "fuente_politica": raw.get("fuente_politica"),
                    "firma_respuesta": raw.get("response_signature"),
                    "forma_respuesta": raw.get("response_shape"),
                    "objetos": raw.get("object_count"),
                    "ids_objeto": raw.get("object_ids"),
                },
            )
        )

    for raw in result.get("pilar2") or []:
        if str(raw.get("estado") or "").upper() != "HALLAZGO":
            continue
        family = _family_from_control(raw)
        structured_evidence = raw.get("evidencia") or []
        items.append(
            _runtime_item(
                family=family,
                state="confirmado",
                control_id=raw.get("id_control"),
                endpoint=raw.get("ruta"),
                method=raw.get("metodo"),
                account=raw.get("cuenta"),
                role=None,
                detail=raw.get("detalle") or raw.get("nombre"),
                component=raw.get("componente") or raw.get("archivo"),
                confidence=raw.get("confianza"),
                severity=raw.get("severidad"),
                recommendation=raw.get("recomendacion"),
                root_cause=raw.get("causa_raiz"),
                evidence={
                    "tipo_control": raw.get("tipo"),
                    "detalle": raw.get("detalle"),
                    "severidad": raw.get("severidad"),
                    "confianza": raw.get("confianza"),
                    "evidencia_estructurada": structured_evidence,
                    "configuracion_detectada": raw.get(
                        "configuracion_detectada"
                    ),
                    "casos_prueba": raw.get("casos_prueba") or [],
                    "origen": raw.get("origen"),
                },
            )
        )

    return consolidate_hypotheses(items)


def attach_runtime_consolidation(result: dict[str, Any]) -> dict[str, Any]:
    findings = consolidate_runtime_results(result)
    result["hallazgos_consolidados"] = findings
    summary = result.setdefault("resumen", {})
    summary["hallazgos_unicos_confirmados"] = sum(
        item.get("estado") == "confirmado" for item in findings
    )
    summary["hallazgos_unicos_por_confirmar"] = sum(
        item.get("estado") == "por_confirmar" for item in findings
    )
    summary["hallazgos_unicos_total"] = len(findings)
    return result