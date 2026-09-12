"""One scope/negation utility for the consultation intake.

Throughout `intake.py` the same idea was repeated six times: a regex match is
*asserted* only if the upstream scope (clause or sentence) does not negate it,
otherwise it is *negated*. The duplication produced R1–R4 and R17-class defects
where one spelling change fixed one symptom but left the others untouched.

This module centralises the policy. Every call site that previously inlined a
clause-prefix check or a `(?<!…)` lookbehind now goes through
`asserted_spans` / `has_asserted` / `has_negated`. The defaults match the union
of the prior spellings, so callers do not need to learn a new policy to keep
their behaviour.

`is_correction` (separate utility) keeps the "user explicitly replaced the
prior value" semantics out of the scope-negation utility because correction
and scope-negation are different signals with different downstream effects
(overwrite vs. constrain).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional


# Union of every multi-character negation prefix previously inlined across
# `intake.py`. The broad set covers signal-style checks (safety / deadline) and
# clause-style checks (exhaustion / exclusive inventory / procedure / outcome).
_CLAUSE_BROAD_NEGATION: re.Pattern[str] = re.compile(
    r'(?:不是|并非|并不是|并不意味着|并不等同于|不等于|不代表|不能说|并非意味着|'
    r'没有|并未|未曾|不存在|尚未|未被|无须|无需|不需|未|'
    r'[不非无未没])'
)

# Narrow end-of-clause negation. Used by exhaustion and exclusive inventory,
# where "并不是X" type phrases must negate the local keyword but a negation
# from the start of the clause must not.
_CLAUSE_END_NEGATION: re.Pattern[str] = re.compile(
    r'(?:不是|并非|并不是|并不意味着|并不等同于|不等于|不代表|不能说|并非意味着)'
    r'\s*$'
)

# Narrow end-of-clause negation used only by exclusive inventory.
_INVENTORY_END_NEGATION: re.Pattern[str] = re.compile(
    r'(?:不是|并非|并不是)\s*$'
)

# A double-negative that *re-asserts* the candidate. Used by every negation
# check that already had to recover from "不是没有人身安全风险" type input.
# The reset may straddle the upstream / match boundary because "不是没有X" is
# split: "不是" lives upstream and the "没有" is the start of the match.
_DOUBLE_NEGATION_RESET: re.Pattern[str] = re.compile(
    r'(?:不是|并非|并不是|并不|也并非)'
    r'\s*'
    r'(?:没有|并未|不存在|无|未曾)'
)

_CORRECTION_MARKERS: re.Pattern[str] = re.compile(
    r'而是|其实是|实际是|准确说是|应该是|应当是|更正(?:一下|为|成)?|说错了'
)
_CORRECTION_IDENTITY: re.Pattern[str] = re.compile(
    r'(?:我|本人)不是[^，,；;]{1,20}[，,；;]\s*(?:我)?是'
)


_CLAUSE_BREAKS: re.Pattern[str] = re.compile(r'[，。；;\n,]')
_SENTENCE_BREAKS: re.Pattern[str] = re.compile(r'[。，；\n,.!?！？]')


@dataclass(frozen=True)
class NegationPolicy:
    """How the upstream context decides whether a candidate is asserted.

    * `negation_pattern` defines what counts as a negation. The pattern is
      searched in the upstream scope; for the "end-of-scope" policies the
      pattern itself contains a trailing ``\\s*$`` so it must be at the end.
    * `double_negative_reset` cancels the negation when its start sits at-or-
      after the negation in the upstream+boundary scope.
    * `scope_breaks` defines what stops a negation from reaching the match.
    * `window` is the maximum number of characters upstream of the match that
      we are willing to inspect (the boundary-aware scope clamps the slice).
    * `name` is for diagnostics only; it surfaces in test failures when the
      wrong policy is selected.
    """

    negation_pattern: re.Pattern[str]
    double_negative_reset: re.Pattern[str] = _DOUBLE_NEGATION_RESET
    scope_breaks: re.Pattern[str] = _CLAUSE_BREAKS
    window: int = 12
    name: str = 'unnamed'

    def upstream_span(self, text: str, match_start: int) -> tuple[int, int]:
        """Return ``(start, end)`` absolute indexes for the upstream scope."""
        start = max(0, match_start - self.window)
        end = match_start
        last_break = -1
        for m in self.scope_breaks.finditer(text, start, end):
            last_break = m.start()
        if last_break == -1:
            return start, end
        return last_break + 1, end

    def upstream(self, text: str, match_start: int) -> str:
        start, end = self.upstream_span(text, match_start)
        return text[start:end]

    def is_asserted(self, text: str, match_start: int) -> bool:
        scope_start, _ = self.upstream_span(text, match_start)
        scope = text[scope_start:match_start]
        negation = self.negation_pattern.search(scope)
        if not negation:
            return True
        # Narrow end-anchored policies do not reset: their negation pattern
        # already anchors to the end of the upstream scope (``\\s*$``), so a
        # candidate "材料我并非没有更多" with scope "材料我并非" is correctly
        # detected as negated without needing to peek past the boundary. The
        # reset never matches for these policies.
        reset_end = min(len(text), match_start + 3)
        reset_start = max(0, scope_start - 1)
        reset = self.double_negative_reset.search(text[reset_start:reset_end])
        if reset is not None:
            reset_abs = reset_start + reset.start()
            negation_abs = scope_start + negation.start()
            if reset_abs >= negation_abs:
                return True
        return False


# Signal-style / safety / deadline / procedure policies. Use a window big
# enough to catch "对方回复里说" style phrases but bounded by clause breaks.
CLAUSE_BROAD = NegationPolicy(
    negation_pattern=_CLAUSE_BROAD_NEGATION,
    scope_breaks=_CLAUSE_BREAKS,
    window=20,
    name='CLAUSE_BROAD',
)
SENTENCE_BROAD = NegationPolicy(
    negation_pattern=_CLAUSE_BROAD_NEGATION,
    scope_breaks=_SENTENCE_BREAKS,
    window=24,
    name='SENTENCE_BROAD',
)
# Narrow end-anchored policies. The negation pattern itself anchors to the
# end of the upstream (``\\s*$``), so the double-negative reset is disabled
# — otherwise "材料我并非没有更多" would be re-asserted even though the
# existing inline behaviour intentionally treated it as negated.
_NO_RESET = re.compile(r'(?!)')
EXCLUSIVE_INVENTORY = NegationPolicy(
    negation_pattern=_INVENTORY_END_NEGATION,
    scope_breaks=_CLAUSE_BREAKS,
    window=24,
    double_negative_reset=_NO_RESET,
    name='EXCLUSIVE_INVENTORY',
)
EVIDENCE_EXHAUSTED = NegationPolicy(
    negation_pattern=_CLAUSE_END_NEGATION,
    scope_breaks=_CLAUSE_BREAKS,
    window=24,
    double_negative_reset=_NO_RESET,
    name='EVIDENCE_EXHAUSTED',
)
# Backwards-compatible default = CLAUSE_BROAD.
DEFAULT = CLAUSE_BROAD


def asserted_spans(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    policy: NegationPolicy = DEFAULT,
) -> list[re.Match[str]]:
    """Return every match of `pattern` whose span is asserted under `policy`."""
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    return [m for m in compiled.finditer(text) if policy.is_asserted(text, m.start())]


def has_asserted(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    policy: NegationPolicy = DEFAULT,
) -> bool:
    return bool(asserted_spans(text, pattern, policy=policy))


def has_negated(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    policy: NegationPolicy = DEFAULT,
) -> bool:
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    return any(not policy.is_asserted(text, m.start()) for m in compiled.finditer(text))


def negated_matches(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    policy: NegationPolicy = DEFAULT,
) -> list[re.Match[str]]:
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    return [m for m in compiled.finditer(text) if not policy.is_asserted(text, m.start())]


def first_asserted(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    policy: NegationPolicy = DEFAULT,
) -> Optional[re.Match[str]]:
    for match in asserted_spans(text, pattern, policy=policy):
        return match
    return None


def find_asserted(
    text: str,
    pattern: str | re.Pattern[str],
    *,
    policy: NegationPolicy = DEFAULT,
):
    """Sugar: return the first asserted match's group(0), or None.

    Mirrors the most common "one asserted capture" shape that the inline code
    used to spell out by hand.
    """
    match = first_asserted(text, pattern, policy=policy)
    return None if match is None else match.group(0)


def is_correction(text: str) -> bool:
    """The user explicitly announced a replacement (not a scope-negation).

    Downstream, a correction overwrites the prior fact while a scope-negation
    just constrains it. Keeping these separate avoids e.g. treating
    "不是没有借条" as a fresh correction that wipes the prior fact.
    """
    return bool(_CORRECTION_MARKERS.search(text)) or bool(_CORRECTION_IDENTITY.search(text))


__all__ = [
    'CLAUSE_BROAD',
    'DEFAULT',
    'EVIDENCE_EXHAUSTED',
    'EXCLUSIVE_INVENTORY',
    'NegationPolicy',
    'SENTENCE_BROAD',
    'asserted_spans',
    'find_asserted',
    'first_asserted',
    'has_asserted',
    'has_negated',
    'is_correction',
    'negated_matches',
]
