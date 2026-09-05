"""Evidence-gap detection derived from the labor domain model."""

from __future__ import annotations

from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.state import CaseState, EvidenceGap, EvidenceStatus


def detect_evidence_gaps(state: CaseState) -> list[EvidenceGap]:
    model = get_labor_model()
    model.prepare_state(state)
    config = model.get(state.dispute_type)
    present = {item.name for item in state.evidence}
    conflict_elements = set(state.facts.get("conflict_elements", []))
    gaps: list[EvidenceGap] = []

    for element in config["elements"]:
        required_facts = element.get("required_facts", [])
        evidence_candidates = element.get("evidence_any", [])
        known_facts = [key for key in required_facts if _known(state.facts.get(key))]
        matched_evidence = [name for name in evidence_candidates if name in present]
        missing_evidence = [name for name in evidence_candidates if name not in present]

        if element["id"] in conflict_elements or element["name"] in conflict_elements:
            status = EvidenceStatus.CONFLICT
            reason = "同一法律要素存在相互冲突的事实或证据。"
        elif len(known_facts) == len(required_facts) and matched_evidence:
            status = EvidenceStatus.PROVEN
            reason = "必要事实已知且至少有一项关联证据。"
        elif known_facts or matched_evidence:
            status = EvidenceStatus.PARTIAL
            reason = "已掌握部分事实或证据，但证据链尚不完整。"
        else:
            status = EvidenceStatus.MISSING
            reason = "必要事实和支持证据均不足。"

        gaps.append(EvidenceGap(
            element_id=element["id"],
            name=element["name"],
            status=status,
            evidence=matched_evidence,
            missing_evidence=missing_evidence,
            reason=reason,
        ))

    state.evidence_gaps = gaps
    _update_scores(state)
    from backend.legal_domain.labor.evidence_graph import build_evidence_graph

    build_evidence_graph(state)
    return gaps


def _known(value: object) -> bool:
    return value is not None and value != "" and value != []


def _update_scores(state: CaseState) -> None:
    total_facts = max(len(state.key_facts), 1)
    known_facts = sum(1 for fact in state.key_facts if _known(state.facts.get(fact)))
    state.fact_completeness = round(known_facts / total_facts, 4)

    weights = {
        EvidenceStatus.PROVEN: 1.0,
        EvidenceStatus.PARTIAL: 0.5,
        EvidenceStatus.CONFLICT: 0.25,
        EvidenceStatus.MISSING: 0.0,
    }
    total_elements = max(len(state.evidence_gaps), 1)
    weighted = sum(weights[gap.status] for gap in state.evidence_gaps)
    state.evidence_completeness = round(weighted / total_elements, 4)
    state.issue_coverage = state.evidence_completeness
    conflicts = sum(1 for gap in state.evidence_gaps if gap.status == EvidenceStatus.CONFLICT)
    state.contradiction_score = round(conflicts / total_elements, 4)
    state.legal_confidence = 1.0 if state.retrieved_laws else 0.0
    state.overall_confidence = round(
        0.35 * state.fact_completeness
        + 0.35 * state.evidence_completeness
        + 0.20 * state.legal_confidence
        + 0.10 * (1.0 - state.contradiction_score),
        4,
    )
