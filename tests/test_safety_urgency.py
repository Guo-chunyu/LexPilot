"""Round-42: direct personal-safety phrasings trigger the safety urgent action."""

import pytest

from backend.legal_domain.consultation.intake import SAFETY_SIGNAL, _has_asserted_signal


@pytest.mark.parametrize(
    'text',
    [
        '对方威胁要打我',
        '我被对方打了',
        '我老公打我',
        '对方说要到我家里来闹',
        '对方一直骚扰我',
        '我老公打我，我身上有伤',
        '对方一直跟踪我',
        '他持刀威胁我',
        # Round-52: a bare personal threat.
        '他威胁我',
        '对方一直恐吓我',
    ],
)
def test_safety_signal_is_detected(text):
    assert _has_asserted_signal(text, SAFETY_SIGNAL), text


@pytest.mark.parametrize(
    'text',
    [
        # Not personal safety: calling someone / a figurative "打击".
        '我给对方打了电话催款',
        '我明天给他打电话',
        '公司被打击后裁员',
        '朋友欠我3万元',
        # A legal threat is not a safety event.
        '他威胁我要起诉',
        '对方威胁我去告我',
    ],
)
def test_non_safety_is_not_detected(text):
    assert not _has_asserted_signal(text, SAFETY_SIGNAL), text
