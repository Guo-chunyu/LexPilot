import pytest

from backend.legal_domain.labor.facts import extract_labor_facts
from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.state import CaseState
from backend.workflow import LexPilotEngine


CURRENT_QUESTION = "公司是否在入职时明确告知了具体录用条件？"
LEGACY_QUESTION = "公司是否在入职时明确告知并留存了录用条件？"


class CountingProvider:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0
        self.thinking_levels = []

    def generate_json(
        self,
        prompt,
        schema,
        *,
        max_output_tokens=2048,
        thinking_level=None,
    ):
        self.calls += 1
        self.thinking_levels.append(thinking_level)
        return self.payload


def _pending_probation_state(*, legacy_question: bool = False) -> CaseState:
    state = CaseState(
        dispute_type="probation_termination",
        facts={
            "employment_duration_months": 8,
            "has_written_contract": True,
            "contract_term_months": 36,
            "probation_period_months": 6,
        },
    )
    get_labor_model().prepare_state(state)
    state.pending_questions = [LEGACY_QUESTION if legacy_question else CURRENT_QUESTION]
    if not legacy_question:
        state.pending_fact_ids = ["recruitment_conditions_disclosed"]
    return state


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("告知并留存了", True),
        ("公司入职时明确说过，也让我签字确认了。", True),
        ("有，HR 当时发给我并让我签收了", True),
        ("没有留存书面材料，但公司确实告知过", True),
        ("没有，公司从未向我说明过录用条件", False),
        ("没告知，也没有让我签过任何文件", False),
    ],
)
def test_contextual_answer_understands_natural_affirmative_and_negative_phrases(
    answer: str,
    expected: bool,
):
    state = extract_labor_facts(answer, _pending_probation_state())

    assert state.facts["recruitment_conditions_disclosed"] is expected
    assert "recruitment_conditions_disclosed" not in state.missing_facts


def test_contextual_answer_supports_question_wording_from_existing_sessions():
    state = extract_labor_facts("告知并留存了", _pending_probation_state(legacy_question=True))

    assert state.facts["recruitment_conditions_disclosed"] is True


def test_engine_advances_instead_of_repeating_answered_question():
    result = LexPilotEngine().process("告知并留存了", _pending_probation_state())

    state = result["case_state"]
    assert state.facts["recruitment_conditions_disclosed"] is True
    assert CURRENT_QUESTION not in result["reply"]
    assert "考核" in result["reply"]
    assert state.pending_fact_ids == ["assessment_evidence_exists"]


def test_uncertain_answer_remains_unanswered_and_is_asked_again():
    result = LexPilotEngine().process("这个我不清楚，想不起来了", _pending_probation_state())

    state = result["case_state"]
    assert "recruitment_conditions_disclosed" not in state.facts
    assert "录用条件" in result["reply"]
    assert "换个更直接的问法" in result["reply"]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("一个月一万", 10000),
        ("每个月10000元", 10000),
        ("月薪1.2万", 12000),
        ("一万块一个月", 10000),
        ("税前工资一个月是12,500元", 12500),
        ("一万", 10000),
    ],
)
def test_contextual_salary_understands_spoken_monthly_amounts(answer: str, expected: float):
    state = CaseState(
        dispute_type="probation_termination",
        missing_facts=["monthly_salary"],
        pending_questions=["解除前十二个月的平均月工资大约是多少？"],
        pending_fact_ids=["monthly_salary"],
    )

    result = extract_labor_facts(answer, state)

    assert result.facts["monthly_salary"] == expected
    assert "monthly_salary" not in result.missing_facts


def test_engine_accepts_spoken_salary_and_moves_to_evidence_instead_of_repeating():
    state = CaseState(
        dispute_type="probation_termination",
        facts={
            "has_written_contract": True,
            "contract_term_months": 36,
            "probation_period_months": 6,
            "recruitment_conditions_disclosed": False,
            "assessment_evidence_exists": False,
            "termination_reason": "试用期表现不合格",
            "written_termination_notice": False,
        },
    )
    get_labor_model().prepare_state(state)
    state.pending_questions = ["解除前十二个月的平均月工资大约是多少？"]
    state.pending_fact_ids = ["monthly_salary"]

    result = LexPilotEngine().process("一个月一万", state)

    updated = result["case_state"]
    assert updated.facts["monthly_salary"] == 10000
    assert updated.current_action.name == "REQUEST_EVIDENCE"
    assert "平均月工资" not in result["reply"]
    assert "手头有没有" in result["reply"]


@pytest.mark.parametrize("answer", ["剩下的没有了", "没有", "现有材料就这些"])
def test_no_more_materials_is_remembered_and_never_reasked(answer: str, monkeypatch):
    provider = CountingProvider({})
    monkeypatch.setattr("backend.ai.semantic.get_ai_provider", lambda: provider)
    state = CaseState(
        dispute_type="probation_termination",
        facts={
            "employment_duration_months": 8,
            "has_written_contract": True,
            "contract_term_months": 12,
            "probation_period_months": 3,
            "recruitment_conditions_disclosed": False,
            "assessment_evidence_exists": False,
            "termination_reason": "试用期表现不合格",
            "written_termination_notice": False,
            "monthly_salary": 10000,
        },
    )
    get_labor_model().prepare_state(state)
    state.add_evidence("劳动合同")
    state.pending_evidence_requests = ["试用期条款", "解除通知"]

    result = LexPilotEngine().process(answer, state)
    updated = result["case_state"]

    assert updated.evidence_collection_exhausted is True
    assert updated.unavailable_evidence == ["试用期条款", "解除通知"]
    assert updated.pending_evidence_requests == []
    assert updated.current_action.name != "REQUEST_EVIDENCE"
    assert "不会再重复让你补同样的材料" in result["reply"]
    assert "手头有没有" not in result["reply"]
    assert provider.calls == 0
    assert updated.ai_calls_this_turn == 0


def test_repeated_salary_question_is_rephrased_instead_of_replayed():
    state = CaseState(dispute_type="probation_termination")
    get_labor_model().prepare_state(state)
    state.pending_questions = ["解除前十二个月的平均月工资大约是多少？"]
    state.pending_fact_ids = ["monthly_salary"]
    state.facts.update({key: True for key in state.key_facts if key != "monthly_salary"})
    get_labor_model().prepare_state(state)

    result = LexPilotEngine().process("这个数字我不确定", state)

    assert "刚才这个数字我没有识别准确" in result["reply"]
    assert "解除前十二个月的平均月工资大约是多少" not in result["reply"]
    assert "为判断案件，先补充一个关键事实" not in result["reply"]


def test_local_rule_answer_skips_ai_completely(monkeypatch):
    provider = CountingProvider({})
    monkeypatch.setattr("backend.ai.semantic.get_ai_provider", lambda: provider)
    state = CaseState(
        dispute_type="probation_termination",
        missing_facts=["monthly_salary"],
        pending_questions=["解除前十二个月的平均月工资大约是多少？"],
        pending_fact_ids=["monthly_salary"],
    )

    result = extract_labor_facts("一个月一万", state)

    assert result.facts["monthly_salary"] == 10000
    assert provider.calls == 0
    assert result.ai_calls_this_turn == 0


def test_unrecognized_answer_uses_one_combined_ai_call(monkeypatch):
    provider = CountingProvider({
        "dispute_type": "probation_termination",
        "facts": [{
            "fact_id": "monthly_salary",
            "value": 10000,
            "source_quote": "10k",
            "confidence": 0.98,
        }],
        "transition": "明白，你说的是平时每月到手的水平。",
    })
    monkeypatch.setattr("backend.ai.semantic.get_ai_provider", lambda: provider)
    state = CaseState(
        dispute_type="probation_termination",
        facts={
            "has_written_contract": True,
            "contract_term_months": 36,
            "probation_period_months": 6,
            "recruitment_conditions_disclosed": False,
            "assessment_evidence_exists": False,
            "termination_reason": "试用期表现不合格",
            "written_termination_notice": False,
        },
        pending_questions=["解除前十二个月的平均月工资大约是多少？"],
        pending_fact_ids=["monthly_salary"],
    )
    get_labor_model().prepare_state(state)

    result = LexPilotEngine().process("10k左右", state)

    updated = result["case_state"]
    assert updated.facts["monthly_salary"] == 10000
    assert provider.calls == 1
    assert provider.thinking_levels == ["low"]
    assert updated.ai_calls_this_turn == 1
    assert result["reply"].startswith("明白，你说的是平时每月到手的水平。")
