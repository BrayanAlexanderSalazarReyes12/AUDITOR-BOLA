"""Orquestación determinista del aprendizaje adaptativo de parches IA.

Este módulo no modifica código ni decide si una vulnerabilidad fue corregida.
Solo mantiene el estado de los intentos para que la capa de GUI/QA pueda:
1) evitar repetir propuestas, 2) cambiar de estrategia tras dos fallos y
3) conservar evidencia compacta de cada intento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


MAX_ADAPTIVE_ATTEMPTS = 6
STRATEGY_RESET_AFTER_FAILURES = 2


@dataclass
class AdaptiveAttempt:
    number: int
    proposal_id: str
    enfoque: str
    estrategia_conceptual: str
    estado_final: str
    estado_patch: str
    motivo: str = ""
    estado_despues: str | None = None
    regresiones: list[dict] = field(default_factory=list)

    def as_feedback(self) -> dict:
        return {
            "numero_intento": self.number,
            "propuesta_anterior": {
                "id": self.proposal_id,
                "enfoque": self.enfoque,
                "estrategia_conceptual": self.estrategia_conceptual,
            },
            "resultado": {
                "estado_final": self.estado_final,
                "estado_patch": self.estado_patch,
                "estado_despues": self.estado_despues,
                "motivo": self.motivo,
                "regresiones": self.regresiones,
            },
        }


def strategy_reset_required(failure_count: int) -> bool:
    """Cambia de capa/mecanismo después de dos intentos fallidos."""
    return int(failure_count) >= STRATEGY_RESET_AFTER_FAILURES


def compact_feedback(attempts: Iterable[AdaptiveAttempt]) -> list[dict]:
    return [attempt.as_feedback() for attempt in attempts]


def choose_next_proposal(proposals: Iterable, attempted_ids: set[str] | None = None):
    """Devuelve la primera propuesta válida no intentada.

    La validación contextual ya la realiza ai_recipes; aquí solo evitamos
    repetir exactamente la misma propuesta dentro de una ronda adaptativa.
    """
    attempted = attempted_ids or set()
    for proposal in proposals:
        proposal_id = str(getattr(proposal, "id", "") or "").strip()
        if not proposal_id or proposal_id in attempted:
            continue
        if getattr(proposal, "validacion_ok", True) is False:
            continue
        return proposal
    return None
