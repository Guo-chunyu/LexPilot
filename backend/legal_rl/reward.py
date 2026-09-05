"""Independent reward function with an inspectable component breakdown."""

from __future__ import annotations

from pydantic import BaseModel

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState


class RewardBreakdown(BaseModel):
    fact_gain: float = 0.0
    evidence_gain: float = 0.0
    issue_coverage_gain: float = 0.0
    confidence_gain: float = 0.0
    successful_resolution: float = 0.0
    action_cost: float = 0.0
    redundant_action: float = 0.0
    invalid_action: float = 0.0
    premature_stop: float = 0.0
    total: float = 0.0


def calculate_reward(
    previous: CaseState,
    current: CaseState,
    action: LegalAction,
    *,
    invalid_action: bool = False,
    redundant_action: bool = False,
    successful_resolution: bool = False,
    premature_stop: bool = False,
) -> RewardBreakdown:
    """Apply the first-stage reward formula and preserve every contribution."""

    fact_gain = 2.0 * max(current.fact_completeness - previous.fact_completeness, 0.0)
    evidence_gain = 3.0 * max(current.evidence_completeness - previous.evidence_completeness, 0.0)
    issue_gain = 2.0 * max(current.issue_coverage - previous.issue_coverage, 0.0)
    confidence_gain = 2.0 * max(current.overall_confidence - previous.overall_confidence, 0.0)
    resolution = 5.0 if successful_resolution else 0.0
    action_cost = -0.5
    redundant = -1.0 if redundant_action else 0.0
    invalid = -3.0 if invalid_action else 0.0
    premature = -5.0 if premature_stop else 0.0
    total = sum((fact_gain, evidence_gain, issue_gain, confidence_gain, resolution,
                 action_cost, redundant, invalid, premature))
    return RewardBreakdown(
        fact_gain=round(fact_gain, 4),
        evidence_gain=round(evidence_gain, 4),
        issue_coverage_gain=round(issue_gain, 4),
        confidence_gain=round(confidence_gain, 4),
        successful_resolution=resolution,
        action_cost=action_cost,
        redundant_action=redundant,
        invalid_action=invalid,
        premature_stop=premature,
        total=round(total, 4),
    )

