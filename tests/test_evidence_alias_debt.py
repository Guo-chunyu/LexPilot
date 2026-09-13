"""Round-37: 欠条 is a debt instrument alongside 借条 / 借据."""

import pytest

from backend.legal_domain.consultation.intake import _evidence_mention

SIBLINGS = ('转账记录', '催款记录')


@pytest.mark.parametrize(
    'text',
    [
        '有欠条',
        '对方给我写了欠条',
        '有借条',
        '有借据',
    ],
)
def test_debt_instrument_is_recognized(text):
    mentioned, unavailable = _evidence_mention(text, '借条', SIBLINGS)
    assert mentioned, text
    assert not unavailable, text
