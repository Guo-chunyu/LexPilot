"""Round-28: colloquial approximate amounts ("8000多块") must be captured."""

import re

import pytest

from backend.legal_domain.consultation.intake import AMOUNT_PATTERN


@pytest.mark.parametrize(
    'text, expected',
    [
        # An approximator between the number and the unit is still an amount.
        ('朋友欠我8000多块', True),
        ('对方欠我3万多元', True),
        ('朋友欠我2万余元', True),
        ('同事欠我1万多块', True),
        ('朋友欠我3万元', True),
        ('欠我8000元', True),
        ('欠我5万', True),
        # Still not an amount: a bare number, or a number with no unit at all.
        ('对方欠我5000左右', False),
        ('欠我8千', False),
        ('请给我方案', False),
    ],
)
def test_amount_pattern_colloquial(text, expected):
    assert bool(re.search(AMOUNT_PATTERN, text)) == expected
