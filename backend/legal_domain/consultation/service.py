"""Shared non-labor consultation turn for LangGraph, API and the offline runner."""

import re

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState
from .intake import QUESTIONS, UNKNOWN_PATTERN, EXHAUSTED_PATTERN, ingest_text, refresh_evidence, urgent_actions, wants_plan
from .profiles import PROFILES, domain_label, identify_domains, route_case
from .reporting import build_consultation_report
from .research import research_case
from .semantic import enrich_consultation
from .authorities import update_rule_references
from .knowledge import retrieve_for_case
from .perspective import case_profile


def _case_opening(state, profile) -> str:
    """Give a direct case-aware answer when semantic AI is unavailable."""
    text = state.user_narrative + '\n' + '\n'.join(str(value) for value in state.facts.values())
    if state.case_type == 'debt' and re.search(r'没有借条|没(?:有)?借条|只有.{0,20}(?:转账|聊天)', text):
        return '没有借条不等于可以直接下结论。先把每笔转账的时间、金额、收款人，与能说明款项用途、还款约定和催还情况的完整聊天逐笔对应；真正需要补的是“这笔钱为什么是借款、是否已经到期、还剩多少”，不是补造一张借条。'
    if state.case_type == 'housing' and re.search(r'押金|扣款', text):
        return '房东只说“有损坏”，还不足以算清应扣多少。先让对方列出具体损坏位置、合同依据、交接前后记录和实际费用；你这边保留退房、钥匙交还、房屋状态及押金支付记录，把正常使用痕迹与确有损坏的项目分开核对。'
    if state.case_type == 'consumer' and re.search(r'关门|停业|跑路|会员卡|预付', text):
        return '先确认是门店停业、迁址，还是经营主体已经异常，并立即固定余额、剩余服务次数和停业信息。退款请求要写清“谁收了款、还有多少未履行、要求怎样处理”；平台投诉或监管处理可以帮助留痕，但不能自动等同于钱已经退回。'
    if state.case_type == 'family' and re.search(r'离婚|孩子|房子|房产', text):
        return '这件事要拆成三部分：是否能协商离婚、孩子目前由谁持续照护、房屋何时取得及资金和贷款来源。房屋只登记在对方名下这一点还不足以单独判断处理结果；先保存婚姻、照护、购房付款和贷款材料，再分别确定你的目标。'
    if state.case_type == 'criminal' and re.search(r'拘留|逮捕|被抓|看守所', text):
        return '现在最重要的不是先猜结果，而是根据通知书核对办案机关、涉嫌事项、采取措施和时间，并尽快联系当地刑事律师或法律援助机构了解依法会见等程序。家属只整理真实材料，不找关系、不串供、不删除记录。'
    if state.case_type == 'contract' and re.search(r'没交货|不交货|违约|解除|退款', text):
        return '先把合同约定、你方已履行、对方未履行和催告经过按时间对齐，再判断是要求继续履行、补救、解除退款还是赔偿损失；这些请求的条件和证据不同，不宜一开始全部堆在一起。'
    return profile.focus


def _next_evidence_task(tasks):
    """Prefer material the user says exists over repeating an unavailable request."""
    return next((task for task in tasks if task.source_refs),
        next((task for task in tasks if task.status == '用户称有，尚未上传'),
        next((task for task in tasks if task.status == '尚未提供'), tasks[0])))


def process_consultation(message: str, state: CaseState) -> dict:
    route_case(message, state)
    dossier = state.consultation
    dossier.turns += 1
    state.ai_calls_this_turn = 0
    had_plan = bool(state.final_report) or any(record.action == LegalAction.GENERATE_DOCUMENT for record in state.action_history)
    previous_slot = state.pending_fact_ids[0] if state.pending_fact_ids else ''
    ingest_text(message, state)
    dossier.urgent_actions = list(dict.fromkeys([*dossier.urgent_actions, *urgent_actions(message, state)]))
    refresh_evidence(state)
    update_rule_references(state)
    # Keep related domains without changing the established primary area mid-case.
    if len(message) > 25:
        related = [d for d in identify_domains(message) if d not in ('general', 'labor_dispute')]
        dossier.domain_ids = list(dict.fromkeys([state.case_type, *dossier.domain_ids, *related]))[:3]
    explicit_plan = wants_plan(message) or bool(re.search(EXHAUSTED_PATTERN, message))
    # The generation call must see this turn's retrieval, not last turn's status.
    retrieve_for_case(state)
    if dossier.jurisdiction_status != 'OUTSIDE_MAINLAND':
        research_case(state)
    previous_domain = state.case_type
    if not re.search(UNKNOWN_PATTERN, message) and not re.search(EXHAUSTED_PATTERN, message):
        enrich_consultation(message, state, include_plan=explicit_plan or had_plan)
    else:
        dossier.analysis = ''
        dossier.follow_up = ''
        dossier.tailored_steps = []
        dossier.grounded_claims = []
        dossier.generation_audit = {}
    if state.case_type != previous_domain:
        # A semantic reclassification invalidates retrieval for the prior area.
        retrieve_for_case(state)
        dossier.grounded_claims = []
        dossier.tailored_steps = []
    profile = case_profile(state)
    refresh_evidence(state)
    rules = update_rule_references(state)
    state.legal_confidence = 0.0  # Discovery has not established applicability.
    state.legal_issues = [profile.focus]
    state.opponent_analysis = {'arguments': [profile.defense], 'response': profile.response}
    slots = ['location', 'event_time', 'goal', 'parties', 'details', 'procedure', 'evidence_inventory', 'constraints']
    missing = [slot for slot in slots if slot not in state.facts and slot not in dossier.declined_slots]
    if state.uploaded_files:
        missing = [slot for slot in missing if slot != 'evidence_inventory']
    state.missing_facts = missing
    state.fact_completeness = len([slot for slot in slots if slot in state.facts]) / len(slots)
    state.pending_fact_ids = []
    state.pending_questions = []
    state.pending_evidence_requests = []
    state.done = False
    state.escalated = False
    pieces = []
    if dossier.urgent_actions:
        pieces += ['**先处理紧急事项**', *[f'- {s}' for s in dossier.urgent_actions], '']
    if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        pieces += ['你描述的情况涉及中国大陆以外的地区或涉外因素，需要先核对当地适用法和程序；目前先整理事实与材料。', '']
    if previous_slot in dossier.declined_slots:
        pieces.append('明白，这项先记为待核实，不会反复追问同一个问题。')
    if state.evidence_collection_exhausted:
        pieces.append('现有材料就按这些整理，不会再重复让你补同样的材料；缺的部分会列出合法替代办法。')
    current_analysis = dossier.analysis or _case_opening(state, profile)
    dossier.analysis = current_analysis
    pieces.append(current_analysis)
    pieces.append('')
    if rules:
        rule = rules[0]
        pieces += [f'**可先核对的规则**：{rule["summary"]}（[{rule["law_name"]}{rule["article"]}]({rule["source_url"]})）；是否适用还要结合发生时间和具体事实。', '']
    produce = explicit_plan or had_plan or not missing or dossier.turns >= 6
    if produce:
        report = build_consultation_report(state)
        pieces += ['**建议先走的路线**：' + report['strategy_comparison']['decision_reason'],
            '**按现有信息，先这样推进**', *[f'{i}. **{s["title"]}**（建议{s["suggested_date"]}开始）：{s["instructions"][0]}' for i, s in enumerate(report['action_plan'], 1)], '', '完整方案已同步到右侧“报告”，可下载 Word / PDF：包含办理入口、具体操作、材料、费用比较、期限核对和沟通草稿。日程是行动建议，不能替代法定期限。后续补充材料会更新方案。']
        action = LegalAction.GENERATE_DOCUMENT
        reason = '先提供现有信息下可执行的阶段方案，保留事实和法源核验缺口。'
    else:
        task = _next_evidence_task(dossier.evidence_tasks)
        pieces += [f'**现在可以先做**：{task.alternative if task.status == "暂无法提供" else task.how} 这些材料主要用于说明{task.proves}。']
        action = LegalAction.ASK_FACT
        reason = '按地区、时间、诉求和本领域关键争点逐轮接谈。'
    if missing:
        slot = missing[0]
        # Keep canonical common slots; only the area-specific question can be rephrased.
        question = (dossier.follow_up or profile.question) if slot == 'details' else QUESTIONS[slot]
        if question in dossier.question_history:
            question = profile.question if slot == 'details' else QUESTIONS[slot]
        state.pending_fact_ids = [slot]
        state.pending_questions = [question]
        dossier.question_history.append(question)
        if slot == 'evidence_inventory' and not state.evidence_collection_exhausted:
            state.pending_evidence_requests = [t.name for t in dossier.evidence_tasks if not t.source_refs][:2]
            action = LegalAction.REQUEST_EVIDENCE if not produce else action
        pieces += ['', '**接下来最需要确认的是**：' + question]
    else:
        pieces += ['', '可以继续告诉我对方的新回复、补充材料，或者说明希望先推进哪一步。']
    if not produce:
        dossier.stage = '事实与证据接谈'
    state.record_action(action, reason, 'general_consultation', f'{domain_label(state.case_type)}：已整理 {len(state.facts)} 项事实、{len(dossier.evidence_tasks)} 项取证任务。')
    return {'case_state': state, 'reply': '\n'.join(pieces), 'requires_user': True}
