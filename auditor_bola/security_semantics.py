"""Semántica genérica para convertir evidencia de una aplicación en controles.

No contiene nombres de una aplicación concreta. Trabaja con señales comunes
de identidad, propiedad e identificadores y devuelve evidencia con nivel de
confianza para que los motores P1 decidan si pueden activar un control.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


_OWNER_STRONG = {
    "owner",
    "owner_username",
    "owned_by",
    "created_by",
    "creator",
    "creator_username",
    "author",
    "author_username",
    "propietario",
    "propietario_esperado",
    "creado_por",
    "creador",
    "autor",
    "usuario_propietario",
    "user_owner",
}
_OWNER_TOKENS = {
    "owner",
    "owned",
    "creator",
    "created",
    "author",
    "propietario",
    "creador",
    "autor",
}
_ID_STRONG = {
    "id",
    "uuid",
    "pk",
    "key",
    "codigo",
    "code",
    "record_id",
    "object_id",
    "resource_id",
}
_ID_TOKENS = {
    "id",
    "uuid",
    "pk",
    "key",
    "codigo",
    "code",
    "numero",
    "number",
}


def owner_key_score(path: str) -> int:
    key = normalize_key(path)
    leaf = key.split("_")[-1] if key else ""
    if key in _OWNER_STRONG or leaf in _OWNER_STRONG:
        return 100
    tokens = set(key.split("_"))
    if tokens & _OWNER_TOKENS:
        return 80
    # Campos de identidad asociados explícitamente a creación/autoría.
    if (
        {"created", "by"} <= tokens
        or {"created", "user"} <= tokens
        or {"creator", "user"} <= tokens
        or {"author", "user"} <= tokens
    ):
        return 75
    return 0


def id_key_score(path: str, route_parameter: str | None = None) -> int:
    key = normalize_key(path)
    leaf = key.split("_")[-1] if key else ""
    route_key = normalize_key(route_parameter or "")

    if route_key and (key == route_key or leaf == route_key):
        return 130
    if route_key and (
        key.endswith("_" + route_key)
        or route_key.endswith("_" + leaf)
    ):
        return 115
    if key in _ID_STRONG or leaf in _ID_STRONG:
        return 100
    if key.endswith("_id"):
        return 95
    if key.endswith("_uuid"):
        return 92
    if key.endswith("_code") or key.endswith("_codigo"):
        return 85
    tokens = set(key.split("_"))
    if tokens & _ID_TOKENS:
        return 70
    return 0


def _walk_mapping(
    value: Any,
    prefix: str = "",
) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(nested, (dict, list)):
                yield from _walk_mapping(nested, path)
            else:
                yield path, nested
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]"
            if isinstance(nested, (dict, list)):
                yield from _walk_mapping(nested, path)
            else:
                yield path, nested


def infer_object_identity(
    mapping: dict[str, Any],
    known_users: set[str],
    *,
    route_parameter: str | None = None,
) -> dict[str, Any] | None:
    """Infere identificador y propietario desde una estructura arbitraria.

    Para activar evidencia de propiedad exigimos que el valor de identidad
    coincida exactamente con una cuenta conocida y que el nombre del campo
    tenga semántica fuerte de propiedad/autoría. Esto evita asumir que campos
    como assigned_to o reviewer equivalen automáticamente a propietario.
    """
    owner_candidates: list[tuple[int, str, str]] = []
    id_candidates: list[tuple[int, str, str]] = []

    for path, raw in _walk_mapping(mapping):
        if raw is None or isinstance(raw, bool):
            continue

        scalar = str(raw).strip()
        if not scalar:
            continue

        if scalar in known_users:
            score = owner_key_score(path)
            if score:
                owner_candidates.append((score, path, scalar))

        if isinstance(raw, (str, int)):
            score = id_key_score(path, route_parameter)
            if score:
                id_candidates.append((score, path, scalar))

    if not owner_candidates or not id_candidates:
        return None

    owner_candidates.sort(reverse=True)
    id_candidates.sort(reverse=True)

    owner_score, owner_path, owner = owner_candidates[0]

    # Evita usar como id el mismo campo que aportó la identidad.
    usable_ids = [
        item
        for item in id_candidates
        if item[1] != owner_path
        and not item[1].startswith(owner_path + ".")
    ]
    if not usable_ids:
        return None

    id_score, id_path, object_id = usable_ids[0]
    confidence = (
        "alta"
        if owner_score >= 80 and id_score >= 85
        else "media"
    )
    return {
        "id_prueba": object_id,
        "propietario_esperado": owner,
        "campo_id": id_path,
        "campo_propietario": owner_path,
        "confianza": confidence,
        "puntaje_id": id_score,
        "puntaje_propietario": owner_score,
    }


def route_parameter_name(route: str) -> str | None:
    raw = str(route or "")
    patterns = (
        r"<(?:[^:<>]+:)?([^<>]+)>",
        r"\{([^{}]+)\}",
        r":([A-Za-z_][A-Za-z0-9_]*)",
    )
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return normalize_key(match.group(1))
    return None
