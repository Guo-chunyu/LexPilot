"""Convert CaseState into the normalized vector consumed by RL policies."""

from __future__ import annotations

import numpy as np

from backend.legal_rl.state import CaseState


OBSERVATION_NAMES = (
    "fact_completeness",
    "evidence_completeness",
    "legal_confidence",
    "issue_coverage",
    "contradiction_score",
    "remaining_key_facts_ratio",
    "remaining_evidence_ratio",
    "step_ratio",
)


def state_to_vector(state: CaseState) -> np.ndarray:
    """Return an 8-dimensional float32 vector with every value in [0, 1]."""

    remaining_facts = len(state.missing_facts) / max(len(state.key_facts), 1)
    remaining_evidence = len(state.missing_evidence) / max(len(state.key_evidence), 1)
    step_ratio = state.step_count / max(state.max_steps, 1)
    values = np.asarray([
        state.fact_completeness,
        state.evidence_completeness,
        state.legal_confidence,
        state.issue_coverage,
        state.contradiction_score,
        remaining_facts,
        remaining_evidence,
        step_ratio,
    ], dtype=np.float32)
    return np.clip(values, 0.0, 1.0)

