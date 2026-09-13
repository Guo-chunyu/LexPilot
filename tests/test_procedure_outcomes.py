"""Round-34: failed mediation / refused procedure is a procedural outcome."""

import pytest

from backend.legal_domain.consultation.intake import ingest_text
from backend.legal_rl.state import CaseState


@pytest.mark.parametrize(
    'text',
    [
        '法院说调解不成让我等判决',
        '我申请调解被拒绝了',
        '我和对方协商不成',
        '我向消协投诉被驳回了',
    ],
)
def test_procedural_outcome_is_recorded(text):
    state = CaseState(case_type='debt')
    ingest_text(text, state)
    assert state.facts.get('procedure'), text
