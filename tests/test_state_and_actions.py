from backend.legal_rl.actions import ACTION_TO_NODE, LegalAction, validate_action_mapping
from backend.legal_rl.state import CaseState


def test_case_state_updates_facts_and_evidence_once():
    state = CaseState(missing_facts=["has_written_contract", "monthly_salary"])
    state.apply_facts({"has_written_contract": False, "monthly_salary": 10000})
    state.add_evidence("劳动合同")
    state.add_evidence("劳动合同")
    assert state.facts["has_written_contract"] is False
    assert state.missing_facts == []
    assert [item.name for item in state.evidence] == ["劳动合同"]


def test_every_action_maps_to_one_real_node():
    validate_action_mapping()
    assert set(ACTION_TO_NODE) == set(LegalAction)
    assert len(set(ACTION_TO_NODE.values())) == len(LegalAction)

