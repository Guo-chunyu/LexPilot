"""Round-49: a coordinating conjunction ends a negation's reach (urgent signals)."""

import pytest

from backend.legal_domain.consultation._spans import URGENT_SCOPE, has_asserted
from backend.legal_domain.consultation.intake import SAFETY_SIGNAL


@pytest.mark.parametrize(
    'text',
    [
        # The 不退 governs 押金 only; 打人 is a new predicate.
        '房东不退我押金还打人',
        '公司扣我工资还打我',
        '对方不还钱又打我',
    ],
)
def test_coordination_ends_negation(text):
    assert has_asserted(text, SAFETY_SIGNAL, policy=URGENT_SCOPE), text


@pytest.mark.parametrize(
    'text',
    [
        # The negation still governs the signal directly.
        '他没有把我打伤',
        '对方没有打我',
        '没有人威胁我',
    ],
)
def test_direct_negation_still_applies(text):
    assert not has_asserted(text, SAFETY_SIGNAL, policy=URGENT_SCOPE), text
