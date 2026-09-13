"""Round-33: spoken relative dates are captured as event_time."""

import re

import pytest

from backend.legal_domain.consultation.intake import DATE_PATTERN, ingest_text
from backend.legal_rl.state import CaseState


@pytest.mark.parametrize(
    'text',
    [
        '上周我们签了合同',
        '本周对方拒绝发货',
        '这个月他一直没还钱',
        '前几天对方把我的车撞了',
        '3天前对方把货拉走了',
        '3个月前借给朋友2万元',
        # Round-55: the year before last.
        '朋友前年借我3万元',
        '朋友大前年借我3万元',
    ],
)
def test_relative_date_is_extracted(text):
    state = CaseState(case_type='debt')
    ingest_text(text, state)
    assert state.facts.get('event_time'), text


@pytest.mark.parametrize('text', ['上周', '这个月', '前几天', '3天前', '3个月前', '前年', '大前年'])
def test_relative_date_matches_pattern(text):
    assert re.search(DATE_PATTERN, text)


def test_future_relative_date_is_not_event_time():
    state = CaseState(case_type='debt')
    ingest_text('对方说下个月才还我3万元', state)
    assert not state.facts.get('event_time'), state.facts.get('event_time')
