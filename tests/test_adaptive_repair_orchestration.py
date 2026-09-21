from dataclasses import dataclass

from auditor_bola.adaptive_repair import (
    AdaptiveAttempt,
    MAX_ADAPTIVE_ATTEMPTS,
    choose_next_proposal,
    compact_feedback,
    strategy_reset_required,
)


@dataclass
class Proposal:
    id: str
    validacion_ok: bool = True


def test_strategy_changes_after_two_failures():
    assert strategy_reset_required(0) is False
    assert strategy_reset_required(1) is False
    assert strategy_reset_required(2) is True


def test_choose_next_proposal_skips_invalid_and_repeated():
    proposals = [
        Proposal("IA-1", validacion_ok=False),
        Proposal("IA-2"),
        Proposal("IA-3"),
    ]
    assert choose_next_proposal(proposals, {"IA-2"}).id == "IA-3"


def test_feedback_contains_reproducible_failure_evidence():
    attempt = AdaptiveAttempt(
        number=1,
        proposal_id="IA-1",
        enfoque="MINIMA",
        estrategia_conceptual="guard local",
        estado_final="NO_CORREGIDO",
        estado_patch="PATCH_FAILED",
        motivo="el hallazgo sigue reproduciéndose",
        estado_despues="HALLAZGO",
    )
    feedback = compact_feedback([attempt])
    assert feedback[0]["numero_intento"] == 1
    assert feedback[0]["resultado"]["estado_despues"] == "HALLAZGO"
    assert feedback[0]["resultado"]["motivo"]


def test_adaptive_attempt_budget_is_finite():
    assert MAX_ADAPTIVE_ATTEMPTS >= 3
