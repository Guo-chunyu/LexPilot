"""Deterministic enumeration matrix for evidence alias coverage.

Stage 5 promotes the "missing alias" symptom (e.g. R17
``bare_medical_record_alias_missing``) into an explicit probe. For every
canonical material in ``intake.EVIDENCE_ALIASES`` we run a battery of natural
phrase variants through ``_evidence_mention`` and assert each maps to the
right ``(mentioned, unavailable)`` status.

The matrix is intentionally narrow: it covers natural alias coverage and
unavailability scope, so a newly added alias or a changed unavailability
regex fails the matrix without a hand-picked red-team round.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.legal_domain.consultation.intake import EVIDENCE_ALIASES


# Canonical evidence type -> canonical phrasing variants a user is likely
# to use. Each entry must reach `mentioned=True` when fed verbatim into
# ``_evidence_mention(text, name)``.
ALIAS_PHRASINGS: dict[str, tuple[str, ...]] = {
    '借条': (
        '他写的借条',
        '那张借据',
        '借条我手里有一份',
    ),
    '转账记录': (
        '银行转账记录',
        '银行流水',
        '我这边转账凭证',
    ),
    '催款记录': (
        '催款记录',
        '微信催还',
        '催款的聊天',
    ),
    '房屋交接记录': (
        '退房时拍过交房视频',
        '当时拍了交接视频',
    ),
    '付款及押金凭证': (
        '押金转账凭证',
        '当时押金的付款记录',
    ),
    '租赁或购房合同': (
        '我们签的租赁合同',
        '租房合同',
        '购房合同',
        '租约',
    ),
    '订单与消费合同': (
        '我下的订单',
        '签的消费合同',
        '健身房会员协议',
    ),
    '付款和余额记录': (
        '付款截图',
        '支付截图',
        '我的余额记录',
    ),
    '售后沟通记录': (
        '我跟客服的完整聊天',
        '售后记录的截图',
        '客服沟通的邮件',
    ),
    '股东与章程材料': (
        '股东名册',
        '公司章程',
        '出资证明',
        '工商登记文件',
    ),
    '权利来源材料': (
        '创作源文件',
        '原始工程文件',
        '首次发表页面',
    ),
    '事故认定及现场记录': (
        '交警的事故认定书',
        '行车记录仪的视频',
        '现场照片',
    ),
    '完整病历': (
        '手术同意书',
        '护理记录',
        '出院记录',
        '病历复印件',
        '检查报告',
        '手术病历',
    ),
    '履行记录': (
        '物流签收单',
        '签收单',
        '验收记录',
        '交货记录',
    ),
}


# (canonical, sentence, expected_mentioned, expected_unavailable)
SCOPE_PROBES: tuple[tuple[str, str, bool, bool], ...] = (
    # name-first denial in the same clause
    ('借条', '我没有借条', True, True),
    ('借条', '借条我没有', True, True),
    # name-first denial followed by a non-other-material "I cannot get it" clause
    ('借条', '我有转账记录，借条我这边拿不到', True, True),
    # transfer should not be negated because the second clause names 借条 only
    ('转账记录', '我有转账记录，借条我这边拿不到', True, False),
    # postposed "拿不到" without another material in between
    ('完整病历', '病历我这边拿不到', True, True),
    ('完整病历', '病历还在医院，我现在拿不到', True, True),
    # explicit "没有" / "没有…问题" boundary
    ('借条', '借条没有问题', True, False),
    # possession without denial
    ('借条', '借条我手里有一份', True, False),
    # possessive-but-missing if mentioned in scope negative
    ('借条', '我没有其他相关材料，借条也没有', True, True),
)


@dataclass(frozen=True)
class AliasProbe:
    probe_id: str
    canonical: str
    phrase: str


@dataclass(frozen=True)
class ScopeProbe:
    probe_id: str
    canonical: str
    sentence: str
    expect_mentioned: bool
    expect_unavailable: bool


def generate_alias_probes() -> list[AliasProbe]:
    return [
        AliasProbe(
            probe_id=f'alias|{canonical}|{idx}',
            canonical=canonical,
            phrase=phrase,
        )
        for canonical, phrases in ALIAS_PHRASINGS.items()
        for idx, phrase in enumerate(phrases)
    ]


def generate_scope_probes() -> list[ScopeProbe]:
    return [
        ScopeProbe(
            probe_id=f'scope|{idx}',
            canonical=canonical,
            sentence=sentence,
            expect_mentioned=expect_mentioned,
            expect_unavailable=expect_unavailable,
        )
        for idx, (canonical, sentence, expect_mentioned, expect_unavailable) in enumerate(SCOPE_PROBES)
    ]


def audit_alias_probe(probe: AliasProbe) -> list[str]:
    from backend.legal_domain.consultation.intake import EVIDENCE_ALIASES as _ALIASES

    aliases = _ALIASES.get(probe.canonical)
    if aliases is None:
        return [f'no aliases registered for canonical {probe.canonical!r}']
    if not any(term in probe.phrase for term in aliases):
        return [
            f'phrase {probe.phrase!r} does not match any registered alias '
            f'{tuple(aliases)!r} for canonical {probe.canonical!r}'
        ]
    return []


def audit_scope_probe(probe: ScopeProbe, siblings: tuple[str, ...] = ()) -> list[str]:
    from backend.legal_domain.consultation.intake import _evidence_mention

    if probe.canonical not in EVIDENCE_ALIASES:
        return [f'no aliases registered for canonical {probe.canonical!r}']
    mentioned, unavailable = _evidence_mention(probe.sentence, probe.canonical, siblings)
    failures: list[str] = []
    if mentioned != probe.expect_mentioned:
        failures.append(
            f'mentioned={mentioned}, expected={probe.expect_mentioned} '
            f'for sentence={probe.sentence!r}'
        )
    if unavailable != probe.expect_unavailable:
        failures.append(
            f'unavailable={unavailable}, expected={probe.expect_unavailable} '
            f'for sentence={probe.sentence!r}'
        )
    return failures


def all_canonical_names() -> tuple[str, ...]:
    return tuple(EVIDENCE_ALIASES.keys())
