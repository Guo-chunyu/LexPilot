"""Grounded intake and contextual short answers, with no remote document upload."""

import re

from backend.legal_rl.state import CaseState, EvidenceGap, EvidenceStatus
from .models import EvidenceTask, TimelineEntry
from .profiles import OUTSIDE_MAINLAND, PROFILES


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
EXHAUSTED_PATTERN = r'没有(?:更多|其他|其它|别的)|(?:剩下|其余|其他|其它).{0,4}(?:没有|没了)|就这些|没有了|没证据|没有证据|暂时没有'


def wants_plan(text: str) -> bool:
    return bool(re.search(PLAN_PATTERN, text))


def save_fact(state: CaseState, key: str, value: str, quote: str, *, source_type='user_message', source_ref='') -> None:
    value = str(value).strip()[:1200]
    if not value:
        return
    old = state.facts.get(key)
    if old and str(old) != value:
        change = {'fact': LABELS.get(key, key), 'previous': str(old), 'current': value, 'source_ref': source_ref, 'status': '存在不同陈述，请核对'}
        if change not in state.consultation.conflicts:
            state.consultation.conflicts.append(change)
    state.apply_facts({key: value})
    state.add_fact_provenance(key, source_type=source_type, source_ref=source_ref, quote=quote, extraction_method='consultation_intake')
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

    def put(key, value, quote):
        save_fact(state, key, value, quote, source_type=source_type, source_ref=source_ref)
        extracted.add(key)

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
        if re.search(r'低成本|预算|不想打官司|不方便到场|时间有限|不想影响关系|费用.{0,5}(?:以内|以下|不超过)', sentence):
            put('constraints', sentence, sentence)
        if re.search(r'已经(?:起诉|投诉|报案|申请|协商)|收到.{0,10}(?:传票|通知|决定)|尚未|还没(?:投诉|起诉|协商)', sentence):
            put('procedure', sentence, sentence)
    amount_sentences = [sentence for sentence in sentences if re.search(AMOUNT_PATTERN, sentence)]
    if amount_sentences:
        put('amount', '；'.join(amount_sentences), '；'.join(amount_sentences))
    if contextual and pending and not unknown and not wants_plan(message) and not re.search(EXHAUSTED_PATTERN, message):
        # A short answer belongs to the previous question only when it is not
        # demonstrably a different slot (e.g. an amount supplied to a date question).
        if pending in QUESTIONS and (pending in extracted or not extracted):
            put(pending, state.facts.get(pending, message) if pending in extracted else message, message)
    if contextual and re.search(EXHAUSTED_PATTERN, message):
        state.mark_evidence_unavailable(list(state.pending_evidence_requests), exhausted=True)
        if 'evidence_inventory' not in dossier.declined_slots:
            dossier.declined_slots.append('evidence_inventory')
    if source_type == 'user_message':
        for name, *_ in PROFILES.get(state.case_type, PROFILES['general']).evidence:
            if re.search(rf'(?:没有|没|找不到|无).{{0,6}}{re.escape(name)}', message):
                state.mark_evidence_unavailable([name])
            elif name in message:
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
    if re.search(r'家暴|正在.{0,4}(?:打|威胁)|打死|人身安全|持刀|跟踪', message) and not re.search(r'没有家暴|没有人身安全问题', message):
        actions.append('先到安全地点并联系当地警方；正在遭受伤害时优先求助和就医，不要为了取证单独接触对方。')
    if state.case_type == 'criminal' and re.search(r'拘留|逮捕|被抓|看守所', message):
        actions.append('尽快联系当地刑事律师或法律援助机构，带上通知书核实措施类型、起算日期、办案单位和依法会见途径；不要找关系、串供或删记录。')
    if re.search(r'明天.{0,5}(?:开庭|到期)|今天.{0,5}到期|最后一天|马上到期|快过期', message):
        actions.append('先核对文书载明的截止日期与送达凭证，今天就向受理机关或当地律师确认提交和补正方式；不要等材料全部齐了才处理期限。')
    return actions
