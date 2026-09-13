"""Round-31: a lost / misplaced material is recorded as unobtainable."""

import pytest

from backend.legal_domain.consultation.intake import _evidence_mention

SIBLINGS = ('转账记录', '催款记录')


@pytest.mark.parametrize(
    'text',
    [
        '对方欠我3万元，借条弄丢了',
        '对方欠我3万元，借条遗失了',
        '对方欠我3万元，借条丢失了',
        '对方欠我3万元，借条丢了',
        '对方欠我3万元，借条找不到了',
        '对方欠我3万元，借条在对方手里，我拿不到',
        '对方欠我3万元，没有借条',
    ],
)
def test_lost_material_is_unavailable(text):
    mentioned, unavailable = _evidence_mention(text, '借条', SIBLINGS)
    assert mentioned, text
    assert unavailable, text


@pytest.mark.parametrize(
    'text',
    [
        '对方欠我3万元，有借条',
        '对方欠我3万元，借条还在',
    ],
)
def test_held_material_is_available(text):
    mentioned, unavailable = _evidence_mention(text, '借条', SIBLINGS)
    assert mentioned, text
    assert not unavailable, text
