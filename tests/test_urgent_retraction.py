"""Round-48: an urgent action can be withdrawn once the danger is over."""

import pytest

from backend.workflow import LexPilotEngine


def _run(*messages):
    engine = LexPilotEngine()
    state = None
    for message in messages:
        state = engine.process(message, state)['case_state']
    return state


@pytest.mark.parametrize(
    'first, second',
    [
        ('对方威胁要打我，请给我方案。', '现在没事了，他不会再打我了。'),
        ('法院要来查封我的房子，请给我方案。', '法院没有查封我的房子，事情已经解决了。'),
        ('法院要求我明天前提交材料，请给我方案。', '法院说没有期限要求，不着急。'),
    ],
)
def test_urgent_action_is_withdrawn(first, second):
    assert _run(first).consultation.urgent_actions
    assert not _run(first, second).consultation.urgent_actions


@pytest.mark.parametrize(
    'first, second',
    [
        ('对方威胁要打我，请给我方案。', '他现在还在打我。'),
        ('法院要来查封我的房子，请给我方案。', '还没来，法院说要查封。'),
    ],
)
def test_urgent_action_stays_while_ongoing(first, second):
    assert _run(first, second).consultation.urgent_actions
