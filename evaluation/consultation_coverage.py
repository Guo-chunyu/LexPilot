"""Deterministic enumerative coverage matrix for the shared consultation intake.

The hand-picked red-team rounds probe behaviour. This module probes *coverage*:
it walks every domain's evidence slots against a fixed set of natural
availability frames and reports which (domain, frame, material) combinations the
intake does not handle. The result is a measurand, not an example: the residual
gap set is compared against `evaluation/consultation_coverage.json`, so a new gap
fails the suite and a fixed gap has to be removed from the registry.

Cases contain no real personal data.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.legal_domain.consultation.profiles import PROFILES


DOMAIN_OPENERS: dict[str, tuple[str, str]] = {
    'debt': ('对方', '朋友向我借款4万元，约定下个月还，请给我方案。'),
    'housing': ('房东', '我是租客，退租后房东扣着我的押金不退，请给我方案。'),
    'family': ('对方', '我准备离婚，双方对财产分割有争议，请给我方案。'),
    'consumer': ('商家', '我在健身房办的会员卡，门店停止营业了，请给我方案。'),
    'contract': ('供应商', '供应商收了货款但一直没有交货，请给我方案。'),
    'corporate': ('公司', '我是公司股东，想核对出资和股东权利，请给我方案。'),
    'intellectual_property': ('平台', '有人盗用我创作的摄影作品并在网上销售，请给我方案。'),
    'inheritance': ('家人', '父亲去世后留下遗产，家人对分配有争议，请给我方案。'),
    'traffic': ('交警', '我发生交通事故受伤，还在治疗，请给我方案。'),
    'medical': ('医务科', '手术后出现后遗症，我想核对诊疗过程，请给我方案。'),
    'tort': ('对方', '有人仍在网上公开我的隐私并造谣，请给我方案。'),
    'enforcement': ('执行法官', '生效判决履行期已过，对方仍未付款，请给我方案。'),
    'criminal': ('办案人员', '家人被刑事拘留，我收到了通知书，请给我方案。'),
    'administrative': ('承办人员', '我收到行政处罚决定，认为事实认定不完整，请给我方案。'),
    'labor_dispute': ('公司', '我是员工，公司拖欠我的工资，请给我方案。'),
}

FRAME_TEMPLATES = {
    'user_has': '补充一下，我有{material}，请更新方案。',
    'user_lacks': '补充一下，我没有{material}，请更新方案。',
    'user_cannot_get': '补充一下，{material}我这边拿不到，请更新方案。',
    'handler_cannot_provide': '{actor}表示{material}不能给我，我应该怎么办？',
}

# frame -> (expect material recorded as held by the user, expect material recorded unavailable)
FRAME_EXPECTATIONS: dict[str, tuple[bool, bool]] = {
    'user_has': (True, False),
    'user_lacks': (False, True),
    'user_cannot_get': (False, True),
    # A handler's refusal says nothing about what the user already holds, so
    # availability is not asserted; the claim itself must be persisted.
    'handler_cannot_provide': (False, False),
}


@dataclass(frozen=True)
class CoverageProbe:
    probe_id: str
    domain: str
    frame: str
    material: str
    messages: tuple[str, str]

    @property
    def expectation(self) -> tuple[bool, bool]:
        return FRAME_EXPECTATIONS[self.frame]


@dataclass(frozen=True)
class AssertionProbe:
    """A user number that a later counterparty claim must not displace."""

    probe_id: str
    domain: str
    user_number: str
    claim_marker: str
    messages: tuple[str, str]


ASSERTION_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        'debt', '4万元', '只借了2万元',
        '朋友向我借款4万元，约定下个月还，请给我方案。',
        '对方表示只借了2万元，剩下的是利息，我应该怎么办？',
    ),
    (
        'housing', '6000元', '只有3000元',
        '我是租客，退租后房东扣着我6000元押金不退，请给我方案。',
        '房东表示押金只有3000元，其余是租金，我应该怎么办？',
    ),
    (
        'contract', '8万元', '只收到5万元',
        '供应商收了8万元货款但一直没有交货，请给我方案。',
        '供应商表示只收到5万元，其他是别的项目，我应该怎么办？',
    ),
    (
        'consumer', '3000元', '只有1200元',
        '我在健身房办的会员卡，余额3000元，门店停止营业了，请给我方案。',
        '商家表示我的余额只有1200元，其余已经消费过了，我应该怎么办？',
    ),
    (
        'enforcement', '10万元', '只欠5万元',
        '生效判决履行期已过，对方还欠10万元没付，请给我方案。',
        '执行法官表示对方只欠5万元，其余已经付过了，我应该怎么办？',
    ),
)


def generate_assertion_probes() -> list[AssertionProbe]:
    """Return probes for "a counterparty claim must not replace the user's number"."""
    return [
        AssertionProbe(
            probe_id=f'{domain}|counterparty_claim_number',
            domain=domain,
            user_number=user_number,
            claim_marker=claim_marker,
            messages=(opener, claim),
        )
        for domain, user_number, claim_marker, opener, claim in ASSERTION_SPECS
    ]


def audit_assertion_probe(probe: AssertionProbe, state) -> list[str]:
    """The user's own figure survives, and the claim lands as a dispute detail."""
    failures: list[str] = []
    if state.case_type != probe.domain:
        failures.append(f'domain={state.case_type}, expected={probe.domain}')
    amount = str(state.facts.get('amount', ''))
    if probe.user_number not in amount:
        failures.append(f'user figure lost from amount: {amount!r}')
    if probe.claim_marker in amount:
        failures.append('counterparty claim was written into the user amount slot')
    details = str(state.facts.get('details', ''))
    if probe.claim_marker not in details:
        failures.append('counterparty claim was not persisted as a dispute detail')
    return failures


def _material_terms(name: str) -> str:
    """Use the most natural wording the project knows for this material."""
    from backend.legal_domain.consultation.intake import EVIDENCE_ALIASES

    aliases = EVIDENCE_ALIASES.get(name)
    return aliases[0] if aliases else name


def generate_coverage_probes() -> list[CoverageProbe]:
    """Return a stable cross-product of domain evidence slots and frames."""
    probes: list[CoverageProbe] = []
    for domain, (actor, opener) in DOMAIN_OPENERS.items():
        profile = PROFILES.get(domain)
        if profile is None:
            continue
        for name, *_ in profile.evidence:
            material = _material_terms(name)
            for frame, template in FRAME_TEMPLATES.items():
                if frame == 'handler_cannot_provide' and not actor:
                    continue
                follow_up = template.format(material=material, actor=actor)
                probes.append(
                    CoverageProbe(
                        probe_id=f'{domain}|{frame}|{name}',
                        domain=domain,
                        frame=frame,
                        material=name,
                        messages=(opener, follow_up),
                    )
                )
    return probes


def audit_coverage_probe(probe: CoverageProbe, state) -> list[str]:
    """Return invariant failures for one probe, using structured state only."""
    failures: list[str] = []
    if state.case_type != probe.domain:
        failures.append(f'domain={state.case_type}, expected={probe.domain}')
    held = {item.name for item in state.evidence}
    unavailable = set(state.unavailable_evidence)
    expect_held, expect_unavailable = probe.expectation
    is_held = probe.material in held
    is_unavailable = probe.material in unavailable
    if expect_held and not is_held:
        failures.append('material not recorded as held')
    if expect_unavailable and not is_unavailable:
        failures.append('material not recorded as unobtainable')
    if not expect_held and expect_unavailable and is_held:
        failures.append('material wrongly recorded as held')
    if not expect_unavailable and is_unavailable and probe.frame != 'handler_cannot_provide':
        failures.append('material wrongly recorded as unobtainable')
    if is_held and is_unavailable:
        failures.append('material recorded as both held and unobtainable')
    if probe.frame == 'handler_cannot_provide':
        details = str(state.facts.get('details', ''))
        if probe.material not in details:
            failures.append('handler claim about the material was not persisted')
    # An unobtainable material must never be requested as an upload action.
    if is_unavailable:
        for step in (state.final_report or {}).get('action_plan', []):
            if any(probe.material in str(item) for item in step.get('materials', [])):
                failures.append('unobtainable material listed as an upload action')
    return failures
