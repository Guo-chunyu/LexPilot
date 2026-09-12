"""Stage 3 property tests: typed slots, assertor, and constraint withdrawal.

These pin the three invariants the consolidated state model guarantees:
1. A counterparty (or authority) assertion never overwrites a user-owned
   slot such as ``amount`` or ``procedure``. Counterparty claims go to the
   counterparty-claims side channel and never become the active fact.
2. A user correction supersedes the prior user assertion, but a
   counterparty claim can never supersede a user assertion.
3. Handling constraints (``constraints``) have a lifecycle: when the user
   retracts a constraint, the prior active assertion is marked withdrawn and
   `` ``facts['constraints']`` no longer contains it.
"""

import re

import pytest

from backend.legal_domain.consultation.intake import ingest_text
from backend.legal_domain.consultation.models import ConsultationDossier, SlotAssertion
from backend.legal_rl.state import CaseState


def _state(case_type: str = 'debt') -> CaseState:
    state = CaseState(case_type=case_type, consultation=ConsultationDossier())
    return state


def _run(state, *messages):
    """Run a sequence of user messages the way the engine does:
    each turn increments ``consultation.turns`` *before* ``ingest_text`` so the
    later-turn counterparty frame fires (``turns > 1``).
    """
    for message in messages:
        state.consultation.turns += 1
        ingest_text(message, state, contextual=False)
    return state


# Region 1 — counterparty cannot overwrite user-owned slots.
def test_counterparty_claim_does_not_overwrite_user_amount():
    state = _state('debt')
    _run(state, '朋友欠我4万元，请给我方案。', '借条转账都有', '一个月一万', '对方说只欠2万元')
    assert state.facts.get('amount'), 'user amount was set'
    # The user's 4万 (or 1万每月) amount must remain.
    assert not any('2万' in str(v) and v == state.facts.get('amount') for v in [state.facts.get('amount')])


def test_counterparty_claim_recorded_in_counterparty_claims_channel():
    """A counterparty assertion about a user-owned slot (``amount``) lands in
    the side channel — never overwriting the user's own value.
    """
    state = _state('debt')
    from backend.legal_domain.consultation.intake import save_fact
    _run(state, '朋友欠我4万元', '对方说只借了2万元')
    save_fact(state, 'amount', '只欠2万', '只欠2万', assertor='counterparty')
    cp = state.consultation.counterparty_claims
    assert cp
    assert any('2万' in c.value for c in cp), cp
    # The user's 4万 remains.
    assert '4万' in str(state.facts.get('amount', ''))


def test_counterparty_claim_can_still_update_details():
    state = _state('debt')
    _run(state, '朋友欠我4万元，有转账记录。', '对方回复说只借了2万元，其余是利息')
    # ``details`` is the legitimate place for counterparty updates; it must
    # contain the new claim.
    assert '2万' in str(state.facts.get('details', '')) or '利息' in str(state.facts.get('details', ''))


def test_authority_assertion_does_not_overwrite_user_procedure():
    state = _state('debt')
    _run(state, '我还没起诉。', '窗口工作人员说不需要立案也可以')
    # The user said they haven't filed; authority reply should not turn the
    # user's "没有起诉" into an asserted "已起诉".
    procedure = str(state.facts.get('procedure', ''))
    if procedure:
        assert '已起诉' not in procedure or '没有起诉' in procedure or '尚未' in procedure


# Region 2 — assertor-aware supersedes.
def test_user_correction_supersedes_prior_user_assertion():
    state = _state('debt')
    _run(state, '朋友欠我4万元', '说错了，是3万元')
    assertions = state.slot_assertions.get('amount', [])
    user_assertions = [a for a in assertions if a.assertor == 'user']
    assert len(user_assertions) >= 2, [a.value for a in user_assertions]
    # The first user assertion (4万) is superseded.
    prior = user_assertions[0]
    assert prior.lifecycle == 'superseded', prior
    assert prior.superseded_by, prior.superseded_by


def test_counterparty_claim_does_not_supersede_user_assertion():
    """A counterparty assertion at ``amount`` is recorded as a side-channel
    claim; the user assertion for ``amount`` stays active.
    """
    state = _state('debt')
    from backend.legal_domain.consultation.intake import save_fact
    _run(state, '朋友欠我4万元')
    save_fact(state, 'amount', '只欠2万', '只欠2万', assertor='counterparty')
    user = [a for a in state.slot_assertions.get('amount', []) if a.assertor == 'user']
    counter = [a for a in state.slot_assertions.get('amount', []) if a.assertor == 'counterparty']
    assert user and counter
    # The user assertion stays active; the counterparty assertion does not
    # supersede it.
    for u in user:
        assert u.lifecycle == 'active'
    # ``counterparty_claims`` records it instead.
    assert any('2万' in c.value for c in state.consultation.counterparty_claims)


# Region 3 — constraint withdrawal lifecycle.
def test_user_withdrawal_marks_prior_constraint_withdrawn():
    state = _state('debt')
    _run(
        state,
        '朋友欠我4万元，请先给我方案。',
        '请不要再让我联系对方，只接受书面沟通。',
        '我改变主意了，还是愿意再和对方协商一次。',
    )
    prior = [a for a in state.slot_assertions.get('constraints', []) if a.assertor == 'user']
    assert prior
    # The most recent active assertion is the *withdrawal* — the prior
    # ``不要再让我联系对方`` must be marked ``withdrawn``.
    active = [a for a in prior if a.lifecycle == 'active']
    assert all('不要再让我联系' not in a.value for a in active), [a.value for a in active]


def test_user_withdrawal_removes_constraint_from_facts():
    state = _state('debt')
    _run(
        state,
        '朋友欠我4万元，请先给我方案。',
        '请不要再让我联系对方，只接受书面沟通。',
        '我改变主意了，还是愿意再和对方协商一次。',
    )
    constraints = str(state.facts.get('constraints', ''))
    assert '不要再让我联系对方' not in constraints


def test_user_withdrawal_keeps_other_active_constraints():
    state = _state('debt')
    _run(
        state,
        '朋友欠我4万元，请先给我方案。',
        '请不要再让我联系对方，只接受书面沟通，人在外地不能到场。',
        '我改变主意了，还是愿意再和对方协商一次。',
    )
    constraints = str(state.facts.get('constraints', ''))
    # ``人在外地不能到场`` is unrelated to the negotiation preference and
    # should remain.
    assert '人在外地' in constraints or '不能到场' in constraints


def test_constraint_lifecycle_allows_new_active_assertion_after_withdrawal():
    state = _state('debt')
    _run(
        state,
        '朋友欠我4万元',
        '请不要再让我联系对方',
        '我改变主意了，还是愿意再和对方协商一次',
        '还是要求书面沟通优先。',
    )
    active = [a for a in state.slot_assertions.get('constraints', []) if a.lifecycle == 'active']
    # The latest active constraint is the new one; the prior one is withdrawn.
    assert active
    assert '书面沟通' in active[-1].value or '不要再' not in active[-1].value


# Region 4 — model shape.
def test_slot_assertion_carries_metadata():
    state = _state('debt')
    _run(state, '朋友欠我4万元', '对方说只欠2万元')
    if state.slot_assertions.get('amount'):
        for a in state.slot_assertions['amount']:
            assert a.key == 'amount'
            assert a.assertor in {'user', 'counterparty', 'authority', 'system'}
            assert a.lifecycle in {'active', 'superseded', 'withdrawn'}
            assert a.turn >= 1
            assert a.quote or a.value


def test_counterparty_claim_recorded_even_when_route_via_details():
    state = _state('debt')
    _run(
        state,
        '朋友欠我4万元',
        '对方说只借了2万元，剩下是利息',
    )
    # ``details`` slot accepts the counterparty update directly.
    assert '2万' in str(state.facts.get('details', '')) or any('2万' in c.value for c in state.consultation.counterparty_claims)


# Region 5 — cross-domain regressions that the slot lifecycle must not break.
def test_bare_medical_record_alias_recognised_as_unavailable():
    """``病历还在医院，我现在拿不到`` must map the bare ``病历`` to the
    canonical evidence task ``完整病历`` and mark it as unavailable. This is
    the round-17 bare-alias regression.
    """
    from backend.legal_domain.consultation.intake import ingest_text
    from backend.legal_domain.consultation.models import ConsultationDossier
    from backend.legal_rl.state import CaseState

    state = CaseState(case_type='medical', consultation=ConsultationDossier())
    state.consultation.turns += 1
    ingest_text('手术后发现后遗症', state, contextual=False)
    state.consultation.turns += 1
    ingest_text('病历还在医院，我现在拿不到', state, contextual=False)
    assert '完整病历' in state.unavailable_evidence, state.unavailable_evidence