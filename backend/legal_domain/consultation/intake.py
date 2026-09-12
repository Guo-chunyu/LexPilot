"""Grounded intake and contextual short answers, with no remote document upload."""

import re

from backend.legal_rl.state import CaseState, EvidenceGap, EvidenceStatus
from .models import CounterpartyClaim, EvidenceTask, SlotAssertion, TimelineEntry
from .profiles import OUTSIDE_MAINLAND, PROFILES
from .perspective import client_perspective
from ._spans import (
    CLAUSE_BROAD as _DEFAULT_POLICY,
    EVIDENCE_EXHAUSTED,
    EXCLUSIVE_INVENTORY,
    SENTENCE_BROAD,
    find_asserted,
    first_asserted,
    has_asserted,
    has_negated,
    is_correction,
    is_correction as _is_correction,
)


# Slots that record the user's own statement. A counterparty or authority
# assertion for these keys is recorded in ``counterparty_claims`` instead of
# overwriting the user's value.
_USER_OWNED_SLOTS = frozenset({'amount', 'parties', 'event_time', 'goal', 'location', 'procedure', 'constraints'})


# Slots that are explicitly built to absorb counterparty / authority updates.
# A claim at these slots is the legitimate write target.
_COUNTERPARTY_OPEN_SLOTS = frozenset({'details'})


# Withdrawal marker for ``constraints``. The user retracts an earlier handling
# preference so the prior active assertion must be marked ``withdrawn`` and
# dropped from ``facts['constraints']``. Only the *most recent* active user
# constraint is withdrawn — earlier ones stay active unless the message
# explicitly retracts them. Generic "我改变主意了" alone is too broad
# (round-19 probe 4) and would drop unrelated constraints like 人在外地.
_NEGATE_NO_CONTACT_PATTERN = re.compile(
    r'愿意再.{0,6}(?:协商|沟通|联系|谈|主动)|'
    r'愿意重新.{0,4}(?:协商|谈|联系)|'
    r'不再拒绝.{0,4}(?:协商|联系)|'
    r'撤(?:销|回).{0,6}(?:不要再|不要.{0,4}联系|不要.{0,4}协商)|'
    r'重新.{0,4}(?:协商|联系)'
)
_GENERIC_RETRACTION_PATTERN = re.compile(
    r'改变主意|不再限制|不坚持.{0,6}(?:那个|前述)|撤(?:销|回).{0,4}(?:限制|要求|那个)'
)
_REAFFIRM_TAIL_PATTERN = re.compile(
    r'愿意|可以.{0,4}了|还是想.{0,6}(?:试试|再|重新)|还是.{0,4}(?:可以|愿意|想)'
)


QUESTIONS = {
    'location': '这件事发生在哪个省、市？如果涉及境外、香港、澳门或台湾，也请说明，以免用错法律和办理渠道。',
    'event_time': '关键事情是什么时候发生的？有没有收到通知、决定或约定履行日期？能说出年月日最好，不确定也可以直接说。',
    'goal': '你现在最希望得到什么结果：拿回钱、停止某个行为、继续履行，还是先弄清责任？',
    'parties': '你和对方分别是什么身份？对方是个人、公司还是机关，有没有能确认对方主体的材料？姓名可以先用化名。',
    'details': '',
    'procedure': '现在处理到哪一步：尚未交涉、已经协商或投诉，还是收到法院／机关文书？如果文书写了期限，请把相关内容告诉我。',
    'evidence_inventory': '目前有哪些可以提供的原始材料？可以上传最关键的一份；只有截图、材料在对方手里或暂时没有，也请如实说。',
    'constraints': '你能接受的时间、费用和处理方式有什么限制？例如希望先低成本协商、无法到场，或担心影响关系。',
    'amount': '争议金额是多少？请区分原始金额、已经支付或返还的部分和目前主张金额。',
}
LABELS = {'location': '适用地区', 'event_time': '关键时间', 'goal': '希望结果', 'parties': '双方身份', 'details': '争议细节', 'procedure': '当前进展', 'evidence_inventory': '材料自述', 'constraints': '时间与预算', 'amount': '金额陈述'}
DATE_PATTERN = r'(?:\d{4}年\d{1,2}月(?:\d{1,2}日)?|\d{4}-\d{1,2}-\d{1,2}|今年\d{1,2}月|去年\d{1,2}月|今天|昨天|前天|上个月|去年)'
AMOUNT_PATTERN = r'[0-9零一二两三四五六七八九十百千万点.,]+\s*(?:万元|元|块钱|块|万)'
PLAN_PATTERN = r'方案|步骤|怎么做|怎么办理|起草|写.{0,4}(?:函|申请|诉状)|报告|行动清单|先给我|直接告诉'
UNKNOWN_PATTERN = r'^(?:我也?|这个|现在|目前)?(?:不清楚|不知道|不确定|记不清|忘了|不方便说|不想说|无法提供)[。！!\s]*$'
EXHAUSTED_PATTERN = (
    r'(?:没有(?:更多|其他|其它|别的).{0,6}(?:材料|证据|文件)|'
    r'(?:材料|证据|文件).{0,8}(?:暂时)?没有(?:更多|其他|其它|别的)|'
    r'(?:现有|目前|手头|只有|能提供的).{0,6}(?:材料|证据|文件)?.{0,4}就这些|'
    r'(?:暂时)?(?:没|没有)(?:材料|证据)|'
    r'^\s*(?:剩下的?没有了|其余没有了|没有了|就这些)\s*[。！!\s]*$)'
)

EVIDENCE_ALIASES = {
    '借条': ('借条', '借据'),
    '转账记录': ('转账记录', '转账', '流水'),
    '催款记录': ('催款记录', '催款', '催还', '聊天', '微信'),
    '房屋交接记录': ('房屋交接记录', '交房', '交接', '视频'),
    '付款及押金凭证': ('付款及押金凭证', '押金凭证', '转账', '付款'),
    '租赁或购房合同': ('租赁或购房合同', '租赁合同', '租房合同', '购房合同', '合同', '租约'),
    '订单与消费合同': ('订单与消费合同', '订单', '消费合同', '会员协议'),
    '付款和余额记录': ('付款和余额记录', '付款截图', '支付截图', '付款凭证', '余额记录'),
    '售后沟通记录': ('售后沟通记录', '售后记录', '完整聊天', '聊天', '客服沟通'),
    '股东与章程材料': (
        '股东与章程材料', '股东名册', '公司章程', '出资证明', '工商登记',
    ),
    '权利来源材料': (
        '权利来源材料', '创作源文件', '原始工程文件', '首次发表', '发表页面',
    ),
    '事故认定及现场记录': (
        '事故认定及现场记录', '事故认定书', '行车记录仪', '现场照片', '现场视频',
    ),
    '完整病历': (
        '完整病历', '手术同意书', '护理记录', '出院记录', '病历复印件', '检查报告', '病历',
    ),
    '履行记录': (
        '履行记录', '物流签收单', '签收单', '验收记录', '物流记录', '交货记录',
    ),
}

SAFETY_URGENT_ACTION = '先到安全地点并联系当地警方；正在遭受伤害时优先求助和就医，不要为了取证单独接触对方。'
CRIMINAL_URGENT_ACTION = '尽快联系当地刑事律师或法律援助机构，带上通知书核实措施类型、起算日期、办案单位和依法会见途径；不要找关系、串供或删记录。'
DEADLINE_URGENT_ACTION = '先核对文书载明的截止日期与送达凭证，今天就向受理机关或当地律师确认提交和补正方式；不要等材料全部齐了才处理期限。'


def wants_plan(text: str) -> bool:
    return bool(re.search(PLAN_PATTERN, text))


def says_evidence_exhausted(text: str) -> bool:
    """Accept an exhaustion statement only when its scope is asserted.

    The previous inline shape — find a match, walk back to the last clause
    break, then check the narrow-end-of-scope negation list — was duplicated
    across the exclusion-scope siblings below. The ``_spans`` utility now
    owns that policy.
    """
    return has_asserted(text, EXHAUSTED_PATTERN, policy=EVIDENCE_EXHAUSTED)


def asserted_exclusive_inventory(text: str):
    """Return an asserted “only these materials” match, excluding scope negation."""
    return first_asserted(text, r'(?:只有|仅有)([^，。；\n]{1,80})', policy=EXCLUSIVE_INVENTORY)


def _plausible_pending_answer(slot: str, message: str) -> bool:
    """Prevent unrelated free text from becoming a structured fact."""
    if slot == 'location':
        return bool(
            re.search(r'(?:中国大陆|大陆|.{2,12}(?:省|市|县|区))', message)
            or any(word in message for word in OUTSIDE_MAINLAND)
        )
    if slot == 'event_time':
        return bool(
            re.search(DATE_PATTERN, message)
            or re.search(r'上周|本周|这个月|本月|前几天|几天前|\d+\s*(?:天|个月|年)前', message)
        )
    if slot == 'amount':
        return bool(re.search(AMOUNT_PATTERN, message))
    return True


POSTPOSED_UNAVAILABLE = re.compile(
    r'(?:(?:我|本人|我们|这边|手头|目前|现在|暂时|一时|都|也|还)\s*)*'
    r'(?:拿不到|拿不到手|拿不着|没拿到|没有拿到|没法拿|拿不出|要不?到|不给我|无法取得)'
    r'\s*[了啊呀呢吧]?\s*$'
)


def _evidence_mention(text: str, name: str, siblings: tuple[str, ...] = ()) -> tuple[bool, bool]:
    """Return (mentioned, unavailable) without treating “没有借条” as possession."""
    terms = EVIDENCE_ALIASES.get(name, (name,))
    mentioned = any(term in text for term in terms)
    clauses = [part.strip() for part in re.split(r'[，,。；;\n]', text) if part.strip()]
    sibling_terms = tuple(
        term
        for other in siblings
        if other != name
        for term in EVIDENCE_ALIASES.get(other, (other,))
    )
    unavailable = False
    for term in terms:
        escaped = re.escape(term)
        for index, clause in enumerate(clauses):
            if term not in clause:
                continue
            # A negation before the material must stay inside the same clause
            # and may only contain a short modifier, not another evidence name.
            before = re.search(
                rf'(?:没有|找不到|无法提供|没(?:有|找到|拿到|保存|留住)?|无)'
                rf'\s*(?:(?:任何|相关|完整|原始)(?:的)?\s*)?{escaped}',
                clause,
            )
            match = re.search(escaped, clause)
            tail = clause[match.end():].strip() if match else ''
            # Postposed Chinese such as “借条我没有” is accepted only when the
            # rest of the clause is purely the negation. This prevents
            # “有转账记录，没有借条” from negating the transfer record.
            after = re.fullmatch(
                r'(?:(?:原件|材料|记录)\s*)?'
                r'(?:(?:我|本人|我们|这边|手头|目前|现在)\s*){0,2}'
                r'(?:(?:都|也|还|暂时|一时)\s*)?'
                r'(?:没有(?!问题)|没(?:有|了|找到|拿到|保存|留住)?|找不到|无法提供|无(?!问题|异议)'
                r'|拿不到|拿不着|没法拿|拿不出|要不?到)'
                r'[啊呀呢吧]?',
                tail,
            )
            # Natural speech often names the material first and only says “now I
            # cannot get it” in a following clause. That clause counts only
            # while no other material has been named in between, so
            # “有转账记录，我拿不到借条” still cannot negate the transfer record.
            if before or after or _later_clause_reports_unavailability(
                clauses[index + 1:], sibling_terms
            ):
                unavailable = True
                break
        if unavailable:
            break
    return mentioned, unavailable


def _later_clause_reports_unavailability(clauses: list[str], sibling_terms: tuple[str, ...]) -> bool:
    """Accept a trailing “I cannot get it” clause until another material appears."""
    for clause in clauses:
        if any(term in clause for term in sibling_terms) or '对方' in clause:
            return False
        if POSTPOSED_UNAVAILABLE.search(clause):
            return True
    return False


def _record_slot_assertion(
    state: CaseState,
    *,
    key: str,
    value: str,
    quote: str,
    assertor: str,
    source_ref: str,
    source_type: str,
    extraction_method: str,
    lifecycle: str = 'active',
) -> SlotAssertion:
    """Append a structured SlotAssertion to ``state.slot_assertions``."""
    snippet = ' '.join(str(quote).split())[:240]
    src_ref = source_ref or f'对话第{state.consultation.turns}轮'
    entry = SlotAssertion(
        key=key,
        value=value,
        assertor=assertor,
        turn=state.consultation.turns,
        source_ref=src_ref,
        quote=snippet,
        lifecycle=lifecycle,
        extraction_method=extraction_method,
        asserted_at=src_ref,
    )
    state.slot_assertions.setdefault(key, []).append(entry)
    return entry


def _supersede_user_assertion(
    state: CaseState, key: str, new_assertion: SlotAssertion
) -> None:
    """Mark prior user assertions for ``key`` as ``superseded`` by the new one.

    Only a user-asserted ``new_assertion`` is allowed to supersede a previous
    user assertion. Counterparty / authority assertions can never supersede a
    user-held slot.
    """
    if new_assertion.assertor != 'user':
        return
    for prior in state.slot_assertions.get(key, []):
        if prior.lifecycle != 'active' or prior.assertor != 'user':
            continue
        prior.lifecycle = 'superseded'
        prior.superseded_by = new_assertion.source_ref


def _withdraw_active_constraints(state: CaseState, message: str, source_ref: str) -> None:
    """Mark active user-asserted constraints as ``withdrawn`` if the
    withdrawal message retracts them.

    Targeted withdrawal: only clauses whose text matches the *subject* of the
    retraction are marked withdrawn. Unrelated clauses (e.g. "人在外地
    不能到场") stay active. A bare "我改变主意了" without a re-affirmation
    does nothing — round-19 probe 4.
    """
    subject = _withdrawal_subject(message)
    if subject is None:
        return
    for prior in state.slot_assertions.get('constraints', []):
        if prior.lifecycle != 'active' or prior.assertor != 'user':
            continue
        if not subject.search(prior.value):
            continue
        prior.lifecycle = 'withdrawn'
        prior.superseded_by = source_ref


def _withdrawal_subject(message: str):
    """Return a regex whose matches are the subject of the withdrawal, or
    ``None`` if the message does not specifically target a constraint."""
    if _NEGATE_NO_CONTACT_PATTERN.search(message):
        return re.compile(r'不要再.{0,6}(?:联系|沟通|协商|见面)|不要(?:见面|联系|协商)')
    if _GENERIC_RETRACTION_PATTERN.search(message) and _REAFFIRM_TAIL_PATTERN.search(message):
        # ``我改变主意了`` plus a re-affirmation. Target only the most recent
        # constraint; downstream code (recompute) already drops the slot if
        # it was the only one.
        return re.compile(r'.*')
    return None


def _recompute_constraints_after_withdrawal(state: CaseState) -> None:
    """Drop withdrawn constraint sentences from ``facts['constraints']`` so the
    routing layer no longer sees them.
    """
    active_values = [
        a.value for a in state.slot_assertions.get('constraints', [])
        if a.lifecycle == 'active' and a.assertor == 'user'
    ]
    new_value = '；'.join(active_values)
    if new_value:
        state.apply_facts({'constraints': new_value})
    else:
        # ``apply_facts`` ignores empty values; drop the slot entirely so the
        # routing layer no longer sees the prior constraint.
        state.facts.pop('constraints', None)
        if 'constraints' in state.missing_facts:
            state.missing_facts.remove('constraints')


def is_constraint_withdrawal(message: str) -> bool:
    """True iff the message retracts an active user constraint.

    Two patterns qualify:

    1. The message explicitly re-affirms contact (愿意再协商 / 重新协商 /
       撤销不要再联系). Round-17 probe 1.
    2. The message is a generic retraction ("改变主意", "不再限制",
       "不坚持那个") followed by a re-affirmation ("愿意", "可以…了",
       "还是想…"). Round-19 probe 4 shows this exact shape.
    """
    if _NEGATE_NO_CONTACT_PATTERN.search(message):
        return True
    if _GENERIC_RETRACTION_PATTERN.search(message) and _REAFFIRM_TAIL_PATTERN.search(message):
        return True
    return False


def save_fact(state: CaseState, key: str, value: str, quote: str, *, source_type='user_message', source_ref='', correction_context=False, assertor='user', extraction_method='consultation_intake') -> None:
    value = str(value).strip()[:1200]
    if not value:
        return
    old = state.facts.get(key)
    accepted = True
    if old and str(old) != value:
        label = LABELS.get(key, key)
        explicit_correction = source_type == 'user_message' and bool(
            correction_context or is_correction(quote)
        )
        if source_type == 'uploaded_file':
            accepted = False
            change = {'fact': label, 'previous': str(old), 'current': value,
                'source_ref': source_ref, 'status': '上传材料记载与当前事实不同，未自动覆盖，需核对原件、上下文及双方解释'}
            if change not in state.consultation.conflicts:
                state.consultation.conflicts.append(change)
        elif explicit_correction:
            change = {'fact': label, 'previous': str(old), 'current': value,
                'source_ref': source_ref, 'status': '用户明确更正，旧值仅保留为历史记录，当前方案采用本轮值'}
            if change not in state.consultation.corrections:
                state.consultation.corrections.append(change)
            state.consultation.conflicts = [
                item for item in state.consultation.conflicts if item.get('fact') != label
            ]
        elif key == 'procedure':
            # The procedural record accumulates. A later outcome advances the
            # case instead of contradicting the earlier procedural statement, so
            # it must not be raised as a fact the user has to reconcile. The
            # change itself is still reported through the per-turn decision delta.
            pass
        else:
            change = {'fact': label, 'previous': str(old), 'current': value,
                'source_ref': source_ref, 'status': '存在不同陈述，请核对'}
            if change not in state.consultation.conflicts:
                state.consultation.conflicts.append(change)
    # Counterparty / authority assertions must not overwrite a user-owned
    # slot. ``details`` is the legitimate channel for them; anything else is
    # routed to ``counterparty_claims`` and we do not touch ``facts``.
    if assertor != 'user' and key in _USER_OWNED_SLOTS and old and str(old) != value:
        accepted = False
        claim = CounterpartyClaim(
            slot=key,
            value=value,
            assertor=assertor,
            turn=state.consultation.turns,
            source_ref=source_ref or f'对话第{state.consultation.turns}轮',
            quote=' '.join(str(quote).split())[:240],
        )
        already_recorded = any(
            c.slot == claim.slot
            and c.value == claim.value
            and c.assertor == claim.assertor
            and c.source_ref == claim.source_ref
            for c in state.consultation.counterparty_claims
        )
        if not already_recorded:
            state.consultation.counterparty_claims.append(claim)
        # Still record the assertion so the audit trail is complete.
        _record_slot_assertion(
            state,
            key=key,
            value=value,
            quote=quote,
            assertor=assertor,
            source_ref=source_ref,
            source_type=source_type,
            extraction_method=extraction_method,
        )
        state.add_fact_provenance(key, source_type=source_type, source_ref=source_ref, quote=quote,
            extraction_method=extraction_method, accepted=False)
        return
    if accepted:
        state.apply_facts({key: value})
    new_assertion = _record_slot_assertion(
        state,
        key=key,
        value=value,
        quote=quote,
        assertor=assertor,
        source_ref=source_ref,
        source_type=source_type,
        extraction_method=extraction_method,
    )
    # User corrections supersede prior user assertions; counterparty / authority
    # assertions cannot supersede user-held slots (already blocked above for
    # user-owned slots).
    if correction_context and source_type == 'user_message':
        _supersede_user_assertion(state, key, new_assertion)
    state.add_fact_provenance(key, source_type=source_type, source_ref=source_ref, quote=quote,
        extraction_method=extraction_method, accepted=accepted)
    if key in state.consultation.declined_slots:
        state.consultation.declined_slots.remove(key)


def ingest_text(text: str, state: CaseState, *, source_type='user_message', source_ref='', contextual=True, scoped_inventory=False) -> None:
    dossier = state.consultation
    message = text.strip()
    if not message:
        return
    source_ref = source_ref or f'对话第{dossier.turns}轮'
    if not state.user_narrative and source_type == 'user_message':
        state.user_narrative = message
    pending = state.pending_fact_ids[0] if state.pending_fact_ids else ''
    unknown = bool(re.search(UNKNOWN_PATTERN, message))
    if contextual and unknown and pending and pending not in dossier.declined_slots:
        dossier.declined_slots.append(pending)
    sentences = [part.strip() for part in re.split(r'[，。；\n]', message) if part.strip()]
    extracted: set[str] = set()
    constraint_sentences: list[str] = []
    procedure_sentences: list[str] = []
    correction_context = source_type == 'user_message' and is_correction(message)

    def put(key, value, quote, *, assertor='user'):
        save_fact(state, key, value, quote, source_type=source_type, source_ref=source_ref,
            correction_context=correction_context, assertor=assertor)
        extracted.add(key)

    if source_type == 'user_message':
        role = client_perspective(state, message)
        if role['id'] != 'unconfirmed' and role['basis'].removeprefix('对话陈述：') in message:
            quote = role['basis'].removeprefix('对话陈述：')
            put('parties', quote, quote)

    # Keep a location phrase small. Never infer a particular court from a city.
    location = re.search(r'(?:我在|发生在|位于|地点[是：:]?)([^，。；\n]{2,35})', message)
    known_city = re.search(r'(?:北京|上海|天津|重庆|深圳|广州|杭州|南京|成都|武汉|西安|苏州|长沙|郑州|东莞|佛山|宁波|合肥|青岛|济南|厦门|福州|沈阳|大连|昆明|南宁|海口|贵阳|南昌|长春|哈尔滨)', message)
    if contextual and pending == 'location' and len(message) <= 40 and not re.search(r'[，。；\n？?]', message) and (known_city or any(word in message for word in OUTSIDE_MAINLAND) or re.search(r'.{2,8}(?:省|市|县|区)', message)):
        put('location', message, message)
    elif location and (any(word in location.group(1) for word in (*OUTSIDE_MAINLAND, '省', '市', '县', '区')) or known_city):
        put('location', location.group(1), location.group(0))
    elif known_city:
        put('location', known_city.group(0), known_city.group(0))
    for sentence in sentences:
        date_match = re.search(DATE_PATTERN, sentence)
        if date_match:
            if 'event_time' not in extracted:
                put('event_time', date_match.group(0), sentence)
            entry = TimelineEntry(date_text=date_match.group(0), description=sentence[:600], source_ref=source_ref, source_type=source_type, status='材料记载，待核实' if source_type == 'uploaded_file' else '用户陈述，待核实')
            if not any(item.description == entry.description and item.source_ref == source_ref for item in dossier.timeline):
                dossier.timeline.append(entry)
        if re.search(r'想.{0,10}(?:要回|追回|拿回|退|离婚|解决|申请|查)|希望|我要(?:离婚|追回|退款)|要求(?:退|赔)', sentence) and not wants_plan(sentence):
            put('goal', sentence, sentence)
        if re.search(
            r'低成本|预算|不想打官司|不想再.{0,8}(?:催款|协商|调解)|'
            r'不方便到场|无法到场|时间有限|不想影响关系|看不懂|不会操作|'
            r'不会用|听不清|看不清|需要.{0,4}帮|费用.{0,12}(?:以内|以下|不超过)|'
            r'(?:请)?不要再.{0,12}(?:联系|接触|沟通|协商|打电话)|人在外地|'
            r'不能.{0,6}(?:去)?(?:现场|到场)|费用.{0,5}(?:很少|有限)|'
            r'优先免费渠道|只接受书面沟通|书面沟通优先|不进行电话交涉|'
            r'(?:必须|希望).{0,4}尽快|不能长期拖延',
            sentence,
        ):
            constraint_sentences.append(sentence)
        affirmative_procedure = re.search(
            r'已经(?:起诉|投诉|报案|申请|协商)|收到.{0,10}(?:传票|通知|决定)',
            sentence,
        )
        negative_procedure = has_asserted(
            sentence,
            r'(?:没有|尚未|还没)(?:起诉|立案|投诉|报案|申请|协商)',
            policy=SENTENCE_BROAD,
        )
        corporate_inspection_refusal = (
            state.case_type == 'corporate'
            and re.search(
                r'(?:已经|此前|先后).{0,12}(?:书面)?(?:要求|申请)?'
                r'(?:查账|查阅).{0,20}(?:拒绝|不回复|未回复)',
                sentence,
            )
        )
        # A negative procedural outcome (dismissed, not accepted, revoked or
        # withdrawn) changes the case as much as filing it did.  Both an outcome
        # and a procedural object are required so substantive wording such as
        # “撤销合同” is not misread as procedure progress.
        outcome_token = r'驳回|不予受理|不予立案|不受理|不成立|未受理|撤销|撤回|终结'
        outcome_procedure = (
            has_asserted(sentence, outcome_token, policy=SENTENCE_BROAD)
            and re.search(
                r'申请|投诉|举报|仲裁|复议|诉讼|起诉|执行|调解|复核|决定|立案|请求|裁决|判决|认定',
                sentence,
            )
            and not has_negated(sentence, outcome_token, policy=SENTENCE_BROAD)
        )
        if (
            affirmative_procedure
            or negative_procedure
            or corporate_inspection_refusal
            or outcome_procedure
        ):
            procedure_sentences.append(sentence)
    if constraint_sentences:
        # If the user is withdrawing prior handling constraints, the prior
        # active assertions must be marked ``withdrawn`` *before* the new
        # value is composed; otherwise the new sentences would simply append
        # to the existing constraint string and keep old restrictions active.
        if source_type == 'user_message' and is_constraint_withdrawal(message):
            _withdraw_active_constraints(state, message, source_ref or f'对话第{dossier.turns}轮')
        new_constraint_sentences = list(constraint_sentences)
        # Each clause is recorded as its own SlotAssertion so per-clause
        # withdrawal can drop the negated clause without disturbing unrelated
        # ones (e.g. ``人在外地不能到场`` must survive a withdrawal of
        # ``不要再联系对方``). The visible fact string is the join of those
        # active clauses; recomputing it from the slot_assertions keeps the
        # string consistent with the lifecycle.
        for clause in dict.fromkeys(new_constraint_sentences):
            save_fact(state, 'constraints', clause, clause, source_type=source_type, source_ref=source_ref,
                correction_context=correction_context, assertor='user',
                extraction_method='constraint_clause')
        _recompute_constraints_after_withdrawal(state)
    elif source_type == 'user_message' and is_constraint_withdrawal(message):
        # Withdrawal without any new constraint sentences: still mark the
        # targeted subject as withdrawn so it stops influencing routing.
        _withdraw_active_constraints(state, message, source_ref or f'对话第{dossier.turns}轮')
        _recompute_constraints_after_withdrawal(state)
    procedure_retraction = correction_context and any(
        action in {CRIMINAL_URGENT_ACTION, DEADLINE_URGENT_ACTION}
        for action in retracted_urgent_actions(message)
    )
    if procedure_retraction:
        put('procedure', message, message)
    elif procedure_sentences:
        value = '；'.join(dict.fromkeys(procedure_sentences))
        put('procedure', value, value)
    if (
        'procedure' not in extracted
        and (
            re.search(
                r'(?:已经|此前|先后).{0,24}(?:协商|催款|催还|沟通|调解|投诉|申诉)'
                r'.{0,36}(?:拒绝|不回复|不理|失败|不成)',
                message,
            )
            or re.search(
                r'(?:协商|催款|催还|沟通|调解|投诉|申诉)'
                r'.{0,8}(?:\d+|[一二两三四五六七八九十]+)次'
                r'.{0,24}(?:拒绝|不回复|不理|失败|不成)',
                message,
            )
            or (
                state.case_type == 'corporate'
                and re.search(
                    r'(?:已经|此前|先后).{0,40}(?:查账|查阅)'
                    r'.{0,40}(?:拒绝|不回复|未回复)',
                    message,
                )
            )
        )
    ):
        put('procedure', message, message)
    counterparty_update = None
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    if profile.extra_detail_pattern is not None:
        # Practice areas (e.g. debt round 18) ask area-specific compound
        # questions whose answers land in ``details``. The shared pipeline
        # reads the pattern from the profile instead of inlining an
        # ``if case_type == 'debt':`` branch, so adding a new practice area
        # is a profile-only change.
        extra_details = [
            sentence
            for sentence in sentences
            if profile.extra_detail_pattern.search(sentence)
        ]
        if extra_details:
            value = '；'.join(dict.fromkeys(extra_details))
            put('details', value, value)
    # Later-turn positions from the other party are part of the dispute, not
    # conversational noise.  Persist them so every delivery path can ground the
    # focused reply and the exported report in the new fact.  Debt needs this
    # too: a denial of the principal must land in `details` instead of being
    # written into the user's own `amount` slot below.  Debt keeps a stricter
    # report-frame verb set so an already recorded position such as
    # “对方承认还欠4万元并拒绝还款” is not re-read as a fresh reply.
    # Capture across commas because the condition attached to a position often
    # follows in the next clause ("涨价，除非加价否则不发货").
    counterparty_timing = (
        r'.{0,8}(?:(?:刚|又|最新|现(?:在)?).{0,8})?'
        if dossier.turns > 1
        else r'.{0,8}(?:刚|又|最新|现(?:在)?).{0,120}'
    )
    # The counter-party verb set lives on the practice profile so debt can
    # narrow it (e.g. ``拒绝`` must not be re-read as a fresh reply on a
    # recorded position like “对方承认还欠4万元并拒绝还款”).
    counterparty_verbs = profile.counterparty_verbs
    counterparty_update = re.search(
        r'((?:对方|房东|租客|商家|平台|医院|供应商|公司|单位|家人|继承人|'
        r'中介|客服|人事|承办人员|保险理赔员|店铺经营者|物业|开发商|'
        r'保险人|承办机构|经营者|代理人|他们|'
        r'办案人员|民警|警官|交警|检察官|检察人员|执行法官|法官|书记员|'
        r'窗口工作人员|窗口|医务科|医务处|科室)'
        + counterparty_timing
        + r'(?:' + counterparty_verbs + r')'
        + r'.{0,120}?)(?=[，,](?:我|现在我)?(?:应该|该|能否|能不能|要不要|怎么)|[？?]|$)',
        message,
    )
    if not counterparty_update and dossier.turns > 1:
        counterparty_update = re.search(
            r'((?:收到(?:的)?回复(?:说|称|表示|写明)?|'
            r'回复(?:里|中)(?:说|称|表示|写着|写明))'
            r'.{0,180}?)(?=[，,](?:我|现在我)?'
            r'(?:应该|该|能否|能不能|要不要|怎么)|[？?]|$)',
            message,
        )
    if counterparty_update:
        value = counterparty_update.group(1).strip('，,。；; ')
        put('details', value, value, assertor='counterparty')
    amount_sentences = [sentence for sentence in sentences if re.search(AMOUNT_PATTERN, sentence)]
    if amount_sentences and not counterparty_update:
        put('amount', '；'.join(amount_sentences), '；'.join(amount_sentences))
    if contextual and pending and not unknown and not wants_plan(message) and not says_evidence_exhausted(message):
        # A short answer belongs to the previous question only when it is not
        # demonstrably a different slot (e.g. an amount supplied to a date question).
        if (
            pending in QUESTIONS
            and (pending in extracted or not extracted)
            and _plausible_pending_answer(pending, message)
        ):
            put(pending, state.facts.get(pending, message) if pending in extracted else message, message)
    if contextual and says_evidence_exhausted(message):
        state.mark_evidence_unavailable(list(state.pending_evidence_requests), exhausted=True)
        if 'evidence_inventory' not in dossier.declined_slots:
            dossier.declined_slots.append('evidence_inventory')
    if source_type == 'user_message':
        profile_evidence = PROFILES.get(state.case_type, PROFILES['general']).evidence
        siblings = tuple(item[0] for item in profile_evidence)
        only = asserted_exclusive_inventory(message)
        if (
            only
            and not scoped_inventory
            and re.search(r'转账|聊天|截图|合同|通知|材料|证据|视频|借条', only.group(1))
        ):
            # Explicitly exclusive inventory, not an assertion that missing
            # documents never existed or that supplied evidence proves the case.
            unavailable = []
            for name, *_ in profile_evidence:
                mentioned, denied = _evidence_mention(only.group(1), name, siblings)
                if mentioned and not denied:
                    state.add_evidence(name, source='user_message', notes=f'{source_ref}：用户陈述现有材料，尚未核实。')
                else:
                    unavailable.append(name)
            state.mark_evidence_unavailable(unavailable, exhausted=True)
        for name, *_ in profile_evidence:
            mentioned, denied = _evidence_mention(message, name, siblings)
            if denied:
                state.mark_evidence_unavailable([name])
            elif mentioned:
                state.add_evidence(name, source='user_message', notes=f'{source_ref}：用户称持有，尚未读取或核实。')
    location_text = str(state.facts.get('location', ''))
    # A direct geographic statement in this turn also covers a short answer.
    if any(word in location_text or word in message for word in OUTSIDE_MAINLAND):
        dossier.jurisdiction_status = 'OUTSIDE_MAINLAND'
    elif location_text:
        dossier.jurisdiction_status = 'MAINLAND_LOCATION_REPORTED'


def refresh_evidence(state: CaseState) -> None:
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    tasks = []
    for name, proves, how, alternative in profile.evidence:
        files = [f for f in state.uploaded_files if name in f.evidence_names]
        claimed = any(e.name == name for e in state.evidence)
        status = '已上传，内容与真实性待核对' if files else '用户称有，尚未上传' if claimed else '暂无法提供' if state.evidence_collection_exhausted or name in state.unavailable_evidence else '尚未提供'
        tasks.append(EvidenceTask(name=name, proves=proves, how=how, alternative=alternative, status=status, source_refs=[f.original_name for f in files]))
    state.consultation.evidence_tasks = tasks
    state.evidence_gaps = [EvidenceGap(element_id=f'{state.case_type}_{i}', name=t.proves, status=EvidenceStatus.PARTIAL if t.source_refs else EvidenceStatus.MISSING, evidence=t.source_refs, missing_evidence=[] if t.source_refs else [t.name], reason=t.status) for i, t in enumerate(tasks)]
    state.missing_evidence = [t.name for t in tasks if not t.source_refs]
    state.evidence_completeness = sum(bool(t.source_refs) for t in tasks) / max(1, len(tasks))


def urgent_actions(message: str, state: CaseState) -> list[str]:
    actions = []
    if _has_asserted_signal(message, r'家暴|正在.{0,4}(?:打|威胁)|打死|人身安全|持刀|跟踪'):
        actions.append(SAFETY_URGENT_ACTION)
    if state.case_type == 'criminal' and _has_asserted_signal(message, r'拘留|逮捕|被抓|看守所'):
        actions.append(CRIMINAL_URGENT_ACTION)
    imminent_document_deadline = (
        _has_asserted_urgent_deadline(message)
        and not re.search(r'已经过去|早已超过|半年前|去年', message)
    )
    if imminent_document_deadline or re.search(r'最后一天|马上到期|快过期', message):
        actions.append(DEADLINE_URGENT_ACTION)
    return actions


def _has_asserted_urgent_deadline(message: str) -> bool:
    pattern = (
        r'(?:今天|明天|后天|本周|这周).{0,16}(?:开庭|补正|提交|举证|答辩|到期|截止)'
        r'|(?:要求|须|需|应).{0,10}(?:\d+|[一二两三四五六七八九十]+)(?:个)?(?:工作)?日内'
        r'.{0,16}(?:开庭|补正|提交|举证|答辩|办理|回复)'
    )
    return _has_asserted_signal(message, pattern)


def _signal_states(message: str, pattern: str) -> list[bool]:
    """Backward-compatible signal-state list used by urgent-action code."""
    return [state for state in _signal_state_iter(message, pattern)]


def _signal_state_iter(message: str, pattern: str) -> list[bool]:
    compiled = re.compile(pattern)
    return [_DEFAULT_POLICY.is_asserted(message, m.start()) for m in compiled.finditer(message)]


def _has_asserted_signal(message: str, pattern: str) -> bool:
    return any(_signal_state_iter(message, pattern))


def _has_negated_signal(message: str, pattern: str) -> bool:
    return any(not state for state in _signal_state_iter(message, pattern))


def retracted_urgent_actions(message: str) -> set[str]:
    retracted = set()
    safety_pattern = r'家暴|正在.{0,4}(?:打|威胁)|打死|人身安全|持刀|跟踪'
    criminal_pattern = r'拘留|逮捕|被抓|看守所'
    if _has_negated_signal(message, safety_pattern) and not _has_asserted_signal(message, safety_pattern):
        retracted.add(SAFETY_URGENT_ACTION)
    if _has_negated_signal(message, criminal_pattern) and not _has_asserted_signal(message, criminal_pattern):
        retracted.add(CRIMINAL_URGENT_ACTION)
    if retracts_urgent_deadline(message):
        retracted.add(DEADLINE_URGENT_ACTION)
    return retracted


def retracts_urgent_deadline(message: str) -> bool:
    if _has_asserted_urgent_deadline(message):
        return False
    return bool(re.search(
        r'(?:不是|并非).{0,4}(?:今天|明天|后天|本周|这周).{0,12}(?:开庭|听证|补正|截止)'
        r'|(?:没有|并未|未曾|未|无)(?:明确|写明|载明|要求)?.{0,10}(?:期限|截止|开庭日期|补正日期)',
        message,
    ))
