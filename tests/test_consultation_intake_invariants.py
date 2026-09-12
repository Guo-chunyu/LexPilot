"""Stage 2 invariants: the assertion/negation scope utility is the source of truth.

The previous ``intake.py`` repeated the same inline scope/negation checks in six
places; one spelling change fixed one symptom and left the others untouched.
After consolidating into ``backend.legal_domain.consultation._spans``, the
*absence* of those repetitions is itself an invariant worth pinning.
"""

import re
from pathlib import Path

import pytest


INTAKE_PATH = Path(__file__).resolve().parents[1] / 'backend' / 'legal_domain' / 'consultation' / 'intake.py'


def _read_intake() -> str:
    return INTAKE_PATH.read_text(encoding='utf-8')


def test_intake_does_not_inline_clause_prefix_negation_logic():
    """The clause-prefix walk (``clause_start = max(text.rfind(...) + 1``) and the
    bare ``prefix = text[...]`` slice have been replaced by ``_spans`` policies.
    Re-introducing them defeats the consolidation.
    """
    text = _read_intake()
    assert 'clause_start' not in text, (
        'intake.py must not inline a clause-prefix walk; route through _spans'
    )
    assert 'prefix = text[' not in text, (
        'intake.py must not compute a prefix slice inline; route through _spans'
    )


def test_intake_does_not_use_negation_lookbehinds():
    """Lookbehind-based negation triggers (``(?<!不是)``, ``(?<!并非)``) are a
    per-char scope check at odds with the unified utility. Use ``has_asserted``
    / ``has_negated`` with the appropriate policy.
    """
    text = _read_intake()
    assert '(?<!不是)' not in text
    assert '(?<!并非)' not in text


def test_intake_reuses_correction_marker_utility():
    """The inline correction list (``而是|其实是|实际是...``) only survives in
    ``_spans.is_correction``; ``intake.py`` calls the function instead.
    """
    text = _read_intake()
    assert '而是|其实是|实际是' not in text, (
        'intake.py must not duplicate the correction marker regex; use is_correction'
    )


def test_intake_routes_exhaustion_via_spans_utility():
    """``says_evidence_exhausted`` and ``asserted_exclusive_inventory`` go
    through the spans utility instead of inlining their own clause-prefix
    matches.
    """
    text = _read_intake()
    assert 'has_asserted(text, EXHAUSTED_PATTERN' in text
    assert 'first_asserted(text' in text


def test_intake_uses_default_policy_object():
    """The default policy is imported from ``_spans`` — single name-binding."""
    text = _read_intake()
    assert 'from ._spans import' in text
    assert 'CLAUSE_BROAD as _DEFAULT_POLICY' in text
    # The utility should define and export these named policies.
    from backend.legal_domain.consultation._spans import (
        CLAUSE_BROAD,
        EVIDENCE_EXHAUSTED,
        EXCLUSIVE_INVENTORY,
        SENTENCE_BROAD,
        DEFAULT,
    )
    assert DEFAULT is CLAUSE_BROAD


@pytest.mark.parametrize(
    'text, pattern, policy_name, expected',
    [
        # CLAUSE_BROAD: negation anywhere in the same clause negates the
        # candidate. ``从未`` is a broad negation.
        ('对方从未存在借条。', r'(?:存在|有).{0,4}借条', 'CLAUSE_BROAD', False),
        ('我有借条。', r'(?:存在|有).{0,4}借条', 'CLAUSE_BROAD', True),
        # Double-negative reset fires for "不是并非没有借条".
        ('不是并非没有借条。', r'没有.{0,2}借条', 'CLAUSE_BROAD', True),
        # EVIDENCE_EXHAUSTED requires narrow end-of-scope negation; "并非"
        # at end of clause flips the EXHAUSTED token to be negated.
        ('并非没有更多材料。', r'(?:没有更多|没有其他)', 'EVIDENCE_EXHAUSTED', False),
        ('我已经没有更多材料了。', r'(?:没有更多|没有其他)', 'EVIDENCE_EXHAUSTED', True),
        # Sentence-policy does not let an earlier-clause negation reach the
        # next clause's outcome — both clauses are part of the same sentence
        # but the clause boundary still resets the scope.
        ('申请被驳回，撤销了原决定。', r'(?:驳回|撤销|撤回)', 'SENTENCE_BROAD', True),
        # Same sentence, same clause: 没有+outcome negates the outcome.
        ('没有驳回，撤销了原决定。', r'(?:驳回|撤销|撤回)', 'SENTENCE_BROAD', True),
        ('没有驳回，也没有立案', r'(?:驳回|撤销|撤回)', 'CLAUSE_BROAD', False),
    ],
)
def test_utility_supports_call_sites(text, pattern, policy_name, expected):
    """Property-style cross-policy sanity check that mirrors what each prior
    inline call site used to verify before being routed through ``_spans``.
    """
    from backend.legal_domain.consultation._spans import (
        CLAUSE_BROAD,
        EVIDENCE_EXHAUSTED,
        SENTENCE_BROAD,
        has_asserted,
    )
    policy = {'CLAUSE_BROAD': CLAUSE_BROAD, 'EVIDENCE_EXHAUSTED': EVIDENCE_EXHAUSTED, 'SENTENCE_BROAD': SENTENCE_BROAD}[policy_name]
    assert has_asserted(text, pattern, policy=policy) == expected, (text, pattern, policy_name)
