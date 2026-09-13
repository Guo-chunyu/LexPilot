"""Round-45: the party record keeps real names, not only a role signal."""

import pytest

from backend.legal_domain.consultation.intake import _party_answer_summary
from backend.legal_domain.consultation.perspective import client_perspective
from backend.legal_rl.state import CaseState


@pytest.mark.parametrize(
    'text, fragment',
    [
        ('我叫张三', '张三'),
        ('对方叫王五', '王五'),
        ('对方是我朋友李四', '李四'),
        ('我是公司老板', ''),
        ('我是出借人', ''),
        ('我是房东', ''),
    ],
)
def test_party_summary(text, fragment):
    out = _party_answer_summary(text)
    if fragment:
        assert fragment in out, out
    else:
        # A bare role label adds nothing over the role itself.
        assert out == '', out


def test_role_signal_survives_a_party_description():
    state = CaseState(case_type='debt')
    state.facts['parties'] = '本人：张三；对方：李四；欠我'
    assert client_perspective(state, '')['id'] == 'creditor'
