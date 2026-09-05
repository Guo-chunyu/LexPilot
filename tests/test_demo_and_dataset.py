import json
from pathlib import Path

from backend.legal_rl.actions import LegalAction
from backend.workflow import LexPilotEngine


def test_dataset_contains_sixty_pending_review_cases():
    paths = sorted(Path("datasets/synthetic_cases").glob("*.json"))
    assert len(paths) == 60
    difficulties = set()
    disputes = set()
    for path in paths:
        case = json.loads(path.read_text(encoding="utf-8"))
        assert case["human_reviewed"] is False
        assert case["review_status"] == "pending_law_student_review"
        difficulties.add(case["difficulty"])
        disputes.add(case["dispute_type"])
    assert difficulties == {"simple", "medium", "complex"}
    assert len(disputes) == 6


def test_acceptance_demo_is_inquiry_first_and_policy_driven():
    engine = LexPilotEngine()
    first = engine.process("我在公司工作8个月，昨天领导微信告诉我明天不用来了，说我试用期表现不合格，我没有拿到赔偿。")
    state = first["case_state"]
    assert state.current_action == LegalAction.ASK_FACT
    assert "劳动合同" in first["reply"]

    second = engine.process("签了劳动合同，合同期限3年，试用期6个月。", state)
    third = engine.process("公司没有告知录用条件，也没有考核记录，只有微信，没有书面通知。", second["case_state"])
    fourth = engine.process("我的月工资是10000元。", third["case_state"])
    assert fourth["case_state"].current_action == LegalAction.REQUEST_EVIDENCE

    final = engine.process("我有劳动合同和工资流水。", fourth["case_state"])
    state = final["case_state"]
    actions = [record.action for record in state.action_history]
    assert actions[0] == LegalAction.ASK_FACT
    assert LegalAction.REQUEST_EVIDENCE in actions
    assert LegalAction.SEARCH_LAW in actions
    assert LegalAction.SIMULATE_OPPONENT in actions
    assert LegalAction.VERIFY in actions
    assert actions[-1] == LegalAction.STOP
    assert state.done is True
    assert state.final_report["legal_basis"]
    assert state.final_report["opponent_arguments"]
    assert state.final_report["compensation_estimate"]["status"] == "ESTIMATE_ONLY"


def test_short_contextual_answer_updates_the_pending_fact():
    engine = LexPilotEngine()
    first = engine.process("我在公司工作8个月，公司说试用期不合格，明天不用来了。")

    second = engine.process("签了，有三年，试用期六个月。", first["case_state"])
    state = second["case_state"]

    assert state.facts["has_written_contract"] is True
    assert state.facts["contract_term_months"] == 36
    assert state.facts["probation_period_months"] == 6
    assert "录用条件" in second["reply"]
