"""Round-56: a turn after the staged plan must still get the plan, not a refusal.

Reported from a real session: after the interview completed, answering the last
question ("已经结束了，是2025.9.10结束的") and the follow-up "那你还要啥信息"
both produced only "当前信息仍不足，系统不会提前输出确定性法律结论。"
"""

import pytest

from backend.workflow import LexPilotEngine

OPENING = (
    '公司拖欠我3个月工资，共18000元。我没有劳动合同，但有工资流水、工作群聊天和考勤截图。'
    '公司已经明确拒绝支付，请先给我方案。'
)
INTERVIEW = [
    '2026.8.11',
    '不好意思，刚才说错了是2025.8.11入职，然后中间又2个月',
    '大概5000吧',
    '暂时没有别的材料了',
    '已经结束了，是2025.9.10结束的',
]


def _run(*messages):
    engine = LexPilotEngine()
    state = None
    reply = ''
    for message in messages:
        result = engine.process(message, state)
        state = result['case_state']
        reply = result['reply']
    return state, reply


def test_end_date_answer_gets_the_report():
    state, reply = _run(OPENING, *INTERVIEW)
    assert state.facts['employment_end_date'] == '2025-09-10'
    assert state.final_report
    assert '阶段性行动方案' in reply
    assert '当前信息仍不足' not in reply


def test_fact_completeness_reaches_one_hundred():
    state, _ = _run(OPENING, *INTERVIEW)
    assert state.fact_completeness == 1.0


@pytest.mark.parametrize(
    'follow_up',
    ['那你还要啥信息', '好的，谢谢。', '公司还欠我加班费。'],
)
def test_follow_up_turns_still_get_the_report(follow_up):
    _, reply = _run(OPENING, *INTERVIEW, follow_up)
    assert '阶段性行动方案' in reply
    assert '当前信息仍不足' not in reply


def test_mentioning_a_new_material_is_not_refused():
    # This turn takes the material-review branch rather than the report branch;
    # either way it must be a substantive answer, never the bare refusal.
    _, reply = _run(OPENING, *INTERVIEW, '我后来找到了社保记录，可以补充。')
    assert len(reply) > 120, reply
    assert '当前信息仍不足' not in reply
