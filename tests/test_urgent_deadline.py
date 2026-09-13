"""Round-36: spoken legal deadlines ("15天内上诉") trigger the urgent action."""

import pytest

from backend.legal_domain.consultation.intake import _has_asserted_urgent_deadline


@pytest.mark.parametrize(
    'text',
    [
        '法院判决下来了，要求我15天内上诉',
        '法院要求我10天内提交材料',
        '行政机关要求我15天内申请复议',
        '法院要求我10日内答辩',
        '法院通知我今天去开庭',
    ],
)
def test_urgent_deadline_is_detected(text):
    assert _has_asserted_urgent_deadline(text), text


@pytest.mark.parametrize(
    'text',
    [
        '朋友欠我3万元',
        '对方要求我10天内还钱',
        '已经过去半年了，早就超过期限',
    ],
)
def test_non_deadline_is_not_urgent(text):
    assert not _has_asserted_urgent_deadline(text), text
