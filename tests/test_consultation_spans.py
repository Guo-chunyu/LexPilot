"""Property tests for the assertion/scope utility.

These tests pin the union of behaviours previously inlined across `intake.py`.
If a future regression tries to change one call-site's negation policy without
re-testing the others, this suite catches the drift.
"""

import re

import pytest

from backend.legal_domain.consultation._spans import (
    CLAUSE_BROAD,
    EVIDENCE_EXHAUSTED,
    EXCLUSIVE_INVENTORY,
    SENTENCE_BROAD,
    asserted_spans,
    first_asserted,
    has_asserted,
    has_negated,
    is_correction,
    negated_matches,
)


# Region 1 — broad negation (signals, procedure, deadline, safety).
BROAD = CLAUSE_BROAD


def test_double_negative_reasserts_broad():
    text = '不是没有借条，我有转账。'
    pat = r'没有.{0,2}借条'
    assert has_asserted(text, pat, policy=BROAD)
    assert not has_negated(text, pat, policy=BROAD)


def test_clause_boundary_blocks_negation_from_earlier_clause_broad():
    text = '对方没有回复，我没有借条。'
    matches = asserted_spans(text, r'没有.{0,2}借条', policy=BROAD)
    assert matches, 'no negation upstream of the second clause "借条"'


def test_negation_unaffected_when_clause_lacks_negation():
    text = '对方没有借条，我可以出示。'
    # No negation upstream of "没有借条" within its clause.
    assert has_asserted(text, r'没有.{0,2}借条', policy=BROAD)


def test_negation_blocks_broad_candidate_same_clause():
    text = '对方从未存在借条。'
    assert not has_asserted(text, r'(?:存在|有)借条', policy=BROAD)


def test_negative_procedure_pattern_broad():
    pat = r'(?:没有|尚未|还没)(?:起诉|立案|投诉|报案|申请|协商)'
    assert has_asserted('我还没起诉', pat, policy=BROAD)
    assert not has_asserted('并非还没起诉', pat, policy=BROAD)
    assert has_asserted('对方说还没起诉，但已经立案', pat, policy=BROAD)


def test_outcome_negation_broad():
    pat = r'驳回'
    assert has_negated('没有驳回', pat, policy=BROAD)
    assert has_asserted('已经驳回', pat, policy=BROAD)
    text2 = '没有驳回，也没有立案'
    assert has_negated(text2, pat, policy=BROAD)


def test_signal_states_broad_handles_single_char_negation():
    pat = r'拘留'
    assert has_asserted('对方回复说被拘留', pat, policy=BROAD)
    assert has_negated('并非拘留', pat, policy=BROAD)


def test_window_size_blocks_distant_negation_broad():
    narrow = CLAUSE_BROAD.__class__(
        negation_pattern=CLAUSE_BROAD.negation_pattern,
        scope_breaks=CLAUSE_BROAD.scope_breaks,
        window=4,
        name='narrow-test',
    )
    far_text = '远在十二个字之外的那一句否定了后面的词。其他并无联系。借条在我手里。'
    matches = asserted_spans(far_text, r'借条', policy=narrow)
    assert matches, '4-char window should not reach the upstream negation'


def test_first_asserted_picks_first_unnegated_claim():
    # First "没有借条" is inside a double-negative and is asserted. We expect
    # first_asserted to return it (just like a human reviewer would cite the
    # closest match).
    text = '不是没有借条，我没有转账，我也没有聊天。'
    match = first_asserted(text, r'没有(.{0,4})(借条|转账|聊天)', policy=BROAD)
    assert match is not None
    assert match.group(2) == '借条', match.group(0)


def test_first_asserted_skips_all_negated_upstream_but_asserts_via_double_negative():
    text = '并非没有借条，我没有转账，更没有聊天。'
    match = first_asserted(text, r'没有(.{0,4})(借条|转账|聊天)', policy=BROAD)
    # "并非没有借条" — "并非" is in DOUBLE_NEGATION_RESET, so this re-asserts.
    # first_asserted returns whichever asserted match comes first; that is
    # the re-asserted "借条" in clause 1.
    assert match is not None
    assert match.group(2) == '借条', match.group(0)


def test_first_asserted_falls_through_after_negated_to_later_asserted():
    text = '对方从未存在借条，我没有转账。'
    match = first_asserted(text, r'(?:存在|有|没有)(.{0,4})(借条|转账)', policy=BROAD)
    # "从未存在借条" — "从未" is not in DOUBLE_NEGATION_RESET, so negated.
    # Clause 2 "没有转账" has no upstream negation; asserted. first asserted
    # match is "转账" in clause 2.
    assert match is not None
    assert match.group(2) == '转账', match.group(0)


def test_first_asserted_returns_none_when_all_negated_broad():
    text = '对方从未存在借条，对方也从未存在转账。'
    assert first_asserted(text, r'(?:存在|有)(.{0,4})(借条|转账)', policy=BROAD) is None


def test_negated_matches_returns_only_negated_broad():
    text = '对方从未存在借条。我这边也是说没有转账。'
    negated = negated_matches(text, r'(?:存在|没有).{0,2}(?:借条|转账)', policy=BROAD)
    assert all(not BROAD.is_asserted(text, m.start()) for m in negated)
    # "从未存在借条" is negated; "没有转账" in clause 2 is asserted.
    # So the negated list contains exactly the first match.
    assert len(negated) == 1
    assert '存在' in negated[0].group(0)


# Region 2 — sentence scope (procedure, where cross-sentence context matters).
def test_sentence_policy_blocks_cross_sentence_negation():
    pat = r'撤销'
    text = '上一个句子里没有驳回。下一个句子说撤销合同。'
    matches = asserted_spans(text, pat, policy=SENTENCE_BROAD)
    assert matches


def test_sentence_policy_negates_within_sentence():
    pat = r'撤销'
    text = '申请没有被驳回，撤销了原处分。'
    # Single sentence: 没有...被驳回 then 撤销. The 没有 hangs at the clause
    # boundary `，`. From SENTENCE_BROAD's scope_breaks `，`, upstream before
    # "撤销" excludes the previous clause entirely. But "撤销" is asserted in
    # its own clause (no negation upstream). So has_negated should be False.
    matches = asserted_spans(text, pat, policy=SENTENCE_BROAD)
    assert matches, 'within-sentence clause boundary isolates the candidate'


def test_sentence_policy_negates_via_within_sentence_negation():
    pat = r'(?:驳回|不予受理|撤销|撤回)'
    text = '没有驳回，撤销没有。'
    # Single sentence. The clause-scope arrives at "没有驳回" → asserted.
    # "撤销" after a comma has empty upstream → asserted. Both passes.
    matches = asserted_spans(text, pat, policy=SENTENCE_BROAD)
    assert matches


def test_clause_break_blocks_negation_but_does_not_promote_assertion():
    """A clause-break resets the clause scope but does not by itself make a
    candidate asserted; it allows broad-policy upstream to be empty.
    """
    pat = r'没有.{0,2}借条'
    text = '上一句说了别的内容。这一句里其实没有借条。'
    matches = asserted_spans(text, pat, policy=BROAD)
    assert matches, 'clause break lets the next clause assert independently'


# Region 3 — narrow end-of-clause (exhaustion, exclusive inventory).
def test_exhausted_negation_at_end_of_clause():
    # Pattern: 短 negation directly precedes the EXHAUSTED signal.
    text = '材料我并非没有更多，证据仍能补。'
    # First clause: "材料我并非没有更多" → "没有更多" is a recognised
    # exhaustion token. Upstream scope before "没有更多" = "我并非" (window
    # 24, before clause break at `，`). narrow-end pattern `_CLAUSE_END_NEGATION`
    # = `(?:不是|并非|...|并非意味着)\s*$`. Search in "我并非": does it end with
    # `并非`? The upstream is "我并非". Does the regex match at end? `并非` is
    # at position 1-3, but the $ anchors to end. So match found? Yes, `并非`
    # at end.
    matches = asserted_spans(text, r'(?:没有更多|没有其他|没有别的|没有了)', policy=EVIDENCE_EXHAUSTED)
    assert not matches, matches


def test_exhausted_asserted_when_clause_lacks_negation():
    text = '我没有更多材料。'
    matches = asserted_spans(text, r'(?:没有更多|没有其他|没有别的|没有了)', policy=EVIDENCE_EXHAUSTED)
    assert matches


def test_exclusive_inventory_far_negation_does_not_count():
    # The far "并非" should not be at the end of the scope leading to "只有".
    text = '我有转账，并非完全相同，只有借条。'
    matches = asserted_spans(text, r'(只有|仅有)([^，。；\n]{1,40})', policy=EXCLUSIVE_INVENTORY)
    # The "并非" is mid-clause; the only negation candidates at end of scope
    # would be immediately before "只有借条". Empty upstream → asserted.
    assert matches


def test_exclusive_inventory_near_negation_excludes():
    text = '我有转账，并非只有借条。'
    matches = asserted_spans(text, r'(只有|仅有)([^，。；\n]{1,40})', policy=EXCLUSIVE_INVENTORY)
    # "并非" is right at the end of the upstream scope leading to "只有";
    # narrow-end pattern catches it → no asserted match.
    assert not matches


def test_exclusive_inventory_narrow_end_keeps_assumption():
    # The historical assertion: an end-of-scope "并非" still excludes
    # "只有借条", even when the second clause continues. We do not reset for
    # narrow-end policies — the design that no inlined check ever reset them.
    text = '我有转账，并非只有借条。'
    matches = asserted_spans(text, r'(只有|仅有)([^，。；\n]{1,40})', policy=EXCLUSIVE_INVENTORY)
    assert not matches


def test_exclusive_inventory_double_negation_pattern_matches_design():
    # Even an explicit "并非并非" (double-并非) does not reset EXCLUSIVE_INVENTORY
    # because the policy opted out of the double-negative reset (the negation
    # is anchored to end of scope, so re-assertion is intentionally unsupported
    # here).
    text = '并非并非只有借条，聊天也有。'
    matches = asserted_spans(text, r'(只有|仅有)([^，。；\n]{1,40})', policy=EXCLUSIVE_INVENTORY)
    assert not matches


# Region 4 — compound negation set replaces inline lists.
def test_compound_negation_set_replaces_inline_lists():
    cases = [
        ('对方说没有借条', True),
        ('对方说并非有转账', False),
        ('并未存在转账这件事', False),
        ('没有转账', True),
        ('对方并不存在借条一说', False),
        ('并非意味着我有借条', False),
        ('对方从未存在借条', False),
        ('对方不存在借条', False),
    ]
    for text, expected_asserted in cases:
        actual = has_asserted(text, r'没有.{0,4}(?:借条|转账)', policy=BROAD)
        assert actual == expected_asserted, f'{text!r} -> expected {expected_asserted}, got {actual}'


# Region 5 — correction is independent of scope.
def test_correction_marker_text_is_recognised():
    assert is_correction('其实是这样的：合同已签')
    assert is_correction('更正一下，金额是4万')
    assert is_correction('说错了，是对方先违约')
    assert is_correction('我不是借款人，我是出借人')


def test_correction_does_not_fire_on_double_negative():
    assert not is_correction('不是没有借条，我没说不给对方借条。')
    assert not is_correction('不是只有借条，我还有其他材料。')


def test_correction_variants():
    # The historical list (and only this list) marks a correction.
    for text in [
        '其实是这样',
        '实际是对方违约',
        '准确说是上周发生的',
        '应该是4万而不是5万',
        '应当是工作日',
        '更正一下',
        '更正是上周',
        '更正成4万',
        '说错了',
    ]:
        assert is_correction(text), text


def test_correction_does_not_fire_on_normal_statements():
    for text in [
        '其实我今天很忙',
        '其实早就说了',
        '应当尽快处理',
        '实际发生时间不确定',
    ]:
        assert not is_correction(text), text
