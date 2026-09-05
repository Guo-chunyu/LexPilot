"""Uncertainty-aware active inquiry for the highest-value missing facts."""

from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.state import CaseState, EvidenceStatus, InquiryCandidate


def select_questions(state: CaseState, limit: int = 2) -> list[str]:
    """Rank questions by expected case information gain and interaction cost."""

    model = get_labor_model()
    model.prepare_state(state)
    config = model.get(state.dispute_type)
    gap_by_id = {gap.element_id: gap for gap in state.evidence_gaps}
    candidates: list[InquiryCandidate] = []
    for spec in model.question_specs(state.dispute_type):
        fact_id = spec["id"]
        if fact_id not in state.missing_facts:
            continue
        related = [
            element
            for element in config.get("elements", [])
            if fact_id in element.get("required_facts", [])
        ]
        legal_importance = min(float(spec.get("priority", 0)) / 100.0, 1.0)
        closure_values = []
        evidence_values = []
        conflict_urgency = 0.0
        present = {item.name for item in state.evidence}
        for element in related:
            missing_count = sum(
                state.facts.get(required) is None or state.facts.get(required) == ""
                for required in element.get("required_facts", [])
            )
            closure_values.append(1.0 / max(missing_count, 1))
            evidence_names = element.get("evidence_any", [])
            evidence_values.append(
                sum(name in present for name in evidence_names) / max(len(evidence_names), 1)
            )
            if gap_by_id.get(element["id"]) and gap_by_id[element["id"]].status == EvidenceStatus.CONFLICT:
                conflict_urgency = 1.0

        expected_gain = sum(closure_values) / max(len(closure_values), 1)
        element_coverage = min(len(related) / max(len(config.get("elements", [])), 1) * 2.0, 1.0)
        evidence_leverage = max(evidence_values, default=0.0)
        interaction_cost = _interaction_cost(fact_id)
        score = (
            0.80 * legal_importance
            + 0.05 * expected_gain
            + 0.05 * element_coverage
            + 0.05 * evidence_leverage
            + 0.06 * conflict_urgency
            - 0.01 * interaction_cost
        )
        score = round(max(0.0, min(score, 1.0)), 4)
        candidates.append(InquiryCandidate(
            fact_id=fact_id,
            question=spec["question"],
            score=score,
            legal_importance=round(legal_importance, 4),
            expected_information_gain=round(expected_gain, 4),
            element_coverage=round(element_coverage, 4),
            evidence_leverage=round(evidence_leverage, 4),
            conflict_urgency=conflict_urgency,
            interaction_cost=interaction_cost,
            reason=(
                f"关联 {len(related)} 个法律要件，预计减少相关要件 "
                f"{expected_gain:.0%} 的事实不确定性。"
            ),
        ))

    candidates.sort(key=lambda item: (-item.score, -item.legal_importance, item.fact_id))
    state.inquiry_candidates = candidates
    selected = candidates[: max(1, min(limit, 2))]
    questions = [item.question for item in selected]
    state.pending_questions = questions
    state.pending_fact_ids = [item.fact_id for item in selected]
    return questions


def _interaction_cost(fact_id: str) -> float:
    if fact_id in {
        "has_written_contract", "recruitment_conditions_disclosed", "assessment_evidence_exists",
        "written_termination_notice", "employer_rules_disclosed", "disciplinary_evidence_exists",
        "employment_active", "overtime_approved",
    }:
        return 0.10
    if fact_id.endswith("_date") or fact_id in {"overtime_period", "work_schedule"}:
        return 0.35
    if fact_id in {"termination_reason", "termination_type"}:
        return 0.25
    return 0.20
