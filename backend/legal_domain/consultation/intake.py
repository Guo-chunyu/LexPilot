"""Grounded intake and contextual short answers, with no remote document upload."""

import re

from backend.legal_rl.state import CaseState, EvidenceGap, EvidenceStatus
from .models import EvidenceTask, TimelineEntry
from .profiles import OUTSIDE_MAINLAND, PROFILES
from .perspective import client_perspective


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
}

SAFETY_URGENT_ACTION = '先到安全地点并联系当地警方；正在遭受伤害时优先求助和就医，不要为了取证单独接触对方。'
CRIMINAL_URGENT_ACTION = '尽快联系当地刑事律师或法律援助机构，带上通知书核实措施类型、起算日期、办案单位和依法会见途径；不要找关系、串供或删记录。'
DEADLINE_URGENT_ACTION = '先核对文书载明的截止日期与送达凭证，今天就向受理机关或当地律师确认提交和补正方式；不要等材料全部齐了才处理期限。'


def wants_plan(text: str) -> bool:
    return bool(re.search(PLAN_PATTERN, text))


def says_evidence_exhausted(text: str) -> bool:
    """Accept an exhaustion statement only when the matched phrase is asserted."""
    for match in re.finditer(EXHAUSTED_PATTERN, text):
        clause_start = max(text.rfind(mark, 0, match.start()) for mark in '，,。；;\n') + 1
        prefix = text[clause_start:match.start()]
        if re.search(r'(?:不是|并非|不代表|不等于|不能说|并不意味着)\s*$', prefix):
            continue
        return True
    return False


def asserted_exclusive_inventory(text: str):
    """Return an asserted “only these materials” match, excluding scope negation."""
    for match in re.finditer(r'(?:只有|仅有)([^，。；\n]{1,80})', text):
        clause_start = max(text.rfind(mark, 0, match.start()) for mark in '，,。；;\n') + 1
        prefix = text[clause_start:match.start()]
        if re.search(r'(?:不是|并非|并不是)\s*$', prefix):
            continue
        return match
    return None


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


def _evidence_mention(text: str, name: str) -> tuple[bool, bool]:
    """Return (mentioned, unavailable) without treating “没有借条” as possession."""
    terms = EVIDENCE_ALIASES.get(name, (name,))
    mentioned = any(term in text for term in terms)
    clauses = [part.strip() for part in re.split(r'[，,。；;\n]', text) if part.strip()]
    unavailable = False
    for term in terms:
        escaped = re.escape(term)
        for clause in clauses:
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
                r'(?:(?:原件|材料|记录)\s*)?(?:(?:我|本人|手头|目前|现在)\s*)?'
                r'(?:没有(?!问题)|没(?:有|了|找到|拿到|保存|留住)?|找不到|无法提供|无(?!问题|异议))'
                r'[啊呀呢吧]?',
                tail,
            )
            if before or after:
                unavailable = True
                break
        if unavailable:
            break
    return mentioned, unavailable


def save_fact(state: CaseState, key: str, value: str, quote: str, *, source_type='user_message', source_ref='', correction_context=False) -> None:
    value = str(value).strip()[:1200]
    if not value:
        return
    old = state.facts.get(key)
    accepted = True
    if old and str(old) != value:
        label = LABELS.get(key, key)
        explicit_correction = source_type == 'user_message' and bool(correction_context or
            re.search(r'而是|其实是|实际是|准确说是|应该是|应当是|更正(?:一下|为|成)?|说错了', quote)
            or re.search(r'(?:我|本人)不是[^，,；;]{1,20}[，,；;]\s*(?:我)?是', quote)
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
        else:
            change = {'fact': label, 'previous': str(old), 'current': value,
                'source_ref': source_ref, 'status': '存在不同陈述，请核对'}
            if change not in state.consultation.conflicts:
                state.consultation.conflicts.append(change)
    if accepted:
        state.apply_facts({key: value})
    state.add_fact_provenance(key, source_type=source_type, source_ref=source_ref, quote=quote,
        extraction_method='consultation_intake', accepted=accepted)
    if key in state.consultation.declined_slots:
        state.consultation.declined_slots.remove(key)


def ingest_text(text: str, state: CaseState, *, source_type='user_message', source_ref='', contextual=True) -> None:
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
    correction_context = source_type == 'user_message' and bool(
        re.search(r'而是|其实是|实际是|准确说是|应该是|应当是|更正(?:一下|为|成)?|说错了', message)
        or re.search(r'(?:我|本人)不是[^，,；;]{1,20}[，,；;]\s*(?:我)?是', message)
    )

    def put(key, value, quote):
        save_fact(state, key, value, quote, source_type=source_type, source_ref=source_ref,
            correction_context=correction_context)
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
        if re.search(r'低成本|预算|不想打官司|不方便到场|无法到场|时间有限|不想影响关系|看不懂|不会操作|不会用|听不清|看不清|需要.{0,4}帮|费用.{0,5}(?:以内|以下|不超过)', sentence):
            constraint_sentences.append(sentence)
        affirmative_procedure = re.search(
            r'已经(?:起诉|投诉|报案|申请|协商)|收到.{0,10}(?:传票|通知|决定)',
            sentence,
        )
        negative_procedure = re.search(
            r'(?<!不是)(?<!并非)(?:没有|尚未|还没)(?:起诉|立案|投诉|报案|申请|协商)',
            sentence,
        )
        if affirmative_procedure or negative_procedure:
            procedure_sentences.append(sentence)
    if constraint_sentences:
        value = '；'.join(dict.fromkeys(constraint_sentences))
        put('constraints', value, value)
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
                r'(?:已经|此前|先后).{0,24}(?:协商|催款|催还|沟通|调解)'
                r'.{0,36}(?:拒绝|不回复|不理|失败|不成)',
                message,
            )
            or re.search(
                r'(?:协商|催款|催还|沟通|调解)'
                r'.{0,8}(?:\d+|[一二两三四五六七八九十]+)次'
                r'.{0,24}(?:拒绝|不回复|不理|失败|不成)',
                message,
            )
        )
    ):
        put('procedure', message, message)
    if state.case_type == 'debt':
        # The area-specific debt question asks about repayment terms, partial
        # performance and competing explanations for the transfer. Persist
        # those answers as `details` even when they appear in separate clauses,
        # otherwise the generic intake loop asks the same compound question.
        debt_details = [
            sentence
            for sentence in sentences
            if re.search(
                r'约定.{0,20}(?:还款|归还|偿还|还)|'
                r'(?:已还|还过|已偿还|偿还过).{0,20}(?:元|万|块|部分|剩)|'
                r'(?:赠与|货款|借款用途|款项用途)',
                sentence,
            )
        ]
        if debt_details:
            value = '；'.join(dict.fromkeys(debt_details))
            put('details', value, value)
    amount_sentences = [sentence for sentence in sentences if re.search(AMOUNT_PATTERN, sentence)]
    if amount_sentences:
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
        only = asserted_exclusive_inventory(message)
        if only and re.search(r'转账|聊天|截图|合同|通知|材料|证据|视频|借条', only.group(1)):
            # Explicitly exclusive inventory, not an assertion that missing
            # documents never existed or that supplied evidence proves the case.
            unavailable = []
            for name, *_ in PROFILES.get(state.case_type, PROFILES['general']).evidence:
                mentioned, denied = _evidence_mention(only.group(1), name)
                if mentioned and not denied:
                    state.add_evidence(name, source='user_message', notes=f'{source_ref}：用户陈述现有材料，尚未核实。')
                else:
                    unavailable.append(name)
            state.mark_evidence_unavailable(unavailable, exhausted=True)
        for name, *_ in PROFILES.get(state.case_type, PROFILES['general']).evidence:
            mentioned, denied = _evidence_mention(message, name)
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
    states = []
    for match in re.finditer(pattern, message):
        clause_start = max(message.rfind(mark, 0, match.start()) for mark in '，,。；;\n') + 1
        prefix = message[clause_start:match.start()]
        negated = bool(re.search(
            r'(?:(?:没有|并未|未曾|不是|并非|并不|无需|不需|不存在|尚未|未被|无须)'
            r'[^，,。；;但]{0,6}|[不非无未])$',
            prefix,
        ))
        states.append(not negated)
    return states


def _has_asserted_signal(message: str, pattern: str) -> bool:
    return any(_signal_states(message, pattern))


def _has_negated_signal(message: str, pattern: str) -> bool:
    return any(not state for state in _signal_states(message, pattern))


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
