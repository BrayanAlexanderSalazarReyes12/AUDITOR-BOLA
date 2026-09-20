"""Generación asistida de recetas correctivas mediante IA.

La IA propone tres alternativas, pero nunca modifica archivos por sí sola.
La propuesta elegida se convierte al mismo modelo Correccion usado por el
motor determinista y queda sometida a preview, backup, verificación y rollback.
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

from .app_paths import default_ai_config_path
from .config import ConfigObjetivo, Correccion
from .remediation_knowledge import (
    RemediationKnowledge,
    normalizar_familia_control,
)


DEFAULT_PROVIDER_ID = "llmlab"
DEFAULT_MODEL_ID = "lab-coder"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


@dataclass
class AIProviderConfig:
    provider_id: str
    provider_name: str
    model_id: str
    model_name: str
    base_url: str
    api_key: str
    config_path: str
    profile_id: str = ""
    profile_name: str = ""

    def public_dict(self) -> dict:
        """Metadatos seguros; nunca incluye la API key."""
        return {
            "provider_id": self.provider_id,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "base_url": self.base_url,
            "config_path": self.config_path,
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
        }


def _opencode_config_path() -> Path:
    override = os.getenv("OPENCODE_CONFIG")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".config" / "opencode" / "opencode.json").resolve()


_ENV_REF = re.compile(r"^\{env:([A-Za-z_][A-Za-z0-9_]*)\}$")


def _resolver_api_key(valor: str | None) -> str:
    if not valor:
        raise RuntimeError(
            "El proveedor llmlab no tiene apiKey en la configuración de OpenCode."
        )

    match = _ENV_REF.match(valor.strip())
    if match:
        variable = match.group(1)
        key = os.getenv(variable)
        if not key:
            raise RuntimeError(
                f"OpenCode usa la variable {variable}, pero no está definida "
                "en esta sesión."
            )
        return key

    return valor.strip()


def cargar_configuracion_opencode(
    *,
    provider_id: str = DEFAULT_PROVIDER_ID,
) -> AIProviderConfig:
    """Carga llmlab/lab-coder desde ~/.config/opencode/opencode.json."""
    path = _opencode_config_path()
    if not path.exists():
        raise RuntimeError(
            "No se encontró la configuración de OpenCode en "
            f"{path}. Configura OpenCode antes de usar el Asistente IA."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"No fue posible leer la configuración de OpenCode: {path}"
        ) from exc

    providers = data.get("provider") or {}
    provider = providers.get(provider_id)
    if not isinstance(provider, dict):
        raise RuntimeError(
            f"No existe el proveedor '{provider_id}' en {path}."
        )

    options = provider.get("options") or {}
    base_url = str(options.get("baseURL") or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError(
            f"El proveedor '{provider_id}' no declara options.baseURL."
        )

    api_key = _resolver_api_key(options.get("apiKey"))

    configured_model = str(
        os.getenv("AUDITOR_AI_MODEL")
        or data.get("model")
        or f"{provider_id}/{DEFAULT_MODEL_ID}"
    ).strip()

    if "/" in configured_model:
        selected_provider, model_id = configured_model.split("/", 1)
        if selected_provider != provider_id:
            model_id = DEFAULT_MODEL_ID
    else:
        model_id = configured_model

    models = provider.get("models") or {}
    model_data = models.get(model_id) or {}
    model_name = str(model_data.get("name") or model_id)

    return AIProviderConfig(
        provider_id=provider_id,
        provider_name=str(provider.get("name") or provider_id),
        model_id=model_id,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        config_path=str(path),
    )


def _empty_ai_store() -> dict:
    return {
        "schema_version": 2,
        "active_profile_id": None,
        "profiles": [],
    }


def _profile_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug or "perfil-ia"


def _read_ai_store(
    path: str | Path | None = None,
    *,
    persist_migration: bool = True,
) -> tuple[Path, dict]:
    """Lee perfiles IA y migra automáticamente el formato antiguo."""
    config_path = (
        Path(path).expanduser().resolve()
        if path is not None
        else default_ai_config_path().resolve()
    )
    if not config_path.exists():
        return config_path, _empty_ai_store()

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"No fue posible leer la configuración IA de Aegis: {config_path}"
        ) from exc

    if isinstance(data, dict) and isinstance(data.get("profiles"), list):
        store = _empty_ai_store()
        store["active_profile_id"] = data.get("active_profile_id")
        store["profiles"] = [
            dict(item)
            for item in data.get("profiles", [])
            if isinstance(item, dict)
        ]
        valid_ids = [
            str(item.get("id") or "").strip()
            for item in store["profiles"]
            if str(item.get("id") or "").strip()
        ]
        if store["active_profile_id"] not in set(valid_ids):
            store["active_profile_id"] = (
                valid_ids[0] if valid_ids else None
            )
        return config_path, store

    # Compatibilidad con v1.1.9: un único proveedor en ai-provider.json.
    if isinstance(data, dict) and str(data.get("base_url") or "").strip():
        display_name = str(
            data.get("profile_name")
            or data.get("provider_name")
            or data.get("model_name")
            or data.get("model_id")
            or "Proveedor IA"
        ).strip()
        profile_id = _profile_slug(display_name)
        profile = {
            "id": profile_id,
            "name": display_name,
            "provider_id": str(
                data.get("provider_id") or DEFAULT_PROVIDER_ID
            ).strip(),
            "provider_name": str(
                data.get("provider_name") or "Proveedor IA"
            ).strip(),
            "model_id": str(
                data.get("model_id") or DEFAULT_MODEL_ID
            ).strip(),
            "model_name": str(
                data.get("model_name")
                or data.get("model_id")
                or DEFAULT_MODEL_ID
            ).strip(),
            "base_url": str(data.get("base_url") or "").strip().rstrip("/"),
            "api_key": str(data.get("api_key") or "").strip(),
        }
        store = {
            "schema_version": 2,
            "active_profile_id": profile_id,
            "profiles": [profile],
        }
        if persist_migration:
            _write_ai_store(config_path, store)
        return config_path, store

    return config_path, _empty_ai_store()


def _write_ai_store(path: Path, store: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "active_profile_id": store.get("active_profile_id"),
        "profiles": list(store.get("profiles") or []),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _resolve_profile_key(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = _ENV_REF.match(raw)
    if not match:
        return raw
    variable = match.group(1)
    key = str(os.getenv(variable) or "").strip()
    if not key:
        raise RuntimeError(
            f"El perfil IA usa la variable {variable}, "
            "pero no está definida en este equipo."
        )
    return key


def _profile_to_provider(
    profile: dict,
    config_path: Path,
) -> AIProviderConfig:
    base_url = str(profile.get("base_url") or "").strip().rstrip("/")
    model_id = str(profile.get("model_id") or DEFAULT_MODEL_ID).strip()
    if not base_url:
        raise RuntimeError("El perfil IA no declara base_url.")
    if not model_id:
        raise RuntimeError("El perfil IA no declara model_id.")

    return AIProviderConfig(
        provider_id=str(
            profile.get("provider_id") or DEFAULT_PROVIDER_ID
        ).strip(),
        provider_name=str(
            profile.get("provider_name") or "Proveedor IA"
        ).strip(),
        model_id=model_id,
        model_name=str(
            profile.get("model_name") or model_id
        ).strip(),
        base_url=base_url,
        api_key=_resolve_profile_key(profile.get("api_key")),
        config_path=str(config_path),
        profile_id=str(profile.get("id") or "").strip(),
        profile_name=str(
            profile.get("name")
            or profile.get("provider_name")
            or model_id
        ).strip(),
    )


def listar_perfiles_ia(
    path: str | Path | None = None,
) -> list[dict]:
    """Lista perfiles sin exponer las API keys."""
    config_path, store = _read_ai_store(path)
    active = str(store.get("active_profile_id") or "")
    result: list[dict] = []
    for item in store.get("profiles", []):
        profile_id = str(item.get("id") or "").strip()
        if not profile_id:
            continue
        result.append(
            {
                "id": profile_id,
                "name": str(
                    item.get("name")
                    or item.get("provider_name")
                    or item.get("model_id")
                    or profile_id
                ),
                "provider_id": str(
                    item.get("provider_id") or DEFAULT_PROVIDER_ID
                ),
                "provider_name": str(
                    item.get("provider_name") or "Proveedor IA"
                ),
                "model_id": str(
                    item.get("model_id") or DEFAULT_MODEL_ID
                ),
                "model_name": str(
                    item.get("model_name")
                    or item.get("model_id")
                    or DEFAULT_MODEL_ID
                ),
                "base_url": str(item.get("base_url") or ""),
                "has_api_key": bool(str(item.get("api_key") or "").strip()),
                "active": profile_id == active,
                "config_path": str(config_path),
            }
        )
    return result


def cargar_perfil_ia(
    profile_id: str | None = None,
    path: str | Path | None = None,
) -> AIProviderConfig:
    config_path, store = _read_ai_store(path)
    selected = str(
        profile_id or store.get("active_profile_id") or ""
    ).strip()
    if not selected:
        raise RuntimeError(
            "Aegis no tiene un perfil IA configurado localmente."
        )

    for item in store.get("profiles", []):
        if str(item.get("id") or "").strip() == selected:
            return _profile_to_provider(item, config_path)
    raise RuntimeError(f"No existe el perfil IA '{selected}'.")


def cargar_configuracion_aegis_ai(
    path: str | Path | None = None,
) -> AIProviderConfig:
    """Compatibilidad: devuelve el perfil IA activo de Aegis."""
    return cargar_perfil_ia(None, path)


def _unique_profile_id(store: dict, name: str) -> str:
    base = _profile_slug(name)
    existing = {
        str(item.get("id") or "").strip()
        for item in store.get("profiles", [])
    }
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


def guardar_perfil_ia(
    *,
    profile_name: str,
    base_url: str,
    model_id: str = DEFAULT_MODEL_ID,
    api_key: str | None = None,
    provider_id: str = DEFAULT_PROVIDER_ID,
    provider_name: str = "Proveedor IA",
    model_name: str | None = None,
    profile_id: str | None = None,
    set_active: bool = True,
    path: str | Path | None = None,
) -> AIProviderConfig:
    """Crea o edita un perfil IA independiente."""
    clean_name = str(profile_name or "").strip()
    clean_url = str(base_url or "").strip().rstrip("/")
    clean_model = str(model_id or DEFAULT_MODEL_ID).strip()
    if not clean_name:
        raise ValueError("El nombre del perfil IA es obligatorio.")
    if not clean_url:
        raise ValueError("La URL base del proveedor IA es obligatoria.")
    if not clean_model:
        raise ValueError("El modelo IA es obligatorio.")

    config_path, store = _read_ai_store(path)
    profiles = list(store.get("profiles") or [])
    selected_id = str(profile_id or "").strip()
    existing: dict | None = None

    if selected_id:
        for item in profiles:
            if str(item.get("id") or "").strip() == selected_id:
                existing = item
                break
        if existing is None:
            raise RuntimeError(
                f"No existe el perfil IA '{selected_id}' para editarlo."
            )
    else:
        selected_id = _unique_profile_id(store, clean_name)

    previous_key = str((existing or {}).get("api_key") or "").strip()
    clean_key = (
        str(api_key).strip()
        if api_key is not None and str(api_key).strip()
        else previous_key
    )
    payload = {
        "id": selected_id,
        "name": clean_name,
        "provider_id": str(
            provider_id or DEFAULT_PROVIDER_ID
        ).strip(),
        "provider_name": str(
            provider_name or clean_name
        ).strip(),
        "model_id": clean_model,
        "model_name": str(model_name or clean_model).strip(),
        "base_url": clean_url,
        "api_key": clean_key,
    }

    if existing is None:
        profiles.append(payload)
    else:
        existing.clear()
        existing.update(payload)

    store["profiles"] = profiles
    if set_active or not store.get("active_profile_id"):
        store["active_profile_id"] = selected_id
    _write_ai_store(config_path, store)
    return cargar_perfil_ia(selected_id, config_path)


def guardar_configuracion_aegis_ai(
    *,
    base_url: str,
    model_id: str = DEFAULT_MODEL_ID,
    api_key: str | None = None,
    provider_id: str = DEFAULT_PROVIDER_ID,
    provider_name: str = "Laboratorio UTB",
    model_name: str | None = None,
) -> AIProviderConfig:
    """Compatibilidad: crea/edita el perfil activo."""
    config_path, store = _read_ai_store()
    active = str(store.get("active_profile_id") or "").strip()
    if active:
        current = cargar_perfil_ia(active, config_path)
        profile_name = current.profile_name or current.provider_name
        return guardar_perfil_ia(
            profile_id=active,
            profile_name=profile_name,
            base_url=base_url,
            model_id=model_id,
            api_key=api_key,
            provider_id=provider_id,
            provider_name=provider_name,
            model_name=model_name,
            set_active=True,
            path=config_path,
        )

    return guardar_perfil_ia(
        profile_name=provider_name or model_name or model_id,
        base_url=base_url,
        model_id=model_id,
        api_key=api_key,
        provider_id=provider_id,
        provider_name=provider_name,
        model_name=model_name,
        set_active=True,
        path=config_path,
    )


def seleccionar_perfil_ia(
    profile_id: str,
    path: str | Path | None = None,
) -> AIProviderConfig:
    config_path, store = _read_ai_store(path)
    selected = str(profile_id or "").strip()
    ids = {
        str(item.get("id") or "").strip()
        for item in store.get("profiles", [])
    }
    if selected not in ids:
        raise RuntimeError(f"No existe el perfil IA '{selected}'.")
    store["active_profile_id"] = selected
    _write_ai_store(config_path, store)
    return cargar_perfil_ia(selected, config_path)


def duplicar_perfil_ia(
    profile_id: str,
    *,
    new_name: str | None = None,
    path: str | Path | None = None,
) -> AIProviderConfig:
    config_path, store = _read_ai_store(path)
    source: dict | None = None
    for item in store.get("profiles", []):
        if str(item.get("id") or "").strip() == str(profile_id).strip():
            source = dict(item)
            break
    if source is None:
        raise RuntimeError(f"No existe el perfil IA '{profile_id}'.")

    name = str(
        new_name
        or f"{source.get('name') or source.get('provider_name') or 'Perfil IA'} copia"
    ).strip()
    return guardar_perfil_ia(
        profile_name=name,
        base_url=str(source.get("base_url") or ""),
        model_id=str(source.get("model_id") or DEFAULT_MODEL_ID),
        api_key=str(source.get("api_key") or ""),
        provider_id=str(source.get("provider_id") or DEFAULT_PROVIDER_ID),
        provider_name=str(source.get("provider_name") or "Proveedor IA"),
        model_name=str(
            source.get("model_name")
            or source.get("model_id")
            or DEFAULT_MODEL_ID
        ),
        set_active=True,
        path=config_path,
    )


def eliminar_perfil_ia(
    profile_id: str,
    path: str | Path | None = None,
) -> str | None:
    config_path, store = _read_ai_store(path)
    selected = str(profile_id or "").strip()
    profiles = [
        item
        for item in store.get("profiles", [])
        if str(item.get("id") or "").strip() != selected
    ]
    if len(profiles) == len(store.get("profiles", [])):
        raise RuntimeError(f"No existe el perfil IA '{selected}'.")

    store["profiles"] = profiles
    active = str(store.get("active_profile_id") or "")
    if active == selected:
        store["active_profile_id"] = (
            str(profiles[0].get("id") or "").strip()
            if profiles
            else None
        )
    _write_ai_store(config_path, store)
    return store.get("active_profile_id")


def importar_configuracion_opencode_a_aegis() -> AIProviderConfig:
    """Importa OpenCode como un perfil adicional y lo activa."""
    provider = cargar_configuracion_opencode()
    display = f"OpenCode · {provider.model_name or provider.model_id}"
    return guardar_perfil_ia(
        profile_name=display,
        base_url=provider.base_url,
        model_id=provider.model_id,
        api_key=provider.api_key,
        provider_id=provider.provider_id,
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        set_active=True,
    )


def cargar_configuracion_ia() -> AIProviderConfig:
    """Resuelve el proveedor IA efectivo.

    Prioridad:
    1. Perfil activo seleccionado dentro de Aegis.
    2. Variables AEGIS_AI_* cuando no hay perfiles locales.
    3. OpenCode como compatibilidad final.
    """
    local_error: Exception | None = None
    try:
        return cargar_configuracion_aegis_ai()
    except Exception as exc:
        local_error = exc

    env_url = str(os.getenv("AEGIS_AI_BASE_URL") or "").strip().rstrip("/")
    if env_url:
        model_id = str(
            os.getenv("AEGIS_AI_MODEL") or DEFAULT_MODEL_ID
        ).strip()
        return AIProviderConfig(
            provider_id=str(
                os.getenv("AEGIS_AI_PROVIDER_ID") or DEFAULT_PROVIDER_ID
            ).strip(),
            provider_name=str(
                os.getenv("AEGIS_AI_PROVIDER_NAME") or "Proveedor IA"
            ).strip(),
            model_id=model_id,
            model_name=str(
                os.getenv("AEGIS_AI_MODEL_NAME") or model_id
            ).strip(),
            base_url=env_url,
            api_key=str(os.getenv("AEGIS_AI_API_KEY") or "").strip(),
            config_path="variables de entorno AEGIS_AI_*",
            profile_id="env",
            profile_name="Variables de entorno",
        )

    try:
        return cargar_configuracion_opencode()
    except Exception as opencode_error:
        raise RuntimeError(
            "La IA no está configurada en este equipo. Abre "
            "Configuración > Inteligencia artificial en Aegis y crea "
            "uno o más perfiles con URL, modelo y API key. También puedes "
            "usar AEGIS_AI_BASE_URL/AEGIS_AI_API_KEY/AEGIS_AI_MODEL. "
            f"Detalle local: {local_error}. OpenCode: {opencode_error}"
        ) from opencode_error


@dataclass
class AIRecipeProposal:
    id: str
    titulo: str
    enfoque: str
    explicacion: str
    riesgo: str
    estrategia: str
    buscar: str
    reemplazar: str
    requiere_reinicio: bool
    consideraciones: str
    validacion_ok: bool = True
    errores_validacion: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


_SENSITIVE_NAME = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b"
)
_BEARER = re.compile(
    r'(?i)(Authorization\s*[:=,\(]\s*["\']?Bearer\s+)([^\s"\']+)'
)
_API_KEY_VALUE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
    r"-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_QUOTED_ASSIGNMENT = re.compile(
    r'([:=]\s*)(["\'])(.*?)(\2)'
)
_UNQUOTED_ASSIGNMENT = re.compile(
    r"([:=]\s*)([^;,\s]+)"
)


def _redactar_linea_sensible(linea: str) -> str:
    if not _SENSITIVE_NAME.search(linea):
        return linea

    if _QUOTED_ASSIGNMENT.search(linea):
        return _QUOTED_ASSIGNMENT.sub(
            lambda m: f"{m.group(1)}{m.group(2)}<REDACTED>{m.group(4)}",
            linea,
            count=1,
        )

    return _UNQUOTED_ASSIGNMENT.sub(
        lambda m: f"{m.group(1)}<REDACTED>",
        linea,
        count=1,
    )


def redactar_secretos(texto: str) -> str:
    """Reduce el riesgo de enviar credenciales accidentales al proveedor IA."""
    resultado = _PRIVATE_KEY.sub("<REDACTED_PRIVATE_KEY>", texto)
    resultado = _BEARER.sub(
        lambda m: f"{m.group(1)}<REDACTED>",
        resultado,
    )
    resultado = _API_KEY_VALUE.sub("<REDACTED_API_KEY>", resultado)

    lineas = resultado.splitlines(keepends=True)
    return "".join(_redactar_linea_sensible(linea) for linea in lineas)


def _redactar_estructura(valor):
    if isinstance(valor, dict):
        resultado = {}
        for clave, contenido in valor.items():
            if _SENSITIVE_NAME.search(str(clave)):
                resultado[clave] = "<REDACTED>"
            else:
                resultado[clave] = _redactar_estructura(contenido)
        return resultado
    if isinstance(valor, list):
        return [_redactar_estructura(item) for item in valor]
    if isinstance(valor, tuple):
        return [_redactar_estructura(item) for item in valor]
    if isinstance(valor, str):
        return redactar_secretos(valor)
    return valor


def _pistas_utiles(*textos: str) -> list[str]:
    palabras: list[str] = []
    for texto in textos:
        for token in re.findall(r"[A-Za-z0-9_./-]{4,}", texto or ""):
            limpio = token.strip("./-").lower()
            if len(limpio) >= 4 and limpio not in palabras:
                palabras.append(limpio)
    return palabras[:30]


def recortar_codigo(
    codigo: str,
    pistas: Iterable[str],
    *,
    max_chars: int = 30000,
) -> str:
    """Conserva zonas cercanas a pistas del hallazgo en archivos grandes."""
    if len(codigo) <= max_chars:
        return codigo

    lines = codigo.splitlines()
    pistas_l = [p.lower() for p in pistas if len(p) >= 4]
    indices: list[int] = []

    for i, line in enumerate(lines):
        lower = line.lower()
        if any(p in lower for p in pistas_l):
            indices.append(i)

    if not indices:
        mitad = max_chars // 2
        return codigo[:mitad] + "\n\n/* ... RECORTADO ... */\n\n" + codigo[-mitad:]

    seleccion: set[int] = set()
    for idx in indices[:12]:
        inicio = max(0, idx - 45)
        fin = min(len(lines), idx + 46)
        seleccion.update(range(inicio, fin))

    piezas: list[str] = []
    ultimo = None
    total = 0
    for idx in sorted(seleccion):
        if ultimo is not None and idx > ultimo + 1:
            pieza = "\n/* ... RECORTADO ... */\n"
            if total + len(pieza) > max_chars:
                break
            piezas.append(pieza)
            total += len(pieza)

        line = lines[idx] + "\n"
        if total + len(line) > max_chars:
            break
        piezas.append(line)
        total += len(line)
        ultimo = idx

    return "".join(piezas)


def _json_schema() -> dict:
    propuesta = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "titulo": {"type": "string"},
            "enfoque": {
                "type": "string",
                "enum": ["MINIMA", "ESTRUCTURAL", "ALTERNATIVA"],
            },
            "explicacion": {"type": "string"},
            "riesgo": {
                "type": "string",
                "enum": ["BAJO", "MEDIO", "ALTO"],
            },
            "estrategia": {
                "type": "string",
                "enum": ["replace_exact", "regex_replace"],
            },
            "buscar": {"type": "string"},
            "reemplazar": {"type": "string"},
            "requiere_reinicio": {"type": "boolean"},
            "consideraciones": {"type": "string"},
        },
        "required": [
            "id",
            "titulo",
            "enfoque",
            "explicacion",
            "riesgo",
            "estrategia",
            "buscar",
            "reemplazar",
            "requiere_reinicio",
            "consideraciones",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "propuestas": {
                "type": "array",
                "items": propuesta,
            }
        },
        "required": ["propuestas"],
        "additionalProperties": False,
    }


def _extraer_contenido_chat(response_json: dict) -> str:
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(
            "El Laboratorio UTB no devolvió choices en chat/completions."
        )

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        textos: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if text:
                    textos.append(str(text))
        if textos:
            return "".join(textos).strip()

    raise RuntimeError(
        "La respuesta de Gemma no contiene texto utilizable."
    )


def _extraer_json(texto: str) -> dict:
    limpio = texto.strip()

    if limpio.startswith("```"):
        limpio = re.sub(r"^```(?:json)?\s*", "", limpio, flags=re.I)
        limpio = re.sub(r"\s*```$", "", limpio)

    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass

    inicio = limpio.find("{")
    fin = limpio.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            return json.loads(limpio[inicio : fin + 1])
        except json.JSONDecodeError:
            pass

    raise RuntimeError(
        "Gemma no devolvió un JSON válido con las tres recetas."
    )


def _validar_propuestas(data: dict) -> list[AIRecipeProposal]:
    items = data.get("propuestas")
    if not isinstance(items, list) or len(items) != 3:
        raise RuntimeError(
            "La IA debe devolver exactamente tres propuestas de receta."
        )

    propuestas = [AIRecipeProposal(**item) for item in items]
    enfoques = {item.enfoque for item in propuestas}
    if enfoques != {"MINIMA", "ESTRUCTURAL", "ALTERNATIVA"}:
        raise RuntimeError(
            "Las tres propuestas deben usar los enfoques "
            "MINIMA, ESTRUCTURAL y ALTERNATIVA."
        )
    return propuestas



_IDENTITY_KEY_RE = re.compile(
    r"(?i)^(cuenta|usuario|username|user|email|identity|identidad|subject|sujeto)$"
)


def _identidades_de_prueba(
    metadata_hallazgo: dict | None,
    matriz_pruebas: list[dict] | None,
) -> set[str]:
    """Extrae identidades usadas como datos de prueba, no como política."""
    values: set[str] = set()

    def walk(value, key: str | None = None) -> None:
        if isinstance(value, dict):
            for item_key, item_value in value.items():
                if _IDENTITY_KEY_RE.match(str(item_key)):
                    if isinstance(item_value, (str, int)):
                        text = str(item_value).strip()
                        if len(text) >= 3 and text not in {"-", "none", "null"}:
                            values.add(text)
                walk(item_value, str(item_key))
        elif isinstance(value, list):
            for item in value:
                walk(item, key)

    walk(metadata_hallazgo or {})
    walk(matriz_pruebas or [])
    return values


def _aplicar_propuesta_en_memoria(
    propuesta: AIRecipeProposal,
    source_text: str,
) -> str:
    if propuesta.estrategia == "replace_exact":
        if propuesta.buscar not in source_text:
            raise RuntimeError(
                "el bloque buscar no aparece literalmente en el archivo"
            )
        patched = source_text.replace(
            propuesta.buscar,
            propuesta.reemplazar,
            1,
        )
    elif propuesta.estrategia == "regex_replace":
        try:
            pattern = re.compile(
                propuesta.buscar,
                re.MULTILINE | re.DOTALL,
            )
        except re.error as exc:
            raise RuntimeError(
                f"regex inválida: {exc}"
            ) from exc
        patched, count = pattern.subn(
            propuesta.reemplazar,
            source_text,
            count=1,
        )
        if count == 0:
            raise RuntimeError(
                "la regex buscar no coincide con el archivo"
            )
    else:
        raise RuntimeError(
            f"estrategia no soportada: {propuesta.estrategia}"
        )

    if patched == source_text:
        raise RuntimeError("la receta no produciría ningún cambio")
    return patched


def _validar_sintaxis_basica(
    source_relative: str,
    patched_text: str,
) -> list[str]:
    """Valida sintaxis cuando existe un parser estándar confiable."""
    suffix = Path(source_relative).suffix.lower()
    errors: list[str] = []

    if suffix == ".py":
        try:
            ast.parse(patched_text)
        except SyntaxError as exc:
            errors.append(
                "el parche dejaría Python inválido: "
                f"{exc.msg} (línea {exc.lineno})"
            )
    elif suffix == ".json":
        try:
            json.loads(patched_text)
        except json.JSONDecodeError as exc:
            errors.append(
                "el parche dejaría JSON inválido: "
                f"{exc.msg} (línea {exc.lineno})"
            )

    return errors


def validar_propuestas_contextuales(
    propuestas: list[AIRecipeProposal],
    *,
    source_relative: str,
    source_text: str,
    metadata_hallazgo: dict | None = None,
    matriz_pruebas: list[dict] | None = None,
) -> list[AIRecipeProposal]:
    """Marca recetas inseguras o no aplicables antes de mostrarlas.

    Una identidad concreta observada en una fila de prueba no puede convertirse
    en una regla hardcodeada de autorización. También se valida que el parche
    realmente coincida con el archivo y, para formatos con parser estándar,
    que conserve sintaxis válida.
    """
    test_identities = _identidades_de_prueba(
        metadata_hallazgo,
        matriz_pruebas,
    )

    for proposal in propuestas:
        errors: list[str] = []
        try:
            patched = _aplicar_propuesta_en_memoria(
                proposal,
                source_text,
            )
        except Exception as exc:
            proposal.validacion_ok = False
            proposal.errores_validacion = [str(exc)]
            continue

        for identity in sorted(test_identities):
            if (
                identity
                and identity not in source_text
                and identity in proposal.reemplazar
            ):
                errors.append(
                    "la receta hardcodea una identidad usada por la prueba "
                    f"({identity!r}) en vez de corregir la política general"
                )

        errors.extend(
            _validar_sintaxis_basica(
                source_relative,
                patched,
            )
        )

        proposal.validacion_ok = not errors
        proposal.errores_validacion = errors

    return propuestas


def _construir_contexto(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    descripcion: str,
    detalle: str,
    source_relative: str,
    source_text: str,
    metadata_hallazgo: dict | None = None,
    matriz_pruebas: list[dict] | None = None,
    intento_anterior: dict | None = None,
    conocimiento_reutilizable: dict | None = None,
) -> dict:
    pistas = _pistas_utiles(control_id, descripcion, detalle, source_relative)
    limpio = redactar_secretos(source_text)
    recortado = recortar_codigo(limpio, pistas)

    return {
        "sistema": cfg.sistema,
        "version_objetivo": cfg.version_objetivo,
        "control_id": control_id,
        "descripcion_hallazgo": descripcion,
        "detalle_observado": detalle,
        "hallazgo_objetivo": _redactar_estructura(metadata_hallazgo or {}),
        "matriz_de_pruebas_del_mismo_control": _redactar_estructura(
            matriz_pruebas or []
        ),
        "intento_anterior_fallido": _redactar_estructura(intento_anterior),
        "conocimiento_correctivo_reutilizable": _redactar_estructura(
            conocimiento_reutilizable
        ),
        "archivo_seleccionado": source_relative,
        "codigo_relevante_redactado": recortado,
        "criterio_de_exito": (
            "La fila objetivo debe pasar a SIN_HALLAZGO y ninguna fila del "
            "mismo control que estaba en SIN_HALLAZGO puede convertirse en "
            "HALLAZGO o ERROR."
        ),
        "restricciones": {
            "solo_archivo_seleccionado": True,
            "no_incluir_credenciales": True,
            "tres_propuestas_diferentes": True,
            "verificacion_posterior_obligatoria": True,
            "no_romper_pruebas_que_ya_pasaban": True,
            "no_hardcodear_identidades_de_prueba": True,
            "parche_debe_ser_aplicable_al_archivo_actual": True,
            "conservar_sintaxis_valida": True,
        },
    }


def generar_tres_recetas(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    descripcion: str,
    detalle: str,
    source_relative: str,
    source_text: str,
    provider: AIProviderConfig | None = None,
    metadata_hallazgo: dict | None = None,
    matriz_pruebas: list[dict] | None = None,
    intento_anterior: dict | None = None,
    conocimiento_reutilizable: dict | None = None,
    timeout: int = 120,
) -> tuple[list[AIRecipeProposal], dict, AIProviderConfig]:
    """Solicita tres recetas a llmlab/lab-coder vía chat/completions."""
    provider = provider or cargar_configuracion_ia()

    contexto = _construir_contexto(
        cfg,
        control_id=control_id,
        descripcion=descripcion,
        detalle=detalle,
        source_relative=source_relative,
        source_text=source_text,
        metadata_hallazgo=metadata_hallazgo,
        matriz_pruebas=matriz_pruebas,
        intento_anterior=intento_anterior,
        conocimiento_reutilizable=conocimiento_reutilizable,
    )

    system_prompt = (
        "Eres un asistente defensivo de remediación de código para un "
        "auditor de seguridad. Debes proponer exactamente tres recetas "
        "diferentes para el mismo hallazgo: "
        "MINIMA (cambio pequeño y localizado), "
        "ESTRUCTURAL (mejora de diseño o centralización) y "
        "ALTERNATIVA (otro enfoque válido). "
        "Todas deben modificar únicamente el archivo seleccionado. "
        "No inventes archivos. No incluyas secretos ni credenciales. "
        "Cuando uses replace_exact, el campo buscar debe ser texto literal "
        "que aparezca en el código recibido. Cuando uses regex_replace, "
        "buscar debe ser una expresión regular acotada. "
        "La IA solo propone; un humano seleccionará una opción y un motor "
        "determinista hará preview, backup, aplicación y verificación. "
        "El objetivo NO es solo producir un cambio sintáctico: la receta debe "
        "hacer que la prueba objetivo pase de HALLAZGO a SIN_HALLAZGO. Usa "
        "hallazgo_objetivo como contrato exacto (cuenta, método, ruta y "
        "resultado esperado/observado). Usa matriz_de_pruebas_del_mismo_control "
        "como conjunto de regresión: cualquier fila que ya estaba en "
        "SIN_HALLAZGO debe seguir segura después del cambio. Si existe "
        "intento_anterior_fallido, analiza por qué no resolvió el comportamiento "
        "y NO repitas la misma solución ni una variante superficial. "
        "Si existe conocimiento_correctivo_reutilizable, trátalo como una "
        "medicina semántica previamente verificada: conserva su invariante, "
        "estrategia y contrato de verificación, pero ADÁPTALA al código actual. "
        "No copies nombres de archivos, clases, variables ni fragmentos del "
        "sistema donde se aprendió. "
        "MUY IMPORTANTE: los nombres de cuenta/usuario presentes en "
        "hallazgo_objetivo o matriz_de_pruebas_del_mismo_control son datos de "
        "prueba, NO una política. Nunca hardcodees una identidad concreta para "
        "permitir o denegar acceso. Corrige la regla general usando identidad "
        "autenticada, propiedad del recurso, rol, permiso o política existente. "
        "La receta debe ser general para usuarios equivalentes. "
        "Prioriza la validación de autorización/propiedad en el punto donde se "
        "decide el acceso al recurso. Responde únicamente con JSON válido, "
        "sin Markdown."
    )

    formato = {
        "propuestas": [
            {
                "id": "IA-1",
                "titulo": "texto",
                "enfoque": "MINIMA",
                "explicacion": "texto",
                "riesgo": "BAJO",
                "estrategia": "replace_exact",
                "buscar": "texto exacto o regex",
                "reemplazar": "texto de reemplazo",
                "requiere_reinicio": True,
                "consideraciones": "texto",
            },
            {
                "id": "IA-2",
                "titulo": "texto",
                "enfoque": "ESTRUCTURAL",
                "explicacion": "texto",
                "riesgo": "MEDIO",
                "estrategia": "replace_exact",
                "buscar": "texto exacto o regex",
                "reemplazar": "texto de reemplazo",
                "requiere_reinicio": True,
                "consideraciones": "texto",
            },
            {
                "id": "IA-3",
                "titulo": "texto",
                "enfoque": "ALTERNATIVA",
                "explicacion": "texto",
                "riesgo": "MEDIO",
                "estrategia": "regex_replace",
                "buscar": "texto exacto o regex",
                "reemplazar": "texto de reemplazo",
                "requiere_reinicio": True,
                "consideraciones": "texto",
            },
        ]
    }

    user_prompt = (
        "Analiza el siguiente hallazgo y genera exactamente tres recetas que "
        "tengan posibilidad real de hacer pasar la prueba de seguridad. "
        "No repitas una receta fallida incluida en el contexto.\n\n"
        "FORMATO JSON OBLIGATORIO:\n"
        + json.dumps(formato, ensure_ascii=False, indent=2)
        + "\n\nCONTEXTO:\n"
        + json.dumps(contexto, ensure_ascii=False, indent=2)
    )

    endpoint = provider.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": provider.model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
    }

    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    resp = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        detalle_error = resp.text[:1200]
        raise RuntimeError(
            "Laboratorio UTB respondió HTTP "
            f"{resp.status_code}: {detalle_error}"
        )

    response_json = resp.json()
    texto = _extraer_contenido_chat(response_json)
    data = _extraer_json(texto)
    propuestas = _validar_propuestas(data)
    propuestas = validar_propuestas_contextuales(
        propuestas,
        source_relative=source_relative,
        source_text=source_text,
        metadata_hallazgo=metadata_hallazgo,
        matriz_pruebas=matriz_pruebas,
    )
    contexto["validacion_local_propuestas"] = [
        {
            "id": item.id,
            "valida": item.validacion_ok,
            "errores": list(item.errores_validacion),
        }
        for item in propuestas
    ]
    return propuestas, contexto, provider


def propuesta_a_correccion(
    propuesta: AIRecipeProposal,
    *,
    control_id: str,
    source_relative: str,
) -> Correccion:
    if propuesta.estrategia == "replace_exact":
        op = {
            "estrategia": "replace_exact",
            "buscar": propuesta.buscar,
            "reemplazar": propuesta.reemplazar,
            "max_reemplazos": 1,
        }
    else:
        op = {
            "estrategia": "regex_replace",
            "patron": propuesta.buscar,
            "sustitucion": propuesta.reemplazar,
            "max_reemplazos": 1,
        }

    return Correccion(
        control_id=control_id,
        archivo=source_relative,
        descripcion=(
            f"Receta IA {propuesta.id}: {propuesta.titulo}. "
            f"{propuesta.explicacion}"
        ),
        requiere_reinicio=propuesta.requiere_reinicio,
        operaciones=[op],
    )


def inferir_archivo_control(
    cfg: ConfigObjetivo,
    control_id: str,
) -> str | None:
    receta = cfg.correccion_por_control(control_id)
    if receta:
        return receta.archivo

    for check in cfg.chequeos_pilar2:
        if check.id_control == control_id and check.archivo:
            return check.archivo
    return None


def guardar_sesion_ia(
    evidence_base: str | Path,
    *,
    contexto: dict,
    propuestas: list[AIRecipeProposal],
    provider: AIProviderConfig,
) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = Path(evidence_base) / "ia" / ts
    root.mkdir(parents=True, exist_ok=True)

    (root / "contexto_redactado.json").write_text(
        json.dumps(contexto, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (root / "propuestas.json").write_text(
        json.dumps(
            {
                "proveedor": provider.public_dict(),
                "propuestas": [p.as_dict() for p in propuestas],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def guardar_seleccion_ia(
    session_dir: str | Path,
    *,
    propuesta: AIRecipeProposal,
    correccion: Correccion,
    resultado: dict | None = None,
) -> None:
    root = Path(session_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "propuesta": propuesta.as_dict(),
        "correccion_normalizada": asdict(correccion),
        "resultado_ciclo": resultado,
    }
    (root / "seleccion.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _solicitar_json_gemma(
    provider: AIProviderConfig,
    *,
    system_prompt: str,
    user_payload: dict,
    timeout: int = 120,
) -> dict:
    endpoint = provider.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": provider.model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
    }
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    resp = requests.post(
        endpoint,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            "Laboratorio UTB respondió HTTP "
            f"{resp.status_code}: {resp.text[:1200]}"
        )
    texto = _extraer_contenido_chat(resp.json())
    return _extraer_json(texto)


def _lista_strings(data: dict, key: str) -> list[str]:
    """Normaliza listas semánticas devueltas por el modelo.

    Algunos modelos devuelven un único string para campos conceptualmente
    listados. No debe perderse una corrección verificada por una diferencia
    superficial de formato.
    """
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]


def generalizar_correccion_exitosa(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    descripcion: str,
    detalle: str,
    metadata_hallazgo: dict,
    matriz_pruebas: list[dict],
    source_relative: str,
    codigo_antes: str,
    codigo_despues: str,
    diff: str,
    propuesta: AIRecipeProposal,
    provider: AIProviderConfig | None = None,
    timeout: int = 120,
) -> tuple[RemediationKnowledge, dict, AIProviderConfig]:
    """Extrae la medicina semántica de una corrección ya verificada."""
    provider = provider or cargar_configuracion_opencode()

    contexto = {
        "sistema_origen": cfg.sistema,
        "version_origen": cfg.version_objetivo,
        "control_id": control_id,
        "descripcion_hallazgo": descripcion,
        "detalle_observado": detalle,
        "hallazgo_objetivo": _redactar_estructura(
            metadata_hallazgo
        ),
        "matriz_pruebas": _redactar_estructura(matriz_pruebas),
        "archivo_origen": source_relative,
        "extension_origen": Path(source_relative).suffix.lower(),
        "propuesta_que_funciono": _redactar_estructura(
            propuesta.as_dict()
        ),
        "codigo_antes_redactado": recortar_codigo(
            redactar_secretos(codigo_antes),
            _pistas_utiles(control_id, descripcion, detalle),
            max_chars=18000,
        ),
        "codigo_despues_redactado": recortar_codigo(
            redactar_secretos(codigo_despues),
            _pistas_utiles(control_id, descripcion, detalle),
            max_chars=18000,
        ),
        "diff_redactado": redactar_secretos(diff)[:18000],
    }

    system_prompt = (
        "Acabas de observar una corrección de seguridad que YA fue verificada "
        "por pruebas dinámicas. Tu tarea NO es guardar el parche literal. "
        "Debes extraer la medicina semántica reusable para aplicaciones "
        "distintas, lenguajes distintos y estructuras distintas. "
        "El resultado debe explicar la causa raíz, la propiedad de seguridad "
        "que siempre debe cumplirse, señales para reconocer el mismo problema, "
        "una estrategia general independiente de nombres concretos, requisitos "
        "de implementación, anti-patrones que no deben repetirse y un contrato "
        "de verificación. Evita nombres de clases, funciones, rutas, usuarios, "
        "variables y archivos del sistema origen salvo que sean conceptos "
        "universales. No incluyas código literal de la aplicación. "
        "Responde únicamente JSON válido."
    )

    expected = {
        "titulo": "nombre genérico de la medicina",
        "causa_raiz": "causa raíz general",
        "invariante_seguridad": "propiedad que debe cumplirse siempre",
        "estrategia_general": ["paso reusable 1", "paso reusable 2"],
        "señales_aplicabilidad": ["señal general 1"],
        "requisitos_implementacion": ["requisito 1"],
        "anti_patrones": ["qué no hacer"],
        "contrato_verificacion": ["prueba/invariante verificable"],
        "consideraciones": ["limitación o condición"],
        "lenguajes_observados": [Path(source_relative).suffix.lower()],
        "frameworks_observados": [],
    }

    data = _solicitar_json_gemma(
        provider,
        system_prompt=system_prompt,
        user_payload={
            "formato_obligatorio": expected,
            "caso_verificado": contexto,
        },
        timeout=timeout,
    )

    for key in (
        "titulo",
        "causa_raiz",
        "invariante_seguridad",
    ):
        if not str(data.get(key) or "").strip():
            raise RuntimeError(
                f"Gemma no devolvió un valor válido en '{key}'."
            )

    knowledge = RemediationKnowledge(
        control_id=control_id,
        titulo=str(data["titulo"]).strip(),
        causa_raiz=str(data["causa_raiz"]).strip(),
        invariante_seguridad=str(
            data["invariante_seguridad"]
        ).strip(),
        estrategia_general=_lista_strings(
            data, "estrategia_general"
        ),
        señales_aplicabilidad=_lista_strings(
            data, "señales_aplicabilidad"
        ),
        requisitos_implementacion=_lista_strings(
            data, "requisitos_implementacion"
        ),
        anti_patrones=_lista_strings(data, "anti_patrones"),
        contrato_verificacion=_lista_strings(
            data, "contrato_verificacion"
        ),
        consideraciones=_lista_strings(
            data, "consideraciones"
        ),
        lenguajes_observados=_lista_strings(
            data, "lenguajes_observados"
        ),
        frameworks_observados=_lista_strings(
            data, "frameworks_observados"
        ),
        familia_control=normalizar_familia_control(control_id),
        tipo_control=(
            str(metadata_hallazgo.get("tipo_control")).strip()
            if metadata_hallazgo.get("tipo_control")
            else None
        ),
        verificada=True,
        casos_exitosos=1,
    )
    knowledge.ensure_id()
    return knowledge, contexto, provider