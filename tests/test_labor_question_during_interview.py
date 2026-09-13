"""Round-54: a question asked during the labour interview gets an answer."""

import pytest

from backend.workflow import LexPilotEngine


def _run(*messages):
    engine = LexPilotEngine()
    state = None
    reply = ''
    for message in messages:
        result = engine.process(message, state)
        state = result['case_state']
        reply = result['reply']
    return state, reply


@pytest.mark.parametrize(
    'question',
    [
        '我需要准备什么材料？',
        '接下来我该走哪一步？',
        '公司说我自己离职的，我怎么回应？',
        '怎么去仲裁？需要什么手续？',
    ],
)
def test_question_is_answered_not_re_asked(question):
    _, reply = _run('公司拖欠我工资，请给我方案。', question)
    # The plan lists the steps; a bare re-ask would be a short single question.
    assert len(reply) > 120, reply
    assert '核对时间节点' in reply or '整理材料' in reply or '抗辩' in reply or '仲裁' in reply


def test_answering_still_records_the_fact():
    state, _ = _run('公司拖欠我工资，请给我方案。', '我在公司干了5年。')
    assert str(state.facts.get('employment_duration_months')) == '60.0'
