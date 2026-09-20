"""Resolución genérica del archivo fuente asociado a un hallazgo.

Prioridad:
1. archivo de una receta existente;
2. archivos_fuente declarados en el perfil;
3. archivo estático de un control P2;
4. búsqueda heurística independiente del lenguaje/framework.

El objetivo es evitar que la GUI obligue al usuario a localizar manualmente
el archivo cada vez que selecciona un hallazgo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigObjetivo


_SOURCE_EXTENSIONS = {
    ".py", ".java", ".kt", ".kts", ".js", ".jsx", ".ts", ".tsx",
    ".php", ".cs", ".go", ".rb", ".scala", ".groovy", ".jsp", ".jspx",
    ".vue", ".svelte", ".html", ".htm", ".xml", ".properties",
    ".yml", ".yaml", ".toml", ".ini", ".conf", ".cfg",
}

_SKIP_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    "node_modules", "vendor", ".venv", "venv", "env",
    "dist", "build", "target", "coverage", ".next",
}

_GENERIC_ROUTE_TOKENS = {
    "api", "v1", "v2", "v3", "id", "ids", "http", "https",
}

_METHOD_MARKERS = {
    "GET": (
        "@get", "getmapping", "doget(", "router.get", ".get(",
        "requestmethod.get", 'methods=["get"', "methods=['get'",
    ),
    "POST": (
        "@post", "postmapping", "dopost(", "router.post", ".post(",
        "requestmethod.post", 'methods=["post"', "methods=['post'",
    ),
    "PUT": (
        "@put", "putmapping", "doput(", "router.put", ".put(",
        "requestmethod.put", 'methods=["put"', "methods=['put'",
    ),
    "PATCH": (
        "@patch", "patchmapping", "dopatch(", "router.patch", ".patch(",
        "requestmethod.patch", 'methods=["patch"', "methods=['patch'",
    ),
    "DELETE": (
        "@delete", "deletemapping", "dodelete(", "router.delete", ".delete(",
        "requestmethod.delete", 'methods=["delete"', "methods=['delete'",
    ),
}


@dataclass
class SourceCandidate:
    archivo: str
    score: int
    razones: list[str] = field(default_factory=list)


@dataclass
class SourceResolution:
    archivo: str | None
    confianza: str
    origen: str
    candidatos: list[SourceCandidate] = field(default_factory=list)


@dataclass
class RelatedSource:
    archivo: str
    score: int
    razones: list[str] = field(default_factory=list)


@dataclass
class SourceContextResolution:
    principal: SourceResolution
    relacionados: list[RelatedSource] = field(default_factory=list)


_LAYER_TOKENS = {
    "controller", "handler", "route", "router", "servlet", "resource",
    "service", "repository", "repo", "dao", "model", "entity",
    "security", "auth", "permission", "policy", "middleware", "filter",
    "config", "settings",
}


def _symbol_tokens(text: str, relative: str) -> list[str]:
    """Extrae símbolos y referencias útiles sin asumir framework."""
    tokens: list[str] = []
    patterns = (
        r"(?m)^\s*(?:class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"(?m)^\s*(?:def|function|func)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"(?m)^\s*(?:public|protected|private|static|final|async|export\s+)?"
        r"(?:[A-Za-z_][A-Za-z0-9_<>,\[\]? ]+\s+)?"
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        r"(?m)^\s*(?:from|import|require\()\s*[\"']?([A-Za-z0-9_./-]+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = str(match.group(1) or "").strip().lower()
            if len(value) >= 4 and value not in tokens:
                tokens.append(value)
            if len(tokens) >= 40:
                break
        if len(tokens) >= 40:
            break

    stem = Path(relative).stem.lower()
    if len(stem) >= 4 and stem not in tokens:
        tokens.insert(0, stem)

    for piece in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", relative):
        value = piece.lower()
        if value not in tokens:
            tokens.append(value)

    return tokens[:50]


def _related_score(
    path: Path,
    root: Path,
    *,
    principal: Path,
    principal_text: str,
    principal_tokens: list[str],
    metodo: str | None,
    ruta: str | None,
    descripcion: str | None,
) -> RelatedSource:
    relative = path.relative_to(root).as_posix()
    if path == principal:
        return RelatedSource(relative, -1000, ["archivo principal"])

    text = _safe_read(path)
    if text is None:
        return RelatedSource(relative, -1000, ["ilegible"])

    lower_text = text.lower()
    lower_path = relative.lower()
    principal_lower = principal_text.lower()
    score = 0
    reasons: list[str] = []

    same_dir = path.parent == principal.parent
    if same_dir:
        score += 8
        reasons.append("misma carpeta")

    for token in principal_tokens[:30]:
        if token in lower_text:
            score += 5
            reasons.append(f"referencia:{token}")
        if token in lower_path:
            score += 3

    other_stem = path.stem.lower()
    if len(other_stem) >= 4 and other_stem in principal_lower:
        score += 22
        reasons.append("referenciado por archivo principal")

    principal_stem = principal.stem.lower()
    if len(principal_stem) >= 4 and principal_stem in lower_text:
        score += 22
        reasons.append("referencia al archivo principal")

    route_tokens = _route_tokens(ruta)
    for token in route_tokens:
        if token in lower_text:
            score += 6
            reasons.append(f"ruta:{token}")

    method = (metodo or "").upper()
    markers = _METHOD_MARKERS.get(method, ())
    if markers and any(marker in lower_text for marker in markers):
        score += 4
        reasons.append(f"método:{method}")

    desc_tokens = _description_tokens(descripcion)
    for token in desc_tokens:
        if token in lower_text:
            score += 1

    layer_hits = [
        token
        for token in _LAYER_TOKENS
        if token in lower_path or token in lower_text[:5000]
    ]
    if layer_hits:
        score += min(10, len(layer_hits) * 2)
        reasons.append("capa:" + ",".join(sorted(layer_hits)[:4]))

    if path.suffix.lower() == principal.suffix.lower():
        score += 2

    bad_parts = {"test", "tests", "docs", "doc", "examples", "example"}
    if any(part.lower() in bad_parts for part in path.parts):
        score -= 8

    return RelatedSource(relative, score, reasons[:10])


def resolver_contexto_fuente(
    cfg: ConfigObjetivo,
    target_root: str | Path,
    *,
    control_id: str,
    metodo: str | None = None,
    ruta: str | None = None,
    descripcion: str | None = None,
    max_relacionados: int = 8,
) -> SourceContextResolution:
    """Resuelve archivo principal y archivos relacionados por flujo.

    No presupone que el archivo donde aparece la evidencia sea la causa raíz.
    A partir del archivo principal busca referencias, símbolos compartidos y
    capas típicas (controller/service/DAO/repository/security/config), siempre
    dentro de target_root.
    """
    principal = resolver_archivo_fuente(
        cfg,
        target_root,
        control_id=control_id,
        metodo=metodo,
        ruta=ruta,
        descripcion=descripcion,
    )
    if not principal.archivo:
        return SourceContextResolution(principal, [])

    root = Path(target_root).resolve()
    principal_path = (root / principal.archivo).resolve()
    principal_text = _safe_read(principal_path) or ""
    tokens = _symbol_tokens(principal_text, principal.archivo)

    related = [
        _related_score(
            path,
            root,
            principal=principal_path,
            principal_text=principal_text,
            principal_tokens=tokens,
            metodo=metodo,
            ruta=ruta,
            descripcion=descripcion,
        )
        for path in _iter_source_files(root)
    ]
    related = [item for item in related if item.score > 8]
    related.sort(key=lambda item: (-item.score, item.archivo))

    # Si el perfil ya declara más de un archivo, se conservan como contexto
    # aunque la heurística de referencias no les asigne suficiente puntuación.
    declared = _declared_files(
        cfg,
        control_id=control_id,
        metodo=metodo,
        ruta=ruta,
    )
    known = {item.archivo for item in related}
    for relative in declared:
        if relative == principal.archivo or relative in known:
            continue
        if _exists(root, relative):
            related.insert(
                0,
                RelatedSource(
                    relative,
                    500,
                    ["declarado explícitamente en el perfil"],
                ),
            )
            known.add(relative)

    return SourceContextResolution(
        principal=principal,
        relacionados=related[:max(0, int(max_relacionados))],
    )


def _normalizar_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _exists(root: Path, relative: str) -> bool:
    path = (root / relative).resolve()
    return path.exists() and (path == root or root in path.parents)


def _match_control(item, control_id: str, metodo: str | None, ruta: str | None) -> bool:
    if getattr(item, "id_control", None) != control_id:
        return False

    item_method = str(
        getattr(item, "metodo", None)
        or getattr(item, "direct_metodo", None)
        or ""
    ).upper()
    item_route = str(
        getattr(item, "ruta", None)
        or getattr(item, "direct_ruta", None)
        or ""
    )

    if metodo and item_method and item_method != metodo.upper():
        return False
    if ruta and item_route and item_route != ruta:
        return False
    return True


def _declared_files(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    metodo: str | None,
    ruta: str | None,
) -> list[str]:
    files: list[str] = []

    recipe = cfg.correccion_por_control(control_id)
    if recipe and recipe.archivo:
        files.append(recipe.archivo)

    groups = (
        cfg.endpoints,
        cfg.chequeos_acceso,
        cfg.chequeos_agente,
        cfg.chequeos_pilar2,
    )
    for group in groups:
        for item in group:
            if not _match_control(item, control_id, metodo, ruta):
                continue
            archivo = getattr(item, "archivo", None)
            if archivo:
                files.append(archivo)
            files.extend(getattr(item, "archivos_fuente", []) or [])

    unique: list[str] = []
    for path in files:
        normalized = _normalizar_rel(path)
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _profile_hints(
    cfg: ConfigObjetivo,
    *,
    control_id: str,
    metodo: str | None,
    ruta: str | None,
) -> list[str]:
    hints: list[str] = []
    for group in (
        cfg.endpoints,
        cfg.chequeos_acceso,
        cfg.chequeos_agente,
        cfg.chequeos_pilar2,
    ):
        for item in group:
            if _match_control(item, control_id, metodo, ruta):
                hints.extend(getattr(item, "pistas_codigo", []) or [])
    return hints


def _route_tokens(route: str | None) -> list[str]:
    if not route:
        return []

    cleaned = re.sub(r"[{}<>:]", "/", route)
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_-]{2,}", cleaned)
    tokens: list[str] = []

    for token in raw:
        lower = token.lower()
        if lower in _GENERIC_ROUTE_TOKENS:
            continue
        if lower not in tokens:
            tokens.append(lower)

        # Variante singular sencilla para nombres REST comunes.
        if lower.endswith("es") and len(lower) > 5:
            singular = lower[:-2]
            if singular and singular not in tokens:
                tokens.append(singular)
        elif lower.endswith("s") and len(lower) > 4:
            singular = lower[:-1]
            if singular and singular not in tokens:
                tokens.append(singular)

    return tokens


def _description_tokens(description: str | None) -> list[str]:
    if not description:
        return []
    stop = {
        "para", "como", "desde", "este", "esta", "esto", "usuario",
        "usuarios", "acceso", "control", "hallazgo", "debe", "puede",
        "cannot", "should", "access", "user", "http", "true", "false",
    }
    result: list[str] = []
    for token in re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ_][A-Za-z0-9ÁÉÍÓÚáéíóúÑñ_-]{3,}", description):
        lower = token.lower()
        if lower not in stop and lower not in result:
            result.append(lower)
    return result[:12]


def _iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.lower() in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _SOURCE_EXTENSIONS and path.name.lower() != "dockerfile":
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue
        yield path


def _safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _score_candidate(
    path: Path,
    root: Path,
    *,
    metodo: str | None,
    ruta: str | None,
    descripcion: str | None,
    hints: list[str],
) -> SourceCandidate:
    relative = path.relative_to(root).as_posix()
    lower_path = relative.lower()
    text = _safe_read(path)
    if text is None:
        return SourceCandidate(relative, -1000, ["ilegible"])

    lower_text = text.lower()
    score = 0
    reasons: list[str] = []

    route_tokens = _route_tokens(ruta)
    desc_tokens = _description_tokens(descripcion)
    all_hints = []
    for item in [*hints, *route_tokens, *desc_tokens]:
        value = str(item).strip().lower()
        if len(value) >= 3 and value not in all_hints:
            all_hints.append(value)

    # Coincidencia exacta de ruta: señal muy fuerte.
    if ruta and ruta.lower() in lower_text:
        score += 45
        reasons.append("ruta exacta en código")

    for token in route_tokens:
        if token in lower_text:
            score += 12
            reasons.append(f"ruta:{token}")
        if token in lower_path:
            score += 9
            reasons.append(f"archivo:{token}")

    for token in hints:
        value = str(token).strip().lower()
        if not value:
            continue
        if value in lower_text:
            score += 15
            reasons.append(f"pista:{value}")
        if value in lower_path:
            score += 10

    for token in desc_tokens:
        if token in lower_text:
            score += 2

    method = (metodo or "").upper()
    markers = _METHOD_MARKERS.get(method, ())
    if markers and any(marker in lower_text for marker in markers):
        score += 12
        reasons.append(f"método:{method}")

    # Favorece archivos de implementación y penaliza pruebas/documentación.
    if path.suffix.lower() in {
        ".py", ".java", ".kt", ".js", ".jsx", ".ts", ".tsx",
        ".php", ".cs", ".go", ".rb", ".scala", ".groovy", ".jsp",
    }:
        score += 4

    bad_parts = {"test", "tests", "docs", "doc", "examples", "example"}
    if any(part.lower() in bad_parts for part in path.parts):
        score -= 12

    if all_hints and not any(token in lower_text or token in lower_path for token in all_hints):
        score -= 5

    return SourceCandidate(relative, score, reasons[:8])


def resolver_archivo_fuente(
    cfg: ConfigObjetivo,
    target_root: str | Path,
    *,
    control_id: str,
    metodo: str | None = None,
    ruta: str | None = None,
    descripcion: str | None = None,
) -> SourceResolution:
    """Resuelve automáticamente el archivo más relacionado con un hallazgo."""
    root = Path(target_root).resolve()
    if not root.exists():
        return SourceResolution(None, "ninguna", "target_root inexistente", [])

    for relative in _declared_files(
        cfg,
        control_id=control_id,
        metodo=metodo,
        ruta=ruta,
    ):
        if _exists(root, relative):
            return SourceResolution(
                relative,
                "alta",
                "perfil/receta",
                [SourceCandidate(relative, 1000, ["declarado explícitamente"])],
            )

    hints = _profile_hints(
        cfg,
        control_id=control_id,
        metodo=metodo,
        ruta=ruta,
    )

    candidates = [
        _score_candidate(
            path,
            root,
            metodo=metodo,
            ruta=ruta,
            descripcion=descripcion,
            hints=hints,
        )
        for path in _iter_source_files(root)
    ]
    candidates = [item for item in candidates if item.score > 0]
    candidates.sort(key=lambda item: (-item.score, item.archivo))

    if not candidates:
        return SourceResolution(None, "ninguna", "sin coincidencias", [])

    best = candidates[0]
    second_score = candidates[1].score if len(candidates) > 1 else -999

    if best.score >= 30 and best.score - second_score >= 8:
        confidence = "alta"
    elif best.score >= 16:
        confidence = "media"
    else:
        confidence = "baja"

    return SourceResolution(
        best.archivo,
        confidence,
        "búsqueda automática",
        candidates[:5],
    )