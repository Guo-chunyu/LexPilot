"""Round-43: an imminent enforcement measure triggers the enforcement urgent action."""

import pytest

from backend.legal_domain.consultation.intake import (
    ENFORCEMENT_SIGNAL,
    ENFORCEMENT_URGENT_ACTION,
    _has_asserted_signal,
)
from backend.legal_rl.state import CaseState
from backend.legal_domain.consultation.intake import urgent_actions


@pytest.mark.parametrize(
    'text',
    [
        '法院要来查封我的房子',
        '法院冻结了我的银行账户',
        '法院要强制执行让我搬走',
        '我的房子要被法院拍卖了',
        '法院要我下周腾退房屋',
        '执行局要扣划我的工资卡',
    ],
)
def test_enforcement_signal_is_detected(text):
    assert _has_asserted_signal(text, ENFORCEMENT_SIGNAL), text


@pytest.mark.parametrize(
    'text',
    [
        # Not urgent for the user: they are the one seeking enforcement.
        '我打算申请强制执行对方',
        '法院判决下来了，要求我15天内上诉',
        '朋友欠我3万元',
    ],
)
def test_non_enforcement_is_not_detected(text):
    assert not _has_asserted_signal(text, ENFORCEMENT_SIGNAL), text


def test_enforcement_urgency_reaches_state():
    state = CaseState(case_type='general')
    actions = urgent_actions('法院要来查封我的房子，请给我方案。', state)
    assert ENFORCEMENT_URGENT_ACTION in actions
