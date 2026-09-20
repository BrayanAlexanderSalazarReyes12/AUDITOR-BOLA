"""Resolución segura de candidatos de Pilar 1 contra el objetivo activo."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from .config import ConfigObjetivo, Endpoint
from .security_semantics import (
    infer_object_identity,
    route_parameter_name,
)
from .transport import request_http


_OWNER_FIELDS = (
    "propietario",
    "propietario_esperado",
    "owner",
    "owner_username",
    "owned_by",
    "created_by",
    "creado_por",
    "usuario_propietario",
    "user_owner",
)
_ID_FIELDS = (
    "id",
    "object_id",
    "resource_id",
    "solicitud_id",
    "request_id",
    "ticket_id",
    "item_id",
    "record_id",
)
_LIST_FIELDS = (
    "items",
    "data",
    "results",
    "resultados",
    "solicitudes",
    "records",
    "registros",
)


def _profile_route(route: str) -> tuple[str, str]:
    raw = str(route or "").strip()
    normalized = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", "{id}", raw)
    normalized = re.sub(r"\{[^{}]+\}", "{id}", normalized)
    normalized = re.sub(
        r":(?:id|\w+_id)(?=/|$)",
        "{id}",
        normalized,
        flags=re.I,
    )
    if "{id}" not in normalized:
        return normalized, ""
    collection = normalized.split("/{id}", 1)[0] or "/"
    return normalized, collection


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in _LIST_FIELDS:
        value = payload.get(key)
        if isinstance(value, list):
            items = [
                item for item in value if isinstance(item, dict)
            ]
            if items:
                return items

    # Fallback genérico: muchas APIs envuelven colecciones con nombres
    # específicos del dominio. Elegimos la lista de objetos más grande.
    generic_lists = []
    for value in payload.values():
        if not isinstance(value, list):
            continue
        items = [
            item for item in value if isinstance(item, dict)
        ]
        if items:
            generic_lists.append(items)
    if generic_lists:
        return max(generic_lists, key=len)

    return [payload] if isinstance(payload, dict) else []


def _noop_patch_body(
    item: dict[str, Any],
    *,
    id_field: str,
    owner_field: str,
) -> dict[str, Any] | None:
    """Construye un PATCH de mismo valor para minimizar efectos laterales.

    Solo usa escalares simples y evita identidad, secretos, roles, timestamps
    e identificadores. El control no se ejecuta durante descubrimiento; se
    guarda para la auditoría posterior.
    """
    blocked_tokens = (
        "id", "uuid", "code", "codigo", "owner", "author", "creator",
        "propiet", "user", "usuario", "role", "rol", "permission",
        "password", "passwd", "secret", "token", "key", "created",
        "updated", "timestamp", "fecha", "date", "time",
    )
    preferred_tokens = (
        "summary", "resumen", "title", "titulo", "subject", "asunto",
        "description", "descripcion", "detalle", "status", "estado",
        "name", "nombre",
    )

    candidates: list[tuple[int, str, Any]] = []
    for key, value in item.items():
        if isinstance(value, (dict, list)) or value is None:
            continue
        normalized = str(key).lower()
        if key in {id_field, owner_field}:
            continue
        if any(token in normalized for token in blocked_tokens):
            continue
        score = 10
        if any(token in normalized for token in preferred_tokens):
            score = 100
        candidates.append((score, str(key), value))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    _score, key, value = candidates[0]
    return {key: value}


def resolve_live_bola_candidates(
    cfg: ConfigObjetivo,
    metadata: dict[str, Any],
    *,
    base_url: str | None = None,
    timeout: int = 5,
) -> list[Endpoint]:
    """Convierte candidatos BOLA en controles usando solo evidencia GET."""
    root_url = str(base_url or cfg.base_url or "").rstrip("/")
    if not root_url:
        return []

    known_users = {
        cuenta.username
        for cuenta in cfg.cuentas
        if cuenta.username
    }
    if not known_users:
        return []

    existing = {
        (
            endpoint.metodo.upper(),
            endpoint.ruta,
            str(endpoint.id_prueba),
            endpoint.propietario_esperado,
        )
        for endpoint in cfg.endpoints
    }
    resolved: list[Endpoint] = []
    seen_routes: set[str] = set()

    for candidate in metadata.get("candidatos_pilar1") or []:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("familia") or "").upper() != "BOLA":
            continue
        if str(candidate.get("metodo") or "").upper() != "GET":
            continue

        raw_route = str(candidate.get("ruta_detectada") or "")
        route, collection = _profile_route(raw_route)
        if not collection or route in seen_routes:
            continue
        seen_routes.add(route)

        found_id = ""
        found_owner = ""
        evidence_account = ""
        evidence_id_field = ""
        evidence_owner_field = ""
        found_item: dict[str, Any] | None = None

        for account in cfg.cuentas:
            if not account.username:
                continue
            url = urljoin(root_url + "/", collection.lstrip("/"))
            try:
                response = request_http(
                    "GET",
                    url,
                    cuenta=account,
                    timeout=timeout,
                )
            except Exception:
                continue
            if not 200 <= response.status_code < 300:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue

            parameter_name = route_parameter_name(raw_route)
            for item in _items(payload):
                evidence = infer_object_identity(
                    item,
                    known_users,
                    route_parameter=parameter_name,
                )
                if not evidence:
                    continue
                found_id = str(evidence["id_prueba"])
                found_owner = str(
                    evidence["propietario_esperado"]
                )
                evidence_account = account.username
                evidence_id_field = str(
                    evidence.get("campo_id") or ""
                )
                evidence_owner_field = str(
                    evidence.get("campo_propietario") or ""
                )
                found_item = dict(item)
                break
            if found_id:
                break

        if not found_id or not found_owner:
            continue

        key = ("GET", route, found_id, found_owner)
        if key in existing:
            continue

        endpoint = Endpoint(
            metodo="GET",
            ruta=route,
            id_prueba=found_id,
            propietario_esperado=found_owner,
            id_control=(
                "P1-AUTO-LIVE-BOLA-"
                + str(len(resolved) + 1).zfill(3)
            ),
            descripcion=(
                "BOLA resuelto con evidencia de propiedad devuelta "
                "por la colección autenticada"
            ),
            archivos_fuente=list(
                candidate.get("archivos_fuente") or []
            ),
            pistas_codigo=[
                "candidato BOLA estático",
                f"colección {collection}",
                f"objeto {found_id}",
                f"propietario {found_owner}",
                f"evidencia leída con {evidence_account}",
                f"campo id {evidence_id_field}",
                f"campo propietario {evidence_owner_field}",
            ],
        )
        resolved.append(endpoint)
        existing.add(key)

        # Si existe un candidato PATCH sobre la misma ruta, la evidencia GET
        # ya demuestra qué objeto y propietario usar. Construimos un cuerpo
        # de mismo valor a partir del objeto leído para que el control de
        # escritura sea ejecutable sin inventar datos del dominio.
        patch_body = (
            _noop_patch_body(
                found_item,
                id_field=evidence_id_field,
                owner_field=evidence_owner_field,
            )
            if found_item
            else None
        )
        if patch_body:
            for sibling in metadata.get("candidatos_pilar1") or []:
                if not isinstance(sibling, dict):
                    continue
                if str(sibling.get("familia") or "").upper() != "BOLA":
                    continue
                if str(sibling.get("metodo") or "").upper() != "PATCH":
                    continue
                sibling_route, _collection = _profile_route(
                    str(sibling.get("ruta_detectada") or "")
                )
                if sibling_route != route:
                    continue

                patch_key = (
                    "PATCH",
                    route,
                    found_id,
                    found_owner,
                )
                if patch_key in existing:
                    continue
                resolved.append(
                    Endpoint(
                        metodo="PATCH",
                        ruta=route,
                        id_prueba=found_id,
                        propietario_esperado=found_owner,
                        cuerpo_prueba=patch_body,
                        id_control=(
                            "P1-AUTO-LIVE-BOLA-"
                            + str(len(resolved) + 1).zfill(3)
                        ),
                        descripcion=(
                            "BOLA de escritura derivado de propiedad GET "
                            "con PATCH de mismo valor"
                        ),
                        archivos_fuente=list(
                            sibling.get("archivos_fuente") or []
                        ),
                        pistas_codigo=[
                            "candidato BOLA PATCH",
                            f"objeto {found_id}",
                            f"propietario {found_owner}",
                            "cuerpo PATCH de mismo valor",
                            f"campo actualizado {next(iter(patch_body))}",
                        ],
                    )
                )
                existing.add(patch_key)

    return resolved
