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
    if not re.search(UNKNOWN_PATTERN, message) and not re.search(EXHAUSTED_PATTERN, message):
        enrich_consultation(message, state, include_plan=explicit_plan or had_plan)
    else:
        dossier.analysis = ''
        dossier.follow_up = ''
        dossier.tailored_steps = []
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    refresh_evidence(state)
    rules = update_rule_references(state)
    if dossier.jurisdiction_status != 'OUTSIDE_MAINLAND':
        research_case(state)
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
    pieces.append(dossier.analysis or profile.focus)
    pieces.append('')
    if rules:
        rule = rules[0]
        pieces += [f'**可先核对的规则**：{rule["summary"]}（[{rule["law_name"]}{rule["article"]}]({rule["source_url"]})）；是否适用还要结合发生时间和具体事实。', '']
    produce = explicit_plan or had_plan or not missing or dossier.turns >= 6
    if produce:
        report = build_consultation_report(state)
        pieces += ['**按现有信息，先这样推进**', *[f'{i}. **{s["title"]}**：{s["instructions"][0]}' for i, s in enumerate(report['action_plan'], 1)], '', '完整方案已同步到右侧“报告”：包括取证方法、办理渠道、材料、费用、期限核对、对方抗辩和沟通草稿。事实或法源尚未核验的部分已标明，后续补充会更新方案。']
        action = LegalAction.GENERATE_DOCUMENT
        reason = '先提供现有信息下可执行的阶段方案，保留事实和法源核验缺口。'
    else:
        task = next((t for t in dossier.evidence_tasks if not t.source_refs and t.status != '暂无法提供'), dossier.evidence_tasks[0])
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
