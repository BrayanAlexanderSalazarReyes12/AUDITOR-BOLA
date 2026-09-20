"""Resolución segura de candidatos de Pilar 1 contra el objetivo activo."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from .config import ConfigObjetivo, Endpoint
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
            return [item for item in value if isinstance(item, dict)]
    if any(key in payload for key in _ID_FIELDS):
        return [payload]
    return []


def _scalar_owner(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in (
            "username", "usuario", "user", "email", "name", "nombre"
        ):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _object_identity(item: dict[str, Any]) -> tuple[str, str]:
    object_id = ""
    owner = ""
    for key in _ID_FIELDS:
        value = item.get(key)
        if value not in (None, ""):
            object_id = str(value)
            break
    for key in _OWNER_FIELDS:
        value = item.get(key)
        if value not in (None, ""):
            owner = _scalar_owner(value)
            if owner:
                break
    return object_id, owner


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

            for item in _items(payload):
                object_id, owner = _object_identity(item)
                if object_id and owner and owner in known_users:
                    found_id = object_id
                    found_owner = owner
                    evidence_account = account.username
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
            ],
        )
        resolved.append(endpoint)
        existing.add(key)

    return resolved
