"""Round-32: the user's own stated goal must be captured."""

import pytest

from backend.legal_domain.consultation.intake import ingest_text
from backend.legal_rl.state import CaseState


@pytest.mark.parametrize(
    'text',
    [
        '我要他公开道歉并还钱',
        '我要他把钱还给我',
        '我要求他继续履行合同',
        '我要求他赔偿损失',
        '我要他修好',
        '商家卖假货，我要求退货退款',
        '我希望对方尽快还钱',
        # Round-41: further contract / tort remedies.
        '我要求他支付违约金',
        '我要求他停止侵权',
        '我要求他双倍返还定金',
        '我要他退我定金',
        # Round-50: plain "我想…" prefix.
        '我想解除合同',
        '我想退还定金',
        '我想让他赔偿损失',
    ],
)
def test_user_goal_phrasings_are_captured(text):
    state = CaseState(case_type='debt')
    ingest_text(text, state)
    assert state.facts.get('goal'), text


@pytest.mark.parametrize(
    'text',
    [
        # The other party's demand is not the user's goal.
        '对方要求我赔偿',
        '公司要求我10天内还',
    ],
)
def test_counterparty_demand_is_not_recorded_as_goal(text):
    state = CaseState(case_type='debt')
    ingest_text(text, state)
    assert not state.facts.get('goal'), state.facts.get('goal')
