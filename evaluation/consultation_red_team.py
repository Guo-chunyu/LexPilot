"""Deterministic synthetic red-team matrix for the public consultation engine.

The cases contain no real names, identifiers, addresses or account data. They
are behavioral probes rather than legal-answer ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
from random import Random
import re

from backend.legal_domain.consultation.perspective import client_perspective


@dataclass(frozen=True)
class RedTeamCase:
    case_id: str
    tags: tuple[str, ...]
    messages: tuple[str, ...]
    expected_domain: str
    expected_role: str = ''
    expected_facts: tuple[tuple[str, str], ...] = ()
    forbidden_reply_fragments: tuple[str, ...] = ()
    expected_urgent: bool | None = None
    expected_exhausted: bool | None = None
    expected_route: str = ''
    origin: str = 'fixed'
    expected_reply_fragments: tuple[str, ...] = ()
    max_followup_similarity: float | None = None
    expected_evidence_names: tuple[str, ...] = ()
    forbidden_evidence_names: tuple[str, ...] = ()
    expected_unavailable_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnonymousUpload:
    name: str
    data: bytes
    media_type: str


def generate_red_team_cases() -> list[RedTeamCase]:
    """Generate a stable, reviewable matrix spanning all supported domains."""

    cases = [
        RedTeamCase(
            'debt_complete_progress',
            ('debt', 'negation', 'partial_payment', 'procedure_progress'),
            (
                '朋友借钱不还，我想追回借款。',
                '2025-03-12朋友向我借款5万元，约定一个月后归还，已还1万元剩4万元，没有借条，有转账和微信，催款三次且对方拒绝，请给我具体方案。',
            ),
            'debt', 'creditor',
            (('details', '约定一个月后归还'), ('amount', '剩4万元'), ('procedure', '催款三次')),
            ('当时约定什么时候还', '已经还过一部分'),
        ),
        RedTeamCase(
            'debt_role_and_amount_correction',
            ('debt', 'role_correction', 'fact_correction'),
            (
                '我是借款人，争议本金是5万元。',
                '说错了，我不是借款人，是出借人；实际尚欠4万元，请给我方案。',
            ),
            'debt', 'creditor', (('amount', '4万元'),),
        ),
        RedTeamCase(
            'debt_unresolved_amount_conflict',
            ('debt', 'fact_conflict'),
            (
                '朋友向我借款5万元，我有转账记录。',
                '借款金额是4万元，请给我方案。',
            ),
            'debt', 'creditor', (('amount', '4万元'),),
        ),
        RedTeamCase(
            'housing_landlord', ('housing', 'opposing_role'),
            ('我是房东，租客退房后房间有损坏，我要核算押金扣款，请给我方案。',),
            'housing', 'landlord',
        ),
        RedTeamCase(
            'family_caregiver', ('family', 'identity', 'property'),
            ('我是孩子母亲，准备离婚，孩子一直由我照顾，房屋登记在对方名下，请给我方案。',),
            'family',
        ),
        RedTeamCase(
            'consumer_exhausted', ('consumer', 'evidence_exhausted', 'procedure_progress'),
            (
                '健身房关门，会员卡还剩3000元，我已经投诉但没有回复。',
                '只有付款截图，现有材料就这些，没有其他证据，请给我方案。',
            ),
            'consumer', expected_facts=(('procedure', '已经投诉'),),
        ),
        RedTeamCase(
            'contract_failed_negotiation', ('contract', 'procedure_progress'),
            ('供应商收款后不交货，已经协商三次但对方拒绝退款，请给我方案。',),
            'contract', expected_facts=(('procedure', '已经协商'),),
        ),
        RedTeamCase(
            'criminal_urgent', ('criminal', 'urgent', 'liberty'),
            ('家人今天被刑事拘留，我收到了拘留通知书，请给我具体方案。',),
            'criminal',
        ),
        RedTeamCase(
            'administrative_deadline', ('administrative', 'deadline', 'document'),
            ('我今天收到市场监管局行政处罚决定，文书写了救济期限，请给我方案。',),
            'administrative',
        ),
        RedTeamCase(
            'court_hearing_day_after_tomorrow',
            ('contract', 'deadline', 'urgent', 'relative_deadline'),
            ('合同纠纷已经起诉，我收到法院通知，后天开庭，请给我方案。',),
            'contract', expected_facts=(('procedure', '已经起诉'),),
        ),
        RedTeamCase(
            'administrative_three_day_cure',
            ('administrative', 'deadline', 'urgent', 'document_period'),
            ('行政复议材料收到补正通知，文书要求3日内补正，请给我方案。',),
            'administrative',
        ),
        RedTeamCase(
            'administrative_negated_deadline',
            ('administrative', 'negation', 'deadline_negation'),
            ('我收到行政复议补正通知，但通知没有要求3日内补正，也没有写明截止日期，请给我一般方案。',),
            'administrative', expected_urgent=False,
        ),
        RedTeamCase(
            'contract_deadline_correction',
            ('contract', 'negation', 'procedure_progress', 'deadline_correction', 'fact_correction'),
            (
                '合同纠纷已经起诉，我收到法院通知，后天开庭，请先给我方案。',
                '更正一下，我看错了，通知不是后天开庭，也没有写明开庭日期，请更新方案。',
            ),
            'contract', expected_facts=(('procedure', '不是后天开庭'),), expected_urgent=False,
        ),
        RedTeamCase(
            'criminal_negated_detention',
            ('criminal', 'negation', 'urgent_negation'),
            ('家人没有被刑事拘留，也没有被抓，只是收到普通询问通知，请给我一般方案。',),
            'criminal', expected_urgent=False,
        ),
        RedTeamCase(
            'criminal_detention_correction',
            ('criminal', 'negation', 'procedure_progress', 'fact_correction', 'urgent_correction'),
            (
                '家人收到刑事拘留通知书，请先给我方案。',
                '更正一下，我看错了，家人没有被拘留，收到的只是普通询问通知，请更新方案。',
            ),
            'criminal', expected_facts=(('procedure', '没有被拘留'),), expected_urgent=False,
        ),
        RedTeamCase(
            'family_safety_correction',
            ('family', 'negation', 'urgent_correction'),
            (
                '准备离婚，对方正在威胁我，我担心人身安全，请先给我方案。',
                '更正一下，刚才表述不准确，对方没有家暴，也没有人身安全问题，请更新一般方案。',
            ),
            'family', expected_urgent=False,
        ),
        RedTeamCase(
            'corporate_shareholder', ('corporate', 'identity'),
            ('我是公司股东，书面要求查账后被拒绝，请给我方案。',),
            'corporate',
        ),
        RedTeamCase(
            'ip_online_sale', ('intellectual_property', 'digital_evidence'),
            ('有人盗用我创作的摄影作品并在网上销售，我有源文件和网页截图，请给我方案。',),
            'intellectual_property',
        ),
        RedTeamCase(
            'inheritance_will', ('inheritance', 'document_conflict'),
            ('父亲去世留有遗嘱，但家人称还有另一份遗嘱，现有材料互相冲突，请给我方案。',),
            'inheritance',
        ),
        RedTeamCase(
            'traffic_insurer_refusal', ('traffic', 'injury', 'opponent_response'),
            ('我被汽车撞伤，对方保险公司已经拒赔，仍在治疗，请给我方案。',),
            'traffic',
        ),
        RedTeamCase(
            'medical_record_gap', ('medical', 'evidence_gap'),
            ('医院手术后出现后遗症，我没有完整病历，只有收费票据，请给我方案。',),
            'medical',
        ),
        RedTeamCase(
            'privacy_tort', ('tort', 'ongoing_harm'),
            ('有人仍在网上公开我的隐私并造谣，我已保存网址和截图，请给我方案。',),
            'tort',
        ),
        RedTeamCase(
            'enforcement_active', ('enforcement', 'procedure_progress'),
            ('生效判决履行期已过，对方只付了一部分，我已经申请执行并取得案号，请给我方案。',),
            'enforcement', expected_facts=(('procedure', '已经申请'),),
        ),
        RedTeamCase(
            'labor_employee', ('labor_dispute', 'employee_role', 'negation'),
            ('我是员工，公司拖欠三个月工资，我没有劳动合同，只有工资流水和工作微信，请给我方案。',),
            'labor_dispute', 'employee',
        ),
        RedTeamCase(
            'outside_mainland', ('jurisdiction', 'outside_mainland'),
            ('事情发生在香港，是合同退款争议，请先给我整理方案。',),
            'contract', expected_facts=(('location', '香港'),),
        ),
        RedTeamCase(
            'unclassified_general', ('general', 'identity_unclear'),
            ('\u8bf7\u5148\u5e2e\u6211\u6574\u7406\u4e8b\u5b9e\u548c\u4e0b\u4e00\u6b65\u65b9\u6848\u3002',),
            'general',
        ),
    ]
    variants = {case.case_id: case for case in generate_automatic_variants()}
    cases = [variants.get(case.case_id, case) for case in cases]
    return [
        *cases,
        *generate_round_two_variants(),
        *generate_round_three_variants(),
        *generate_round_four_variants(),
        *generate_round_five_variants(),
        *generate_round_six_variants(),
        *generate_round_seven_variants(),
        *generate_round_eight_variants(),
        *generate_round_nine_variants(),
        *generate_round_ten_variants(),
        *generate_round_eleven_variants(),
        *generate_round_twelve_variants(),
        *generate_round_thirteen_variants(),
        *generate_round_fourteen_variants(),
        *generate_round_fifteen_variants(),
        *generate_round_sixteen_variants(),
        *generate_round_seventeen_variants(),
        *generate_round_eighteen_variants(),
        *generate_round_nineteen_variants(),
        *generate_round_twenty_variants(),
    ]


def generate_automatic_variants(seed: int = 20260909) -> list[RedTeamCase]:
    """Create reproducible anonymous wording variants for the active red-team round."""
    randomizer = Random(seed)
    deadline_denial = randomizer.choice(('没有要求', '并未要求'))
    detention_denial = randomizer.choice(('没有被刑事拘留', '并未被刑事拘留'))
    return [
        RedTeamCase(
            'administrative_negated_deadline',
            ('administrative', 'negation', 'deadline_negation'),
            (f'我收到行政复议补正通知，但通知{deadline_denial}3日内补正，也没有写明截止日期，请给我一般方案。',),
            'administrative', expected_urgent=False, origin='auto_variant',
        ),
        RedTeamCase(
            'contract_deadline_correction',
            ('contract', 'negation', 'procedure_progress', 'deadline_correction', 'fact_correction'),
            (
                '合同纠纷已经起诉，我收到法院通知，后天开庭，请先给我方案。',
                '更正一下，我看错了，通知不是后天开庭，也没有写明开庭日期，请更新方案。',
            ),
            'contract', expected_facts=(('procedure', '不是后天开庭'),),
            expected_urgent=False, origin='auto_variant',
        ),
        RedTeamCase(
            'criminal_negated_detention',
            ('criminal', 'negation', 'urgent_negation'),
            (f'家人{detention_denial}，也没有被抓，只是收到普通询问通知，请给我一般方案。',),
            'criminal', expected_urgent=False, origin='auto_variant',
        ),
        RedTeamCase(
            'criminal_detention_correction',
            ('criminal', 'negation', 'procedure_progress', 'fact_correction', 'urgent_correction'),
            (
                '家人收到刑事拘留通知书，请先给我方案。',
                '更正一下，我看错了，家人没有被拘留，收到的只是普通询问通知，请更新方案。',
            ),
            'criminal', expected_facts=(('procedure', '没有被拘留'),),
            expected_urgent=False, origin='auto_variant',
        ),
        RedTeamCase(
            'family_safety_correction',
            ('family', 'negation', 'urgent_correction'),
            (
                '准备离婚，对方正在威胁我，我担心人身安全，请先给我方案。',
                '更正一下，刚才表述不准确，对方没有家暴，也没有人身安全问题，请更新一般方案。',
            ),
            'family', expected_urgent=False, origin='auto_variant',
        ),
    ]


def generate_round_two_variants(seed: int = 20260910) -> list[RedTeamCase]:
    """Generate the next five unseen identity, procedure and evidence variants."""
    randomizer = Random(seed)
    evidence_lead = randomizer.choice(('不是没有更多证据', '并不是材料已经用完'))
    return [
        RedTeamCase(
            'housing_negated_landlord_role', ('housing', 'negation', 'role_reversal'),
            ('我不是房东，是租客；退租后房东不退押金，请给我方案。',),
            'housing', 'tenant', origin='auto_variant',
        ),
        RedTeamCase(
            'labor_negated_employee_role', ('labor_dispute', 'negation', 'role_reversal'),
            ('我不是员工，我是用人单位负责人；员工申请劳动仲裁称拖欠工资，我需要答辩方案。',),
            'labor_dispute', 'employer', origin='auto_variant',
        ),
        RedTeamCase(
            'debt_negated_filing', ('debt', 'negation', 'procedure_progress'),
            ('朋友欠我4万元，我没有起诉，也没有立案，只发过一次催款，请给我方案。',),
            'debt', 'creditor', expected_facts=(('procedure', '没有起诉'),),
            expected_route='negotiation', origin='auto_variant',
        ),
        RedTeamCase(
            'consumer_evidence_not_exhausted', ('consumer', 'negation', 'evidence_not_exhausted'),
            (f'健身房关门不退款，{evidence_lead}，我还有订单和聊天，稍后上传，请给我方案。',),
            'consumer', expected_exhausted=False, origin='auto_variant',
        ),
        RedTeamCase(
            'contract_amount_correction', ('contract', 'fact_correction'),
            (
                '采购合同争议金额5万元，对方没有交货。',
                '更正一下，实际争议金额是4万元，请按新金额给我方案。',
            ),
            'contract', expected_facts=(('amount', '4万元'),), origin='auto_variant',
        ),
    ]


def generate_round_three_variants(seed: int = 20260911) -> list[RedTeamCase]:
    """Generate five unseen attribution, correction and negation-scope variants."""
    randomizer = Random(seed)
    payment_material = randomizer.choice(('付款截图', '支付截图'))
    return [
        RedTeamCase(
            'debt_negated_creditor_role', ('debt', 'negation', 'role_reversal'),
            ('我不是出借人，是借款人；借了4万元，已经还了1万元，请给我应对方案。',),
            'debt', 'debtor', origin='auto_variant',
        ),
        RedTeamCase(
            'housing_role_correction_multiturn', ('housing', 'role_correction', 'fact_correction'),
            (
                '我是租客，退租押金有争议。',
                '说错了，我不是租客，是房东；争议是房屋损坏扣押金，请给我方案。',
            ),
            'housing', 'landlord', origin='auto_variant',
        ),
        RedTeamCase(
            'consumer_nonexclusive_inventory', ('consumer', 'negation', 'evidence_not_exhausted'),
            (f'健身房关门不退款，不是只有{payment_material}，我还有订单和聊天，稍后上传，请给我方案。',),
            'consumer', expected_exhausted=False, origin='auto_variant',
        ),
        RedTeamCase(
            'administrative_historical_deadline', ('administrative', 'deadline', 'historical'),
            ('去年收到行政复议补正通知，文书要求3日内补正，但该期限早已过去，请给我当前方案。',),
            'administrative', expected_urgent=False, origin='auto_variant',
        ),
        RedTeamCase(
            'debt_double_negative_filing', ('debt', 'negation', 'procedure_progress'),
            ('朋友欠我4万元，不是尚未起诉，我已经起诉并拿到案号，请给我方案。',),
            'debt', 'creditor', expected_facts=(('procedure', '已经起诉'),),
            expected_route='formal', origin='auto_variant',
        ),
    ]


def generate_round_four_variants(seed: int = 20260912) -> list[RedTeamCase]:
    """Generate five unseen cross-domain correction and negation variants."""
    randomizer = Random(seed)
    medical_material = randomizer.choice(('病历复印件', '出院记录'))
    return [
        RedTeamCase(
            'family_double_negative_safety', ('family', 'negation', 'urgent'),
            ('准备离婚，不是没有人身安全风险，请给我紧急方案。',),
            'family', expected_urgent=True, origin='auto_variant',
        ),
        RedTeamCase(
            'medical_nonexclusive_inventory', ('medical', 'negation', 'evidence_not_exhausted'),
            (f'手术后出现后遗症，不是只有收费票据，我还有{medical_material}和影像，稍后上传，请给我方案。',),
            'medical', expected_exhausted=False, origin='auto_variant',
        ),
        RedTeamCase(
            'enforcement_filing_retraction', ('enforcement', 'procedure_progress', 'fact_correction'),
            (
                '生效判决履行期已过，我已经申请执行并拿到案号，请先给我方案。',
                '更正一下，实际尚未申请执行，也没有案号，请按当前情况更新方案。',
            ),
            'enforcement', expected_facts=(('procedure', '尚未申请执行'),),
            expected_route='formal', origin='auto_variant',
        ),
        RedTeamCase(
            'labor_employer_unfiled', ('labor_dispute', 'negation', 'opposing_role', 'procedure_progress'),
            ('我不是员工，是公司负责人；员工称欠薪但还没有申请劳动仲裁，公司也没收到通知，请给答辩准备方案。',),
            'labor_dispute', 'employer', expected_facts=(('procedure', '还没有申请'),),
            expected_route='negotiation', origin='auto_variant',
        ),
        RedTeamCase(
            'housing_landlord_amount_correction', ('housing', 'opposing_role', 'fact_correction'),
            (
                '我是房东，租客退房后的押金是6000元，房屋有损坏。',
                '更正一下，押金实际是4500元，已经退了1000元，目前争议3500元，请给我方案。',
            ),
            'housing', 'landlord', expected_facts=(('amount', '3500元'),),
            origin='auto_variant',
        ),
    ]


def generate_round_five_variants(seed: int = 20260913) -> list[RedTeamCase]:
    """Generate five unseen reversal and exhausted-state correction variants."""
    randomizer = Random(seed)
    screenshot = randomizer.choice(('付款截图', '支付截图'))
    return [
        RedTeamCase(
            'housing_tenant_unfiled', ('housing', 'negation', 'opposing_role', 'procedure_progress'),
            ('我不是房东，是租客；房东扣着押金，我还没有起诉，也没有立案，请给我方案。',),
            'housing', 'tenant', expected_facts=(('procedure', '还没有起诉'),),
            expected_route='negotiation', origin='auto_variant',
        ),
        RedTeamCase(
            'labor_employer_amount_correction', ('labor_dispute', 'opposing_role', 'fact_correction'),
            (
                '我是公司负责人，员工申请仲裁称欠薪5万元。',
                '更正一下，员工请求金额实际是4万元，请按单位立场给我答辩方案。',
            ),
            'labor_dispute', 'employer', expected_facts=(('amount', '4万元'),),
            origin='auto_variant',
        ),
        RedTeamCase(
            'administrative_double_negative_filing', ('administrative', 'negation', 'procedure_progress'),
            ('不是尚未申请行政复议，我已经申请并拿到受理号，请给我下一步方案。',),
            'administrative', expected_facts=(('procedure', '已经申请'),),
            expected_route='formal', origin='auto_variant',
        ),
        RedTeamCase(
            'consumer_exhaustion_correction', ('consumer', 'negation', 'evidence_correction'),
            (
                f'健身房关门不退款，我只有{screenshot}，没有其他材料，请先给我方案。',
                '更正一下，我后来找到了订单和完整聊天，不是只有截图，请更新方案。',
            ),
            'consumer', expected_exhausted=False, origin='auto_variant',
        ),
        RedTeamCase(
            'criminal_double_negative_detention', ('criminal', 'negation', 'urgent'),
            ('家人并不是没有被拘留，我收到了拘留通知书，请给我紧急方案。',),
            'criminal', expected_urgent=True, origin='auto_variant',
        ),
    ]


def generate_round_six_variants(seed: int = 20260914) -> list[RedTeamCase]:
    """Generate five unseen specialist-domain and jurisdiction variants."""
    randomizer = Random(seed)
    source_material = randomizer.choice(('创作源文件', '原始工程文件'))
    medical_material = randomizer.choice(('病历复印件', '出院记录'))
    return [
        RedTeamCase(
            'ip_nonexclusive_source_materials', ('intellectual_property', 'negation', 'evidence_not_exhausted'),
            (f'摄影作品被网店盗用，不是只有网页截图，我还有{source_material}和首次发布时间记录，请给我方案。',),
            'intellectual_property', expected_exhausted=False, origin='auto_variant',
        ),
        RedTeamCase(
            'medical_records_not_absent', ('medical', 'negation', 'evidence_not_exhausted'),
            (f'手术后出现后遗症，并不是没有诊疗材料，我有{medical_material}和收费票据，请给我方案。',),
            'medical', expected_exhausted=False, origin='auto_variant',
        ),
        RedTeamCase(
            'traffic_insurer_refusal_negated', ('traffic', 'negation', 'opponent_response'),
            ('交通事故仍在治疗，保险公司没有拒赔，只是要求补充病历和票据，请给我方案。',),
            'traffic', expected_route='negotiation', origin='auto_variant',
        ),
        RedTeamCase(
            'corporate_repeated_inspection_refusal', ('corporate', 'procedure_progress'),
            ('我是公司股东，已经书面要求查账两次，公司明确拒绝，请给我后续方案。',),
            'corporate', expected_route='mediation', origin='auto_variant',
        ),
        RedTeamCase(
            'outside_mainland_location_correction', ('contract', 'fact_correction', 'jurisdiction_correction'),
            (
                '事情发生在香港，是合同退款争议，请先给我方案。',
                '更正一下，实际发生在深圳，不涉及香港或其他境外地区，请更新方案。',
            ),
            'contract', expected_facts=(('location', '深圳'),), origin='auto_variant',
        ),
    ]


def generate_round_seven_variants(seed: int = 20260915) -> list[RedTeamCase]:
    """Generate five unseen role, procedure, refusal and jurisdiction variants."""
    randomizer = Random(seed)
    denied_role = randomizer.choice(('出租人', '房东'))
    platform_action = randomizer.choice(('投诉', '申诉'))
    medical_material = randomizer.choice(('病历复印件', '完整病历'))
    return [
        RedTeamCase(
            'housing_formal_role_synonyms', ('housing', 'opposing_role', 'negation'),
            (f'本人并非{denied_role}，而是承租人；退租后的押金被对方扣留，请按承租人立场给我方案。',),
            'housing', 'tenant', origin='auto_variant',
        ),
        RedTeamCase(
            'labor_indirect_arbitration_filing', ('labor_dispute', 'procedure_progress'),
            ('我是员工，公司拖欠工资；我已经向劳动人事争议仲裁委员会提交申请并收到受理通知，请给我下一步方案。',),
            'labor_dispute', 'employee',
            expected_facts=(('procedure', '提交申请'),), expected_route='formal',
            origin='auto_variant',
        ),
        RedTeamCase(
            'ip_platform_complaint_refused', ('intellectual_property', 'procedure_progress'),
            (f'摄影作品被网店盗用，我已经向平台{platform_action}两次，平台明确拒绝处理，请给我后续方案。',),
            'intellectual_property', expected_facts=(('procedure', platform_action),),
            expected_route='mediation', origin='auto_variant',
        ),
        RedTeamCase(
            'inheritance_mainland_to_hong_kong_correction',
            ('inheritance', 'fact_correction', 'outside_mainland'),
            (
                '父亲去世后留下遗产房屋，房屋在深圳，请先给我方案。',
                '更正一下，房屋实际位于香港，不在深圳，请更新方案。',
            ),
            'inheritance', expected_facts=(('location', '香港'),),
            origin='auto_variant',
        ),
        RedTeamCase(
            'medical_exhaustion_scope_negated', ('medical', 'negation', 'evidence_not_exhausted'),
            (f'医院手术后出现后遗症，不能说没有其他证据，我还有{medical_material}和影像，请给我方案。',),
            'medical', expected_exhausted=False, origin='auto_variant',
        ),
    ]


def generate_round_eight_variants(seed: int = 20260916) -> list[RedTeamCase]:
    """Generate five unseen cross-domain follow-up grounding variants."""
    randomizer = Random(seed)
    reply_verb = randomizer.choice(('刚回复说', '刚表示'))
    question = randomizer.choice(('我该怎么回应', '我应该怎么办'))
    will_copy = randomizer.choice(('另一份遗嘱的照片', '一张新遗嘱照片'))
    common_forbidden = ('@granularity:plan_summary',)
    return [
        RedTeamCase(
            'housing_damage_reason_followup', ('housing', 'multiturn', 'opponent_update'),
            (
                '我是租客，退租后房东扣着4000元押金，请先给我方案。',
                f'房东{reply_verb}要扣1200元墙面修复费，但没有提供维修票据，{question}？',
            ),
            'housing', 'tenant', expected_facts=(('details', '1200元墙面修复费'),),
            forbidden_reply_fragments=(*common_forbidden, '房东只说“有损坏”'),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '墙面修复费'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'consumer_transfer_only_followup', ('consumer', 'multiturn', 'opponent_update'),
            (
                '健身房停业，会员卡余额3000元，商家不退款，请先给我方案。',
                f'商家{reply_verb}只能把会员卡转给别人使用，不能退款，{question}？',
            ),
            'consumer', expected_facts=(('details', '只能把会员卡转给别人使用'),),
            forbidden_reply_fragments=(*common_forbidden, '先确认是门店停业'),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '转给别人使用'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'medical_normal_risk_followup', ('medical', 'multiturn', 'opponent_update'),
            (
                '医院手术后出现后遗症，我有完整病历和收费票据，请先给我方案。',
                f'医院{reply_verb}这是正常手术风险，不承认诊疗有问题，{question}？',
            ),
            'medical', expected_facts=(('details', '正常手术风险'),),
            forbidden_reply_fragments=(*common_forbidden, '先保证后续治疗'),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '正常手术风险'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'contract_price_increase_followup', ('contract', 'multiturn', 'opponent_update'),
            (
                '供应商收款后不交货，我已经催过一次，请先给我方案。',
                f'供应商{reply_verb}原材料涨价，除非再加2万元否则不发货，{question}？',
            ),
            'contract', expected_facts=(('details', '除非再加2万元'),),
            forbidden_reply_fragments=(*common_forbidden, '先把合同约定'),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '除非再加2万元'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'inheritance_will_copy_followup', ('inheritance', 'multiturn', 'opponent_update'),
            (
                '父亲去世后留有遗嘱，家人称可能还有另一份，请先给我方案。',
                f'家人刚发来{will_copy}但拒绝提供原件，{question}？',
            ),
            'inheritance', expected_facts=(('details', '拒绝提供原件'),),
            forbidden_reply_fragments=(*common_forbidden, '先确定哪些财产确属被继承人'),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '拒绝提供原件'),
            max_followup_similarity=0.65,
        ),
    ]


def generate_round_nine_variants(seed: int = 20260917) -> list[RedTeamCase]:
    """Generate five unseen counterparty-alias follow-up variants."""
    randomizer = Random(seed)
    reply_verb = randomizer.choice(('刚回复说', '刚表示'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    return [
        RedTeamCase(
            'housing_agent_service_fee_followup',
            ('housing', 'multiturn', 'counterparty_alias'),
            (
                '我是租客，退租后还有5000元押金由中介代管，请先给我方案。',
                f'中介{reply_verb}要先扣800元服务费才退余款，{question}？',
            ),
            'housing', 'tenant',
            expected_facts=(('amount', '5000元押金'), ('details', '扣800元服务费')),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '扣800元服务费'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'consumer_customer_service_voucher_followup',
            ('consumer', 'multiturn', 'counterparty_alias'),
            (
                '我购买的网课无法继续使用，剩余费用2800元，要求退款，请先给我方案。',
                f'客服{reply_verb}只能补发代金券，不能退还剩余费用，{question}？',
            ),
            'consumer',
            expected_facts=(('amount', '2800元'), ('details', '只能补发代金券')),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '只能补发代金券'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'administrative_case_officer_basis_followup',
            ('administrative', 'multiturn', 'counterparty_alias'),
            (
                '我收到行政处罚决定，认为认定事实不完整，请先给我方案。',
                f'承办人员{reply_verb}只能按原决定处理，也不提供进一步说明，{question}？',
            ),
            'administrative',
            expected_facts=(('details', '只能按原决定处理'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '只能按原决定处理'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'traffic_adjuster_partial_repair_followup',
            ('traffic', 'multiturn', 'counterparty_alias'),
            (
                '交通事故后车辆已经维修，我有事故认定书和维修票据，请先给我方案。',
                f'保险理赔员{reply_verb}只认可一半修理费，其余不赔，{question}？',
            ),
            'traffic',
            expected_facts=(('details', '只认可一半修理费'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '只认可一半修理费'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'ip_store_operator_supplier_followup',
            ('intellectual_property', 'multiturn', 'counterparty_alias'),
            (
                '我的摄影作品被网店擅自用于商品页面，我有原始文件，请先给我方案。',
                f'店铺经营者{reply_verb}图片来自供货商，不同意删除或赔偿，{question}？',
            ),
            'intellectual_property',
            expected_facts=(('details', '图片来自供货商'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '图片来自供货商'),
            max_followup_similarity=0.65,
        ),
    ]


def generate_round_ten_variants(seed: int = 20260918) -> list[RedTeamCase]:
    """Generate five unseen follow-ups without an explicit recency marker."""
    randomizer = Random(seed)
    reply_verb = randomizer.choice(('回复说', '表示'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    return [
        RedTeamCase(
            'housing_unmarked_landlord_deduction_followup',
            ('housing', 'multiturn', 'unmarked_opponent_update'),
            (
                '我是租客，退租后房东还扣着6000元押金，请先给我方案。',
                f'房东{reply_verb}只能退4500元，另外1500元算清洁费，{question}？',
            ),
            'housing', 'tenant',
            expected_facts=(('amount', '6000元押金'), ('details', '1500元算清洁费')),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '1500元算清洁费'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'consumer_unmarked_merchant_extension_followup',
            ('consumer', 'multiturn', 'unmarked_opponent_update'),
            (
                '我预付了摄影套餐，但门店一直无法安排服务，要求退款，请先给我方案。',
                f'商家{reply_verb}只能延期半年使用，不接受退款，{question}？',
            ),
            'consumer',
            expected_facts=(('details', '只能延期半年使用'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '只能延期半年使用'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'medical_unmarked_hospital_causation_followup',
            ('medical', 'multiturn', 'unmarked_opponent_update'),
            (
                '手术后出现持续疼痛，我有病历和复查记录，请先给我方案。',
                f'医院{reply_verb}目前的疼痛与手术无关，不同意进一步说明，{question}？',
            ),
            'medical',
            expected_facts=(('details', '疼痛与手术无关'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '疼痛与手术无关'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'contract_unmarked_supplier_force_majeure_followup',
            ('contract', 'multiturn', 'unmarked_opponent_update'),
            (
                '供应商超过合同交付期仍未发货，我已经付款，请先给我方案。',
                f'供应商{reply_verb}延期属于不可抗力，拒绝承担违约责任，{question}？',
            ),
            'contract',
            expected_facts=(('details', '延期属于不可抗力'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '延期属于不可抗力'),
            max_followup_similarity=0.65,
        ),
        RedTeamCase(
            'inheritance_unmarked_family_original_followup',
            ('inheritance', 'multiturn', 'unmarked_opponent_update'),
            (
                '父亲去世后留有一份遗嘱照片，但原件在哪里还不清楚，请先给我方案。',
                f'家人{reply_verb}只有照片，没有原件，也不同意共同查找，{question}？',
            ),
            'inheritance',
            expected_facts=(('details', '只有照片，没有原件'),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '只有照片，没有原件'),
            max_followup_similarity=0.65,
        ),
    ]


def generate_round_eleven_variants(seed: int = 20260919) -> list[RedTeamCase]:
    """Generate five unseen pronoun-based opponent follow-ups."""
    randomizer = Random(seed)
    reply_phrase = randomizer.choice(('他们回复说', '他们表示'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    specs = (
        (
            'housing_pronoun_damage_followup', 'housing', 'tenant',
            '我是租客，退租后房东拒绝退押金，请先给我方案。',
            f'{reply_phrase}墙面损耗都应由我承担，也不提供明细，{question}？',
            '墙面损耗都应由我承担',
        ),
        (
            'consumer_pronoun_store_credit_followup', 'consumer', '',
            '商家取消了我预订的服务，但没有退款，请先给我方案。',
            f'{reply_phrase}只能换成店内余额，不能原路退款，{question}？',
            '只能换成店内余额',
        ),
        (
            'medical_pronoun_record_followup', 'medical', '',
            '医院治疗后症状加重，我想先核对病历和处置过程，请给我方案。',
            f'{reply_phrase}只能现场看病历，不能复制完整资料，{question}？',
            '只能现场看病历',
        ),
        (
            'contract_pronoun_substitute_followup', 'contract', '',
            '供应商交付的设备型号与合同不符，请先给我方案。',
            f'{reply_phrase}替代型号功能相近，所以不同意换货，{question}？',
            '替代型号功能相近',
        ),
        (
            'inheritance_pronoun_inventory_followup', 'inheritance', '',
            '父亲去世后家人一直没有共同核对遗产清单，请先给我方案。',
            f'{reply_phrase}部分财产不需要列入遗产，也拒绝说明依据，{question}？',
            '部分财产不需要列入遗产',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'pronoun_opponent_update'),
            (first, followup),
            domain,
            role,
            expected_facts=(('details', detail),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', detail),
            max_followup_similarity=0.65,
        )
        for case_id, domain, role, first, followup, detail in specs
    ]


def generate_round_twelve_variants(seed: int = 20260920) -> list[RedTeamCase]:
    """Generate five unseen actorless reply-framing follow-ups."""
    randomizer = Random(seed)
    reply_frame = randomizer.choice(('回复里写着', '收到回复说'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    specs = (
        (
            'family_actorless_custody_followup', 'family',
            '准备离婚，双方对孩子抚养安排有争议，请先给我方案。',
            f'{reply_frame}孩子只能由对方抚养，不接受其他安排，{question}？',
            '孩子只能由对方抚养',
        ),
        (
            'corporate_actorless_inspection_scope_followup', 'corporate',
            '我是公司股东，已经要求查阅账簿但被拒绝，请先给我方案。',
            f'{reply_frame}只能看年度报表，不能查会计账簿，{question}？',
            '只能看年度报表',
        ),
        (
            'enforcement_actorless_installment_followup', 'enforcement',
            '生效判决履行期已过，对方仍未付款，请先给我执行方案。',
            f'{reply_frame}只能分期支付，但没有提供具体计划，{question}？',
            '只能分期支付',
        ),
        (
            'administrative_actorless_basis_followup', 'administrative',
            '我收到行政处罚决定，认为事实认定不完整，请先给我方案。',
            f'{reply_frame}处理依据不能另行提供，只能看决定书，{question}？',
            '处理依据不能另行提供',
        ),
        (
            'traffic_actorless_insurer_scope_followup', 'traffic',
            '发生交通事故后车辆受损，我有事故认定书和维修票据，请先给我方案。',
            f'{reply_frame}只处理车辆损失，不认可其他合理费用，{question}？',
            '只处理车辆损失',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'actorless_reply_update'),
            (first, followup),
            domain,
            expected_facts=(('details', detail),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', detail),
            max_followup_similarity=0.65,
        )
        for case_id, domain, first, followup, detail in specs
    ]


def generate_round_thirteen_variants(seed: int = 20260921) -> list[RedTeamCase]:
    """Generate five unseen next-step-only follow-ups."""
    randomizer = Random(seed)
    question = randomizer.choice(('那我现在最先做哪一步', '那我今天先做什么'))
    scope = randomizer.choice(('请只说当前一步', '不用重复完整方案'))
    specs = (
        ('debt_next_step_only_followup', 'debt', '', '朋友欠我2万元，有借条和转账记录，已经到期，请先给我方案。'),
        ('housing_next_step_only_followup', 'housing', 'tenant', '我是租客，退租后房东扣着押金不退，请先给我方案。'),
        ('consumer_next_step_only_followup', 'consumer', '', '健身房停止营业，预付余额没有退，请先给我方案。'),
        ('contract_next_step_only_followup', 'contract', '', '供应商超过约定期限仍未交货，我已经付款，请先给我方案。'),
        ('medical_next_step_only_followup', 'medical', '', '治疗后症状加重，我有完整病历和复查记录，请先给我方案。'),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'next_step_only'),
            (first, f'{question}？{scope}。'),
            domain,
            role,
            forbidden_reply_fragments=('@granularity:plan_summary',),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '@granularity:single_step'),
            max_followup_similarity=0.65,
        )
        for case_id, domain, role, first in specs
    ]


def generate_round_fourteen_variants(seed: int = 20260922) -> list[RedTeamCase]:
    """Generate five unseen cross-domain evidence-supplement follow-ups."""
    randomizer = Random(seed)
    found = randomizer.choice(('我又找到了', '我补充找到了'))
    request = randomizer.choice(('请更新材料清单', '请按这些材料更新方案'))
    specs = (
        (
            'corporate_new_registry_materials', 'corporate',
            '我是公司股东，想核对出资和股东权利，请先给我方案。',
            f'{found}股东名册和公司章程，{request}。',
            ('股东与章程材料',),
        ),
        (
            'ip_new_creation_source_materials', 'intellectual_property',
            '我的摄影作品被网店使用，我正在整理权属材料，请先给我方案。',
            f'{found}创作源文件和首次发表页面，{request}。',
            ('权利来源材料',),
        ),
        (
            'traffic_new_dashcam_materials', 'traffic',
            '发生交通事故，我有事故认定书但还在整理现场资料，请先给我方案。',
            f'{found}行车记录仪原视频和现场照片，{request}。',
            ('事故认定及现场记录',),
        ),
        (
            'medical_new_consent_materials', 'medical',
            '手术后出现持续不适，我正在整理诊疗材料，请先给我方案。',
            f'{found}手术同意书和护理记录，{request}。',
            ('完整病历',),
        ),
        (
            'contract_new_delivery_materials', 'contract',
            '供应商交付的货物存在争议，我正在整理履行情况，请先给我方案。',
            f'{found}物流签收单和验收记录，{request}。',
            ('履行记录',),
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'new_evidence'),
            (first, followup),
            domain,
            forbidden_reply_fragments=('@granularity:plan_summary',),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up',),
            max_followup_similarity=0.65,
            expected_evidence_names=evidence_names,
        )
        for case_id, domain, first, followup, evidence_names in specs
    ]


def generate_round_fifteen_variants(seed: int = 20260923) -> list[RedTeamCase]:
    """Generate five unseen natural-language handling constraints."""
    randomizer = Random(seed)
    prefix = randomizer.choice(('另外补充一个限制', '我还要补充'))
    request = randomizer.choice(('请据此更新方案', '请按这个条件调整'))
    specs = (
        (
            'debt_no_direct_contact_constraint', 'debt',
            '朋友欠款到期不还，我有转账和聊天，请先给我方案。',
            f'{prefix}：请不要再让我联系对方，只接受正式程序，{request}。',
            '不要再让我联系对方',
        ),
        (
            'housing_remote_only_constraint', 'housing',
            '我是租客，退租后押金没有退，请先给我方案。',
            f'{prefix}：我人在外地，不能去现场办理，{request}。',
            '不能去现场办理',
        ),
        (
            'consumer_very_low_cost_constraint', 'consumer',
            '商家停止提供预付服务，也没有退款，请先给我方案。',
            f'{prefix}：我能承担的费用很少，希望优先免费渠道，{request}。',
            '费用很少',
        ),
        (
            'contract_written_only_constraint', 'contract',
            '供应商延期交货并拒绝说明原因，请先给我方案。',
            f'{prefix}：我只接受书面沟通，不进行电话交涉，{request}。',
            '只接受书面沟通',
        ),
        (
            'inheritance_fast_resolution_constraint', 'inheritance',
            '家人对遗产清单有争议，请先给我方案。',
            f'{prefix}：我必须尽快处理完，不能长期拖延，{request}。',
            '必须尽快处理完',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'constraint_update'),
            (first, followup),
            domain,
            expected_facts=(('constraints', constraint),),
            forbidden_reply_fragments=('@granularity:plan_summary',),
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up',),
            max_followup_similarity=0.65,
        )
        for case_id, domain, first, followup, constraint in specs
    ]


def generate_round_sixteen_variants(seed: int = 20260924) -> list[RedTeamCase]:
    """Generate five unseen authority and case-handler reply aliases."""
    randomizer = Random(seed)
    reply_verb = randomizer.choice(('回复说', '表示'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    specs = (
        (
            'criminal_investigator_reply_followup', 'criminal',
            '家人被刑事拘留，我收到了拘留通知书，请给我方案。',
            f'办案人员刚刚{reply_verb}不能告知案件情况，也不提供文书，{question}？',
            '不能告知案件情况',
        ),
        (
            'traffic_police_reply_followup', 'traffic',
            '发生交通事故后车辆受损，我有事故认定书，请给我方案。',
            f'交警{reply_verb}要等责任认定才能办理，也不给其他说明，{question}？',
            '要等责任认定才能办理',
        ),
        (
            'administrative_counter_window_reply_followup', 'administrative',
            '我收到行政处罚决定，认为事实认定不完整，请先给我方案。',
            f'窗口工作人员{reply_verb}只能口头答复，不给书面说明，{question}？',
            '只能口头答复',
        ),
        (
            'medical_office_reply_followup', 'medical',
            '手术后出现持续疼痛，我有病历和复查记录，请先给我方案。',
            f'医务科{reply_verb}只能走鉴定程序，不提供其他说明，{question}？',
            '只能走鉴定程序',
        ),
        (
            'enforcement_judge_reply_followup', 'enforcement',
            '生效判决履行期已过，对方仍未付款，请先给我执行方案。',
            f'执行法官{reply_verb}查不到对方财产，只能先终结本次执行，{question}？',
            '查不到对方财产',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'authority_alias'),
            (first, followup),
            domain,
            expected_facts=(('details', detail),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', detail),
            max_followup_similarity=0.65,
        )
        for case_id, domain, first, followup, detail in specs
    ]


def generate_round_seventeen_variants(seed: int = 20260925) -> list[RedTeamCase]:
    """Generate five unseen naturally phrased unobtainable-material follow-ups."""
    randomizer = Random(seed)
    denial = randomizer.choice(('我现在拿不到', '我这边拿不到'))
    request = randomizer.choice(('请更新方案', '请据此调整材料清单'))
    common_forbidden = ('@granularity:plan_summary',)
    specs = (
        (
            'traffic_unobtainable_accident_report', 'traffic',
            '发生交通事故，我受伤还在治疗，请先给我方案。',
            f'交警说事故认定书要等调查结束，{denial}，{request}。',
            '事故认定及现场记录',
        ),
        (
            'housing_unobtainable_handover_record', 'housing',
            '我是租客，退租后房东扣着押金不退，请先给我方案。',
            f'房东把房屋交接记录收走了，{denial}，{request}。',
            '房屋交接记录',
        ),
        (
            'medical_unobtainable_medical_record', 'medical',
            '手术后出现后遗症，我还在和医院交涉，请先给我方案。',
            f'医院说完整病历还在整理，{denial}，{request}。',
            '完整病历',
        ),
        (
            'contract_unobtainable_delivery_record', 'contract',
            '供应商交付的货物存在争议，我正在整理履行情况，请先给我方案。',
            f'对方不给我签收单和验收记录，{denial}，{request}。',
            '履行记录',
        ),
        (
            'consumer_unobtainable_payment_record', 'consumer',
            '商家停止提供预付服务，也没有退款，请先给我方案。',
            f'商家不给我开发票，付款凭证{denial}，{request}。',
            '付款和余额记录',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'unobtainable_material'),
            (first, followup),
            domain,
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up',),
            max_followup_similarity=0.65,
            forbidden_evidence_names=(material,),
            expected_unavailable_evidence=(material,),
        )
        for case_id, domain, first, followup, material in specs
    ]


def generate_round_eighteen_variants(seed: int = 20260926) -> list[RedTeamCase]:
    """Generate five unseen debt cases where the counterparty disputes the debt."""
    randomizer = Random(seed)
    reply_verb = randomizer.choice(('回复说', '表示'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    first_turn = '朋友向我借款4万元，有转账记录和微信聊天，还没还，请先给我方案。'
    specs = (
        (
            'debt_counterparty_denies_principal',
            f'对方{reply_verb}只借了2万元，剩下的是利息，{question}？',
            '只借了2万元',
        ),
        (
            'debt_counterparty_claims_repaid',
            f'对方{reply_verb}这笔钱早就还清了，{question}？',
            '早就还清了',
        ),
        (
            'debt_counterparty_partial_admission',
            f'对方{reply_verb}只承认其中2万元，其他不认，{question}？',
            '只承认其中2万元',
        ),
        (
            'debt_counterparty_refuses_installments',
            f'对方{reply_verb}不同意分期，也拒绝任何还款安排，{question}？',
            '不同意分期',
        ),
        (
            'debt_counterparty_offsets_with_car',
            f'对方{reply_verb}要用一辆车抵掉这笔借款，{question}？',
            '用一辆车抵掉',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            ('debt', 'multiturn', 'counterparty_denial'),
            (first_turn, followup),
            'debt',
            expected_facts=(('amount', '4万元'), ('details', position)),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', position),
            max_followup_similarity=0.65,
        )
        for case_id, followup, position in specs
    ]


def generate_round_nineteen_variants(seed: int = 20260927) -> list[RedTeamCase]:
    """Generate five unseen labour specialist-path later-turn updates."""
    randomizer = Random(seed)
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    first_turn = '我是员工，公司拖欠工资6万元，没有劳动合同，只有工资流水和工作微信，请给我方案。'
    common_forbidden = ('@granularity:plan_summary',)
    specs = (
        (
            'labor_counterparty_denies_wage_debt',
            f'公司回复说只欠2万元，其余已经结清，{question}？',
            '只欠2万元',
        ),
        (
            'labor_hr_denies_arrears',
            f'人事回复说公司不承认欠薪，也不提供工资明细，{question}？',
            '不承认欠薪',
        ),
        (
            'labor_counterparty_refuses_arbitration',
            f'公司回复说拒绝仲裁，要求我直接去起诉，{question}？',
            '拒绝仲裁',
        ),
        (
            'labor_counterparty_repayment_terms',
            f'公司回复说只能分三个月结清，不同意一次付清，{question}？',
            '只能分三个月结清',
        ),
    )
    cases = [
        RedTeamCase(
            case_id,
            ('labor_dispute', 'multiturn', 'counterparty_denial'),
            (first_turn, followup),
            'labor_dispute', 'employee',
            expected_facts=(('details', position),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', position),
            max_followup_similarity=0.65,
        )
        for case_id, followup, position in specs
    ]
    cases.append(
        RedTeamCase(
            'labor_next_step_only_followup',
            ('labor_dispute', 'multiturn', 'next_step_only'),
            (first_turn, '那我现在最先做哪一步？请只说当前一步。'),
            'labor_dispute', 'employee',
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', '@granularity:single_step'),
            max_followup_similarity=0.65,
        )
    )
    return cases


def generate_round_twenty_variants(seed: int = 20260928) -> list[RedTeamCase]:
    """Generate five unseen procedure-outcome reversals reported by the handler."""
    randomizer = Random(seed)
    reply_verb = randomizer.choice(('回复说', '表示'))
    question = randomizer.choice(('我应该怎么办', '我该怎么回应'))
    common_forbidden = ('@granularity:plan_summary',)
    specs = (
        (
            'enforcement_execution_application_dismissed', 'enforcement', '',
            '生效判决履行期已过，对方仍未付款，请先给我执行方案。',
            f'执行法官{reply_verb}执行申请被驳回了，因为没有提供财产线索，{question}？',
            '驳回', 'formal',
        ),
        (
            'administrative_reconsideration_not_accepted', 'administrative', '',
            '我收到行政处罚决定，认为事实认定不完整，请先给我方案。',
            f'承办人员{reply_verb}复议申请不予受理，因为超过期限了，{question}？',
            '不予受理', 'formal',
        ),
        (
            'ip_platform_complaint_dismissed', 'intellectual_property', '',
            '我的摄影作品被网店盗用，我已经向平台投诉，请给我方案。',
            f'平台{reply_verb}投诉不成立，已经驳回了，{question}？',
            '不成立', 'mediation',
        ),
        (
            'consumer_complaint_rejected', 'consumer', '',
            '健身房停业，会员卡余额没有退，请给我方案。',
            f'商家{reply_verb}我的投诉已经被驳回，不再处理，{question}？',
            '驳回', 'mediation',
        ),
        (
            'traffic_liability_finding_revoked', 'traffic', '',
            '发生交通事故，交警已经出具事故认定书，请给我方案。',
            f'交警{reply_verb}对方申请复核，原认定书被撤销了，{question}？',
            '撤销', '',
        ),
    )
    return [
        RedTeamCase(
            case_id,
            (domain, 'multiturn', 'procedure_outcome'),
            (first, followup),
            domain,
            expected_facts=(('procedure', outcome),),
            forbidden_reply_fragments=common_forbidden,
            origin='auto_variant',
            expected_reply_fragments=('@mode:follow_up', outcome),
            max_followup_similarity=0.65,
            expected_route=route,
        )
        for case_id, domain, role, first, followup, outcome, route in specs
    ]


def generate_anonymous_uploads() -> list[AnonymousUpload]:
    """Build minimal TXT/PDF/DOCX/PNG fixtures entirely in memory."""
    from docx import Document
    import pymupdf
    from PIL import Image, PngImagePlugin

    docx_buffer = BytesIO()
    document = Document()
    document.add_paragraph('Synthetic collection message; no real person or account.')
    document.core_properties.author = 'LexPilot synthetic red team'
    document.save(docx_buffer)

    pdf = pymupdf.open()
    page = pdf.new_page(width=180, height=120)
    page.insert_text((18, 40), 'Synthetic chat record; no real person', fontsize=8)
    pdf_bytes = pdf.tobytes(garbage=4, deflate=True)
    pdf.close()

    png_buffer = BytesIO()
    image = Image.new('RGB', (16, 16), color=(238, 243, 246))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('Description', 'Synthetic screenshot; no real person')
    image.save(png_buffer, format='PNG', pnginfo=metadata)

    return [
        AnonymousUpload('\u533f\u540d\u8f6c\u8d26\u8bb0\u5f55.txt', b'Synthetic transfer record: CNY 40000; no real account.', 'text/plain'),
        AnonymousUpload('\u533f\u540d\u50ac\u6b3e\u8bb0\u5f55.docx', docx_buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        AnonymousUpload('\u533f\u540d\u804a\u5929\u8bb0\u5f55.pdf', pdf_bytes, 'application/pdf'),
        AnonymousUpload('\u533f\u540d\u5fae\u4fe1\u622a\u56fe.png', png_buffer.getvalue(), 'image/png'),
    ]


UNSAFE_RESULT_LANGUAGE = re.compile(r'保证.{0,8}(?:胜诉|赔偿)|肯定胜诉|胜诉率|必胜|一定能赢')
CALCULATED_DEADLINE = re.compile(r'(?:截止|最迟).{0,12}\d{4}[-年]\d{1,2}[-月]\d{1,2}')


def reply_satisfies(fragment: str, reply: str, state) -> bool:
    """Resolve one expected/forbidden fragment.

    A fragment may name a structural reply property instead of literal text so
    the case expectations survive rewording of the surface copy:
    ``@mode:follow_up``, ``@granularity:single_step``, ``@mode_at:1=follow_up``.
    """
    if fragment.startswith('@mode_at:'):
        index, _, expected = fragment.removeprefix('@mode_at:').partition('=')
        history = state.consultation.reply_mode_history
        return int(index) < len(history) and history[int(index)] == expected
    if fragment.startswith('@mode:'):
        return state.consultation.reply_mode == fragment.removeprefix('@mode:')
    if fragment.startswith('@granularity:'):
        return state.consultation.reply_granularity == fragment.removeprefix('@granularity:')
    return fragment in reply


def audit_red_team_result(case: RedTeamCase, state, replies: list[str]) -> list[str]:
    """Return concise invariant failures for one completed synthetic case."""

    failures: list[str] = []
    combined_reply = '\n'.join(replies)
    report = state.final_report or {}
    if state.case_type != case.expected_domain:
        failures.append(f'domain={state.case_type}, expected={case.expected_domain}')
    if case.expected_role:
        role = client_perspective(state)['id']
        if role != case.expected_role:
            failures.append(f'role={role}, expected={case.expected_role}')
    if case.expected_urgent is not None and bool(state.consultation.urgent_actions) != case.expected_urgent:
        failures.append(
            f'urgent={bool(state.consultation.urgent_actions)}, expected={case.expected_urgent}'
        )
    if case.expected_exhausted is not None and state.evidence_collection_exhausted != case.expected_exhausted:
        failures.append(
            f'evidence_exhausted={state.evidence_collection_exhausted}, expected={case.expected_exhausted}'
        )
    if case.expected_route:
        route = report.get('strategy_comparison', {}).get('recommended_route', '')
        if route != case.expected_route:
            failures.append(f'route={route}, expected={case.expected_route}')
    for key, fragment in case.expected_facts:
        value = str(state.facts.get(key, ''))
        if fragment not in value:
            failures.append(f'fact {key} missing {fragment!r}: {value!r}')
    for fragment in case.expected_reply_fragments:
        if not reply_satisfies(fragment, replies[-1], state):
            failures.append(f'current-turn reply missing {fragment!r}')
    evidence_names = {item.name for item in state.evidence}
    for name in case.expected_evidence_names:
        if name not in evidence_names:
            failures.append(f'evidence inventory missing {name!r}')
    for name in case.forbidden_evidence_names:
        if name in evidence_names:
            failures.append(f'evidence {name!r} wrongly recorded as held by the user')
    unavailable_evidence = set(state.unavailable_evidence)
    for name in case.expected_unavailable_evidence:
        if name not in unavailable_evidence:
            failures.append(
                f'evidence {name!r} not recorded as unobtainable: {sorted(unavailable_evidence)}'
            )
    for fragment in case.forbidden_reply_fragments:
        if reply_satisfies(fragment, replies[-1], state):
            failures.append(f'repeated answered question: {fragment}')
    if case.max_followup_similarity is not None and len(replies) > 1:
        similarity = SequenceMatcher(None, replies[0], replies[-1]).ratio()
        if similarity > case.max_followup_similarity:
            failures.append(
                f'follow-up similarity={similarity:.3f}, '
                f'max={case.max_followup_similarity:.3f}'
            )
    if not report:
        failures.append('final report missing')
        return failures
    public_text = combined_reply + '\n' + str(state.public_dict())
    if UNSAFE_RESULT_LANGUAGE.search(public_text):
        failures.append('unsafe result guarantee or win-rate language')
    if CALCULATED_DEADLINE.search(public_text):
        failures.append('unverified exact deadline was calculated')
    if 'stored_path' in public_text:
        failures.append('private storage path leaked')
    if report.get('quality_audit', {}).get('citation_issues'):
        failures.append('citation integrity issue')
    for deadline in report.get('deadlines', []):
        if not re.search(r'待核实|待核对|[需须].{0,12}核对|未计算|无法计算', str(deadline.get('status', ''))):
            failures.append('deadline lacks unverified status')
    return failures
