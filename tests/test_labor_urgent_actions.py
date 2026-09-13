"""Round-47: the labour specialist path computes and surfaces urgent actions."""

import pytest

from backend.workflow import LexPilotEngine


@pytest.mark.parametrize(
    'text',
    [
        '公司拖欠我工资，还把我打伤了，请给我方案。',
        '公司拖欠我工资，规定明天前提交仲裁材料，请给我方案。',
        '公司辞退我了，要求我3天内办理离职手续并答复，请给我方案。',
        '公司拖欠我工资，还威胁要打我，请给我方案。',
    ],
)
def test_labor_urgent_actions_are_recorded_and_shown(text):
    result = LexPilotEngine().process(text, None)
    state = result['case_state']
    assert state.consultation.urgent_actions
    assert '先处理紧急事项' in result['reply']


def test_labor_plain_case_has_no_urgent_action():
    result = LexPilotEngine().process('公司拖欠我工资，请给我方案。', None)
    state = result['case_state']
    assert not state.consultation.urgent_actions
    assert '先处理紧急事项' not in result['reply']
