"""Shared non-labor consultation turn for LangGraph, API and the offline runner."""

import re

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState
from .intake import (
    QUESTIONS, UNKNOWN_PATTERN, ingest_text, refresh_evidence,
    retracted_urgent_actions, says_evidence_exhausted, urgent_actions, wants_plan,
)
from .profiles import PROFILES, domain_label, identify_domains, route_case
from .reporting import build_consultation_report
from .research import research_case
from .semantic import enrich_consultation
from .authorities import update_rule_references
from .knowledge import retrieve_for_case
from .perspective import case_profile, client_perspective


def _case_opening(state, profile) -> str:
    """Give a direct case-aware answer when semantic AI is unavailable."""
    text = state.user_narrative + '\n' + '\n'.join(str(value) for value in state.facts.values())
    role = client_perspective(state)['id']
    if state.case_type == 'debt' and re.search(r'没有借条|没(?:有)?借条|只有.{0,20}(?:转账|聊天)', text):
        if role == 'debtor':
            return '没有借条不代表债务当然不存在，也不代表对方主张的金额都正确。你先按每笔实际到账、已经偿还的本金和利息逐项对账，保存还款记录及双方对款项性质的完整沟通；如已收到法院材料，优先按文书要求核对答辩和举证节点。'
        return '没有借条不等于可以直接下结论。先把每笔转账的时间、金额、收款人，与能说明款项用途、还款约定和催还情况的完整聊天逐笔对应；真正需要补的是“这笔钱为什么是借款、是否已经到期、还剩多少”，不是补造一张借条。'
    if state.case_type == 'housing' and re.search(r'押金|扣款', text):
        if role == 'landlord':
            return '押金不能不经核算就当然全部没收。先把欠租、欠费、正常损耗和有证据的实际损坏分别列账，用入住与退房记录、维修凭证和合同条款说明每项扣款；无争议的余额应与争议项目分开处理。'
        return '房东只说“有损坏”，还不足以算清应扣多少。先让对方列出具体损坏位置、合同依据、交接前后记录和实际费用；你这边保留退房、钥匙交还、房屋状态及押金支付记录，把正常使用痕迹与确有损坏的项目分开核对。'
    if state.case_type == 'consumer' and re.search(r'关门|停业|跑路|会员卡|预付', text):
        return '先确认是门店停业、迁址，还是经营主体已经异常，并立即固定余额、剩余服务次数和停业信息。退款请求要写清“谁收了款、还有多少未履行、要求怎样处理”；平台投诉或监管处理可以帮助留痕，但不能自动等同于钱已经退回。'
    if state.case_type == 'family' and re.search(r'离婚|孩子|房子|房产', text):
        return '这件事要拆成三部分：是否能协商离婚、孩子目前由谁持续照护、房屋何时取得及资金和贷款来源。房屋只登记在对方名下这一点还不足以单独判断处理结果；先保存婚姻、照护、购房付款和贷款材料，再分别确定你的目标。'
    if state.case_type == 'criminal' and re.search(r'拘留|逮捕|被抓|看守所', text):
        return '现在最重要的不是先猜结果，而是根据通知书核对办案机关、涉嫌事项、采取措施和时间，并尽快联系当地刑事律师或法律援助机构了解依法会见等程序。家属只整理真实材料，不找关系、不串供、不删除记录。'
    if state.case_type == 'contract' and re.search(r'没交货|不交货|违约|解除|退款', text):
        return '先把合同约定、你方已履行、对方未履行和催告经过按时间对齐，再判断是要求继续履行、补救、解除退款还是赔偿损失；这些请求的条件和证据不同，不宜一开始全部堆在一起。'
    if state.case_type == 'administrative':
        return '先看决定书写明的作出机关、具体处理、送达方式和救济告知，不要只按聊天中的日期估算期限。把你不服的事实认定、程序或处理幅度分别列出，再核对是复议、诉讼还是需要先走特定程序。'
    if state.case_type == 'corporate' and re.search(r'股东|股权|查账|分红|出资|清算', text):
        return '先用登记信息、章程、股东名册或出资材料确认你的股东身份和权利范围，再把查阅、分红、退出或追责拆成不同请求。尤其是查账，应写清查阅目的、材料范围和此前被拒绝的经过，不能把公司责任直接算到老板个人名下。'
    if state.case_type == 'intellectual_property':
        return '先别急着只做下架投诉：在页面可能消失前，完整保存网址、账号、发布时间、使用方式和可见交易信息，同时整理你的创作源文件、首次发表或授权链。权利归属与对方实际使用要分别证明，赔偿金额也不能只凭浏览量直接推定。'
    if state.case_type == 'inheritance':
        return '先确定哪些财产确属被继承人、是否存在共同财产和债务，再谈如何分配。遗嘱案件还要优先保管原件，并核对形成时间、形式、见证情况及当时行为能力；只凭某位家属转述，暂时不能判断遗嘱是否有效。'
    if state.case_type == 'traffic':
        return '先持续治疗并保存病历、医嘱和票据，同时取得事故认定及保险信息。责任比例、治疗关联和具体损失是三个不同问题；伤情和后续治疗尚未明确时，慎重签署一次性结清或放弃后续请求的文件。'
    if state.case_type == 'medical':
        return '先保证后续治疗，并尽快申请复制、必要时依法保存完整病历，把具体诊疗行为、告知内容和损害结果按时间对应。不良结果本身不能直接证明医疗过错，是否存在过错及因果关系通常还需专业审查。'
    if state.case_type == 'tort':
        return '先制止仍在持续的伤害，并保存原始页面、账号、网址、完整上下文和时间信息；不要为了反击再次扩散对方或自己的隐私。之后再分别核对行为人身份、内容真伪、传播范围和能够证明的实际影响。'
    if state.case_type == 'enforcement':
        return '胜诉不等于款项会自动到账。先核对生效文书、履行期限、已经履行的部分和是否已申请执行，再按合法来源整理被执行人的财产线索；已经立案的，应通过案号补充线索并留存提交记录。'
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
    retracted = retracted_urgent_actions(message)
    if retracted:
        dossier.urgent_actions = [action for action in dossier.urgent_actions if action not in retracted]
    dossier.urgent_actions = list(dict.fromkeys([*dossier.urgent_actions, *urgent_actions(message, state)]))
    refresh_evidence(state)
    update_rule_references(state)
    # Keep related domains without changing the established primary area mid-case.
    if len(message) > 25:
        related = [d for d in identify_domains(message) if d not in ('general', 'labor_dispute')]
        dossier.domain_ids = list(dict.fromkeys([state.case_type, *dossier.domain_ids, *related]))[:3]
    exhausted_statement = says_evidence_exhausted(message)
    explicit_plan = wants_plan(message) or exhausted_statement
    # The generation call must see this turn's retrieval, not last turn's status.
    retrieve_for_case(state)
    if dossier.jurisdiction_status != 'OUTSIDE_MAINLAND':
        research_case(state)
    previous_domain = state.case_type
    if not re.search(UNKNOWN_PATTERN, message) and not exhausted_statement:
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
