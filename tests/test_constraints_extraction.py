"""Round-53: colloquial time / money constraints are captured."""

import pytest

from backend.legal_domain.consultation.intake import ingest_text
from backend.legal_rl.state import CaseState


@pytest.mark.parametrize(
    'text',
    [
        '我只有3个月时间处理',
        '我只剩两周的时间',
        '我时间不多',
        '我时间紧',
        '我请不起律师',
        '我付不起诉讼费',
        '我承担不起这个费用',
        '我没预算打官司',
    ],
)
def test_constraint_is_captured(text):
    state = CaseState(case_type='debt')
    ingest_text(text, state)
    assert state.facts.get('constraints'), text


@pytest.mark.parametrize('text', ['朋友欠我3万元', '我有时间处理'])
def test_non_constraint_is_not_captured(text):
    state = CaseState(case_type='debt')
    ingest_text(text, state)
    assert not state.facts.get('constraints'), state.facts.get('constraints')
