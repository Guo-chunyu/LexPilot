"""Deterministic coverage matrix for constraint extraction (Stage 6).

Stage 5 promoted "missing alias" symptom into an explicit probe. This module
promotes the same symptom for the constraint extraction pipeline: natural
phrasing variants of each constraint kind must reach
``constraint_sentences`` and be persisted to ``facts['constraints']``.

It also covers the three withdrawal patterns in ``intake.py``:
``_NEGATE_NO_CONTACT_PATTERN``, ``_GENERIC_RETRACTION_PATTERN`` and
``_REAFFIRM_TAIL_PATTERN``. A new phrase for "I changed my mind" must be
visible through ``is_constraint_withdrawal`` so R19-style regressions stay
covered without a hand-picked red-team round.

Canonical constraint kinds:
- budget          ："预算有限"/"希望先低成本协商"/"费用不超过5000元".
- contact_method  ："不要电话联系"/"只接受书面沟通"/"请不要再打电话".
- attendance      ："人在外地"/"无法到场"/"我没办法现场办理".
- priority        ："必须尽快处理"/"不能长期拖延".
- relationship    ："不想影响关系"/"怕伤和气".
- action_avoidance ："不想打官司"/"不想再催款".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhrasingProbe:
    """A user sentence that must produce a constraint assertion."""

    probe_id: str
    kind: str
    sentence: str
    expect_match: bool


@dataclass(frozen=True)
class WithdrawalProbe:
    """A user message that must (or must not) trigger constraint withdrawal."""

    probe_id: str
    sentence: str
    expect_withdrawal: bool


# Natural phrasings per constraint kind. Each entry is something a real user
# is likely to type; ``expect_match=True`` means the constraint regex on the
# ``intake`` code path must capture the sentence.
PHRASING_PROBES: tuple[PhrasingProbe, ...] = (
    # budget
    PhrasingProbe('budget|cost', 'budget', '我预算只有5000元', True),
    PhrasingProbe('budget|low', 'budget', '希望先低成本协商', True),
    PhrasingProbe('budget|within', 'budget', '费用希望在2000元以内', True),
    PhrasingProbe('budget|free', 'budget', '优先免费渠道', True),
    PhrasingProbe('budget|limited', 'budget', '费用有限', True),
    # contact_method
    PhrasingProbe('contact|no-call', 'contact_method', '请不要再给我打电话', True),
    PhrasingProbe('contact|written-only', 'contact_method', '只接受书面沟通', True),
    PhrasingProbe('contact|written-prefer', 'contact_method', '书面沟通优先', True),
    PhrasingProbe('contact|no-telephone', 'contact_method', '不进行电话交涉', True),
    PhrasingProbe('contact|no-contact', 'contact_method', '不要再联系我了', True),
    # attendance
    PhrasingProbe('attendance|out-of-town', 'attendance', '人在外地', True),
    PhrasingProbe('attendance|inconvenient', 'attendance', '不方便到场', True),
    PhrasingProbe('attendance|cannot-attend', 'attendance', '无法到场', True),
    PhrasingProbe('attendance|cannot-onsite', 'attendance', '不能到现场', True),
    # priority
    PhrasingProbe('priority|urgent', 'priority', '必须尽快处理', True),
    PhrasingProbe('priority|delay-impossible', 'priority', '不能长期拖延', True),
    PhrasingProbe('priority|hope-fast', 'priority', '希望尽快给个结果', True),
    # relationship
    PhrasingProbe('relationship|no-relation', 'relationship', '不想影响关系', True),
    # action_avoidance
    PhrasingProbe('action|avoid-litigation', 'action_avoidance', '我不想打官司', True),
    PhrasingProbe('action|avoid-dunning', 'action_avoidance', '不想再催款了', True),
    PhrasingProbe('action|avoid-negotiate', 'action_avoidance', '不想再协商', True),
    # Negative examples — must NOT be a constraint
    PhrasingProbe('noise|ask-plan', 'none', '请给我方案', False),
    PhrasingProbe('noise|thank', 'none', '谢谢你', False),
)


# Withdrawal probes — each sentence must trigger ``is_constraint_withdrawal``.
WITHDRAWAL_PROBES: tuple[WithdrawalProbe, ...] = (
    WithdrawalProbe('wd|negate-no-contact', '愿意再和对方协商一次', True),
    WithdrawalProbe('wd|negate-rediscuss', '愿意重新协商', True),
    WithdrawalProbe('wd|negate-no-longer', '不再拒绝协商', True),
    WithdrawalProbe('wd|explicit-revoke', '撤销不要再联系对方', True),
    WithdrawalProbe('wd|generic-retract-with-tail', '我改变主意了，还是想再试试', True),
    # Negative examples — these must NOT trigger withdrawal (they are not
    # constraint-related retractions)
    WithdrawalProbe('wd|noise|hello', '你好吗', False),
    WithdrawalProbe('wd|noise|plan', '请给我下一步方案', False),
    WithdrawalProbe('wd|noise|change-topic', '我现在想先说另一件事', False),
)


def generate_phrasing_probes() -> list[PhrasingProbe]:
    return list(PHRASING_PROBES)


def generate_withdrawal_probes() -> list[WithdrawalProbe]:
    return list(WITHDRAWAL_PROBES)


def audit_phrasing_probe(probe: PhrasingProbe) -> list[str]:
    """Assert ``probe.sentence`` is (or is not) captured by the constraint
    extraction path. We re-run the same regex decision used inside
    ``ingest_text`` without spinning up a full CaseState."""
    from backend.legal_domain.consultation.intake import ingest_text

    if probe.expect_match:
        from backend.legal_rl.state import CaseState

        state = CaseState()
        ingest_text(probe.sentence, state)
        facts = dict(state.facts)
        if 'constraints' not in facts or not facts['constraints']:
            return [
                f'expected constraint captured for {probe.probe_id} '
                f'sentence={probe.sentence!r}'
            ]
    else:
        from backend.legal_rl.state import CaseState

        state = CaseState()
        ingest_text(probe.sentence, state)
        if 'constraints' in state.facts and state.facts['constraints']:
            return [
                f'expected NO constraint for {probe.probe_id} '
                f'sentence={probe.sentence!r}, got {state.facts["constraints"]!r}'
            ]
    return []


def audit_withdrawal_probe(probe: WithdrawalProbe) -> list[str]:
    from backend.legal_domain.consultation.intake import is_constraint_withdrawal

    actual = bool(is_constraint_withdrawal(probe.sentence))
    if actual != probe.expect_withdrawal:
        return [
            f'expected_withdrawal={probe.expect_withdrawal} actual={actual} '
            f'for {probe.probe_id} sentence={probe.sentence!r}'
        ]
    return []
