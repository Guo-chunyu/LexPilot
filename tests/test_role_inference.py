"""Round-44: the debtor role is inferred from any amount unit, not only "钱"."""

import re

import pytest

from backend.legal_domain.consultation.perspective import ROLE_PATTERNS


@pytest.mark.parametrize(
    'text',
    [
        '我欠他3万元',
        '我欠他5万',
        '我欠他3万块钱',
        '我欠他一笔钱',
        '我欠他钱',
    ],
)
def test_debtor_role_is_detected(text):
    assert re.search(ROLE_PATTERNS['debtor'][1], text), text


@pytest.mark.parametrize(
    'text',
    [
        # The user is the creditor, not the debtor.
        '他欠我3万元',
        '朋友欠我3万元',
        # "我欠考虑" is not a debt.
        '我欠考虑',
    ],
)
def test_non_debtor_is_not_matched(text):
    assert not re.search(ROLE_PATTERNS['debtor'][1], text), text


@pytest.mark.parametrize('text', ['他欠我3万元', '朋友欠我3万元'])
def test_creditor_role_is_detected(text):
    assert re.search(ROLE_PATTERNS['creditor'][1], text), text


@pytest.mark.parametrize(
    'text',
    [
        # Round-46: the counterparty wrote the IOU to the user.
        '对方给我写了欠条',
        '他给我打了欠条',
        '对方出具了欠条',
    ],
)
def test_counterparty_written_iou_is_creditor(text):
    assert re.search(ROLE_PATTERNS['creditor'][1], text), text


@pytest.mark.parametrize(
    'text',
    [
        # The user is the writer → not a creditor signal.
        '给他写了欠条',
        '我给他打了欠条',
    ],
)
def test_user_written_iou_is_not_creditor(text):
    assert not re.search(ROLE_PATTERNS['creditor'][1], text), text
