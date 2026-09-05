from backend.agents.judge import evaluate_case_state
from backend.agents.opponent import simulate_opponent
from backend.legal_domain.labor.evidence_gap import detect_evidence_gaps
from backend.legal_domain.labor.inquiry import select_questions
from backend.legal_domain.labor.legal_search import search_law
from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.actions import LegalAction
from backend.legal_rl.policy import RuleBasedPolicy
from backend.legal_rl.state import CaseState, EvidenceStatus


def _probation_state() -> CaseState:
    state = CaseState(
        dispute_type="probation_termination",
        facts={"employment_duration_months": 8},
    )
    get_labor_model().prepare_state(state)
    detect_evidence_gaps(state)
    return state


def test_evidence_gap_supports_all_four_statuses():
    state = _probation_state()
    assert any(gap.status in {EvidenceStatus.MISSING, EvidenceStatus.PARTIAL} for gap in state.evidence_gaps)
    state.apply_facts({
        "has_written_contract": True,
        "contract_term_months": 36,
        "probation_period_months": 6,
    })
    state.add_evidence("劳动合同")
    detect_evidence_gaps(state)
    assert next(g for g in state.evidence_gaps if g.element_id == "valid_probation_term").status == EvidenceStatus.PROVEN
    state.facts["conflict_elements"] = ["termination_occurred"]
    detect_evidence_gaps(state)
    assert next(g for g in state.evidence_gaps if g.element_id == "termination_occurred").status == EvidenceStatus.CONFLICT


def test_active_inquiry_uses_configured_priority():
    state = _probation_state()
    questions = select_questions(state, limit=2)
    assert questions[0] == "是否签订了书面劳动合同？"
    assert len(questions) == 2


def test_rule_policy_starts_with_fact_inquiry():
    state = _probation_state()
    decision = RuleBasedPolicy().decide(state)
    assert decision.action == LegalAction.ASK_FACT


def test_stop_requires_judge_approval():
    state = _probation_state()
    state.apply_facts({key: True for key in state.key_facts})
    state.facts.update({"monthly_salary": 10000, "employment_duration_months": 8})
    for name in state.key_evidence:
        state.add_evidence(name)
    state.retrieved_laws = search_law("试用期解除 违法解除 经济补偿")
    detect_evidence_gaps(state)
    state.retrieved_cases = [{"case_id": "labor_001"}]
    simulate_opponent(state)
    verdict = evaluate_case_state(state)
    assert verdict.can_stop is True
    assert RuleBasedPolicy().predict(state) == LegalAction.CALCULATE
    state.compensation_estimate = {"amount": 20000}
    assert RuleBasedPolicy().predict(state) == LegalAction.STOP

