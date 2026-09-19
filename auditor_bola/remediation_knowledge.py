"""Base de conocimiento semántico de remediaciones.

Una "medicina" no es un parche literal. Describe por qué existe el fallo,
qué propiedad de seguridad debe restaurarse y qué contrato de verificación
debe cumplirse. Las implementaciones concretas se generan por aplicación.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


KNOWLEDGE_SCHEMA_VERSION = 1


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return cleaned.strip("-._") or "control"


def knowledge_root() -> Path:
    override = os.getenv("AUDITOR_REMEDIATION_KNOWLEDGE")
    if override:
        return Path(override).expanduser().resolve()

    recipe_root = os.getenv("AUDITOR_RECIPE_LIBRARY")
    if recipe_root:
        return (
            Path(recipe_root).expanduser().resolve()
            / "conocimiento"
        )

    return (
        Path(__file__).resolve().parent.parent
        / "recetas"
        / "conocimiento"
    ).resolve()


@dataclass
class RemediationKnowledge:
    control_id: str
    titulo: str
    causa_raiz: str
    invariante_seguridad: str
    estrategia_general: list[str]
    señales_aplicabilidad: list[str]
    requisitos_implementacion: list[str]
    anti_patrones: list[str]
    contrato_verificacion: list[str]
    consideraciones: list[str] = field(default_factory=list)
    lenguajes_observados: list[str] = field(default_factory=list)
    frameworks_observados: list[str] = field(default_factory=list)
    knowledge_id: str | None = None
    verificada: bool = True
    casos_exitosos: int = 0
    usos: int = 0
    usos_exitosos: int = 0

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "control_id": self.control_id,
            "causa_raiz": self.causa_raiz.strip(),
            "invariante_seguridad": self.invariante_seguridad.strip(),
            "estrategia_general": [
                item.strip() for item in self.estrategia_general
            ],
            "requisitos_implementacion": [
                item.strip() for item in self.requisitos_implementacion
            ],
            "contrato_verificacion": [
                item.strip() for item in self.contrato_verificacion
            ],
        }

    def ensure_id(self) -> str:
        if self.knowledge_id:
            return self.knowledge_id
        raw = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.knowledge_id = hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()
        return self.knowledge_id


@dataclass
class KnowledgeCandidate:
    path: Path
    knowledge: RemediationKnowledge
    score: int
    razones: list[str]

    def public_dict(self) -> dict:
        return {
            "path": str(self.path),
            "score": self.score,
            "razones": list(self.razones),
            "knowledge": asdict(self.knowledge),
        }


def _load_knowledge(path: Path) -> RemediationKnowledge:
    data = json.loads(path.read_text(encoding="utf-8"))
    return RemediationKnowledge(
        control_id=data["control_id"],
        titulo=data["titulo"],
        causa_raiz=data["causa_raiz"],
        invariante_seguridad=data["invariante_seguridad"],
        estrategia_general=list(data.get("estrategia_general") or []),
        señales_aplicabilidad=list(
            data.get("señales_aplicabilidad") or []
        ),
        requisitos_implementacion=list(
            data.get("requisitos_implementacion") or []
        ),
        anti_patrones=list(data.get("anti_patrones") or []),
        contrato_verificacion=list(
            data.get("contrato_verificacion") or []
        ),
        consideraciones=list(data.get("consideraciones") or []),
        lenguajes_observados=list(
            data.get("lenguajes_observados") or []
        ),
        frameworks_observados=list(
            data.get("frameworks_observados") or []
        ),
        knowledge_id=data.get("knowledge_id"),
        verificada=bool(data.get("verificada", True)),
        casos_exitosos=int(data.get("casos_exitosos", 0)),
        usos=int(data.get("usos", 0)),
        usos_exitosos=int(data.get("usos_exitosos", 0)),
    )


def guardar_conocimiento(
    knowledge: RemediationKnowledge,
    *,
    caso_exitoso: dict | None = None,
    root: str | Path | None = None,
) -> Path:
    base = (
        Path(root).resolve()
        if root is not None
        else knowledge_root()
    )
    knowledge_id = knowledge.ensure_id()
    folder = base / _safe_name(knowledge.control_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{knowledge_id[:24]}.json"

    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}

    casos = list(existing.get("ejemplos_verificados") or [])
    if caso_exitoso:
        # Solo metadatos/diff resumido; nunca credenciales.
        fingerprint = json.dumps(
            caso_exitoso,
            ensure_ascii=False,
            sort_keys=True,
        )
        if not any(
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            == fingerprint
            for item in casos
        ):
            casos.append(caso_exitoso)

    now = _ts()
    created = existing.get("creada_en") or now
    old_success = int(existing.get("casos_exitosos", 0))
    casos_exitosos = max(
        knowledge.casos_exitosos,
        old_success,
        len(casos),
    )

    data = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "tipo": "conocimiento_correctivo_semantico",
        "knowledge_id": knowledge_id,
        "control_id": knowledge.control_id,
        "titulo": knowledge.titulo,
        "causa_raiz": knowledge.causa_raiz,
        "invariante_seguridad": knowledge.invariante_seguridad,
        "estrategia_general": knowledge.estrategia_general,
        "señales_aplicabilidad": knowledge.señales_aplicabilidad,
        "requisitos_implementacion": knowledge.requisitos_implementacion,
        "anti_patrones": knowledge.anti_patrones,
        "contrato_verificacion": knowledge.contrato_verificacion,
        "consideraciones": knowledge.consideraciones,
        "lenguajes_observados": sorted(
            set(
                list(existing.get("lenguajes_observados") or [])
                + knowledge.lenguajes_observados
            )
        ),
        "frameworks_observados": sorted(
            set(
                list(existing.get("frameworks_observados") or [])
                + knowledge.frameworks_observados
            )
        ),
        "verificada": True,
        "casos_exitosos": casos_exitosos,
        "usos": max(
            knowledge.usos,
            int(existing.get("usos", 0)),
        ),
        "usos_exitosos": max(
            knowledge.usos_exitosos,
            int(existing.get("usos_exitosos", 0)),
        ),
        "creada_en": created,
        "actualizada_en": now,
        "ejemplos_verificados": casos[-10:],
    }

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _tokens(*values: str | None) -> set[str]:
    result: set[str] = set()
    for value in values:
        if not value:
            continue
        result.update(
            token.lower()
            for token in re.findall(
                r"[A-Za-zÁÉÍÓÚáéíóúÑñ_][A-Za-z0-9_-]{2,}",
                value,
            )
        )
    return result


def _score(
    knowledge: RemediationKnowledge,
    *,
    control_id: str,
    descripcion: str | None,
    tipo_control: str | None,
    source_text: str | None,
    extension: str | None,
) -> tuple[int, list[str]]:
    if knowledge.control_id != control_id:
        return -1, []

    score = 100
    reasons = ["mismo control de seguridad"]

    haystack = (
        (descripcion or "")
        + "\n"
        + (tipo_control or "")
        + "\n"
        + (source_text or "")[:20000]
    ).lower()
    target_tokens = _tokens(descripcion, tipo_control)

    signal_hits = 0
    for signal in knowledge.señales_aplicabilidad:
        signal_tokens = _tokens(signal)
        if signal.lower() in haystack or (
            signal_tokens and signal_tokens & target_tokens
        ):
            signal_hits += 1

    if signal_hits:
        score += min(30, signal_hits * 6)
        reasons.append(
            f"{signal_hits} señal(es) de aplicabilidad coinciden"
        )

    if extension and extension.lower() in {
        item.lower() for item in knowledge.lenguajes_observados
    }:
        score += 5
        reasons.append("tecnología observada previamente")

    score += min(20, knowledge.usos_exitosos * 4)
    score += min(10, knowledge.casos_exitosos * 2)
    return score, reasons


def buscar_conocimiento(
    *,
    control_id: str,
    descripcion: str | None = None,
    tipo_control: str | None = None,
    source_text: str | None = None,
    extension: str | None = None,
    root: str | Path | None = None,
) -> list[KnowledgeCandidate]:
    base = (
        Path(root).resolve()
        if root is not None
        else knowledge_root()
    )
    folder = base / _safe_name(control_id)
    if not folder.exists():
        return []

    candidates: list[KnowledgeCandidate] = []
    for path in sorted(folder.glob("*.json")):
        try:
            knowledge = _load_knowledge(path)
            score, reasons = _score(
                knowledge,
                control_id=control_id,
                descripcion=descripcion,
                tipo_control=tipo_control,
                source_text=source_text,
                extension=extension,
            )
            if score < 0:
                continue
            candidates.append(
                KnowledgeCandidate(
                    path=path,
                    knowledge=knowledge,
                    score=score,
                    razones=reasons,
                )
            )
        except Exception:
            continue

    candidates.sort(
        key=lambda item: (
            -item.score,
            -item.knowledge.usos_exitosos,
            -item.knowledge.casos_exitosos,
            item.knowledge.titulo.lower(),
        )
    )
    return candidates


def registrar_uso_conocimiento(
    path: str | Path,
    *,
    exitoso: bool,
    caso_exitoso: dict | None = None,
) -> None:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["usos"] = int(data.get("usos", 0)) + 1
    if exitoso:
        data["usos_exitosos"] = int(
            data.get("usos_exitosos", 0)
        ) + 1
        data["verificada"] = True
        if caso_exitoso:
            cases = list(data.get("ejemplos_verificados") or [])
            cases.append(caso_exitoso)
            data["ejemplos_verificados"] = cases[-10:]
            data["casos_exitosos"] = max(
                int(data.get("casos_exitosos", 0)),
                len(data["ejemplos_verificados"]),
            )
    data["actualizada_en"] = _ts()
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
