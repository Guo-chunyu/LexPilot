"""The wording layer must vary without ever changing what is being said."""

from backend.legal_domain.consultation.wording import (
    FACT_LEAD_POOLS,
    GENERIC_LEAD_POOL,
    REPHRASE_POOLS,
    WordingComposer,
    pick_variant,
)
from backend.legal_rl.state import CaseState
from backend.workflow import LexPilotEngine


def test_pick_variant_skips_recently_used_entries():
    pool = ('甲', '乙', '丙')
    assert pick_variant(pool, ['甲'], 0) == '乙'
    assert pick_variant(pool, ['甲', '乙'], 0) == '丙'


def test_pick_variant_falls_back_when_everything_is_recent():
    pool = ('甲', '乙')
    assert pick_variant(pool, ['甲', '乙'], 1) == '乙'


def test_every_lead_pool_offers_real_variation():
    for name, pool in [*FACT_LEAD_POOLS.items(), *REPHRASE_POOLS.items()]:
        assert len(pool) >= 3, name
        assert len(set(pool)) == len(pool), name
    assert len(GENERIC_LEAD_POOL) >= 8


def test_generic_lead_rotates_instead_of_repeating():
    dossier = CaseState().consultation
    leads = []
    for turn in range(1, 7):
        dossier.turns = turn
        leads.append(WordingComposer(dossier).generic_lead())
    assert len(set(leads)) >= 4


def test_composer_never_repeats_a_variant_back_to_back():
    dossier = CaseState().consultation
    previous = None
    for turn in range(1, 10):
        dossier.turns = turn
        current = WordingComposer(dossier).generic_lead()
        assert current != previous
        previous = current


def test_wording_memory_survives_serialization():
    state = CaseState()
    state.consultation.turns = 1
    WordingComposer(state.consultation).generic_lead()
    assert state.consultation.wording_recent

    restored = CaseState.from_value(state.public_dict())
    assert restored.consultation.wording_recent == state.consultation.wording_recent
    # The restored session must keep avoiding what it already said.
    assert WordingComposer(restored.consultation).generic_lead() not in (
        state.consultation.wording_recent
    )


LABOR_INTERVIEW = [
    '我在公司工作8个月，领导说我试用期表现不合格，明天不用来了，也没有给赔偿。',
    '签过书面劳动合同。',
    '试用期写的是六个月。',
    '入职时没有明确说过录用条件。',
    '公司没有给我看过考核标准。',
]


def test_real_interview_does_not_reuse_the_same_lead_every_turn():
    engine = LexPilotEngine()
    state = None
    replies = []
    for message in LABOR_INTERVIEW:
        result = engine.process(message, state)
        state = result['case_state']
        replies.append(result['reply'])
    leads = [reply[:12] for reply in replies[1:]]
    assert len(set(leads)) >= 2


def test_wording_choice_does_not_change_the_asked_question():
    """Same case, same turn count: only the surrounding copy may differ."""
    def run():
        engine = LexPilotEngine()
        state = None
        for message in LABOR_INTERVIEW[:2]:
            result = engine.process(message, state)
            state = result['case_state']
        return state.pending_questions

    assert run() == run()
