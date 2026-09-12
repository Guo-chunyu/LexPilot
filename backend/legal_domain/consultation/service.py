"""Shared non-labor consultation turn for LangGraph, API and the offline runner."""

import re

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState
from ._spans import SENTENCE_BROAD, has_asserted
from .intake import (
    LABELS, QUESTIONS, UNKNOWN_PATTERN, has_explicit_question, ingest_text, refresh_evidence,
    retracted_urgent_actions, says_evidence_exhausted, urgent_actions, wants_next_step_only,
    wants_plan,
)
from .profiles import PROFILES, domain_label, identify_domains, route_case
from .wording import WordingComposer
from .reporting import build_consultation_report
from .research import research_case
from .semantic import enrich_consultation
from .authorities import update_rule_references
from .knowledge import retrieve_for_case
from .perspective import case_profile, client_perspective
from .decision_delta import decision_delta_reply_lines


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


_AMOUNT_UNIT = re.compile(r'[0-9零一二两三四五六七八九十百千万点.,]+\s*(?:万元|元|万)')


def _recorded_amount(state) -> str:
    """The bare amount the user stated, never a value borrowed from one case.

    The stored fact may carry surrounding wording ("付了1800元"); only the
    number and unit belong in a sentence of ours.
    """
    raw = str(state.facts.get('amount', '')).strip()
    match = _AMOUNT_UNIT.search(raw)
    return match.group(0).strip() if match else ''


def _recorded_surname(state) -> str:
    """The surname the user actually gave for a counterparty contact, if any."""
    match = re.search(r'可能姓([\u4e00-\u9fff])', str(state.facts.get('parties', '')))
    return match.group(1) if match else ''


def _follow_up_analysis(message: str, state, profile) -> str:
    """Answer the current turn instead of replaying the first-turn opening."""
    if state.case_type == 'debt' and '赠与' in message:
        return (
            f'对方现在提出的是“赠与抗辩”。重点不是重复证明转账发生，'
            '而是证明双方当时存在借款合意：把转账前后的完整微信、款项用途、还款约定、'
            '催款内容，以及对方曾承认欠款或讨论还款的原始上下文按时间对应。'
            '不要只截取单句；如果没有直接写“借款”，转账备注、双方关系和催还后的回复'
            '只能作为需要结合上下文核对的间接材料，不能据此保证结果。'
        )
    if (
        state.case_type == 'consumer'
        and re.search(r'转(?:给|让)|转卡', message)
        and re.search(r'不(?:能|予|同意)?退|拒绝退款|不能退款', message)
    ):
        amount = _recorded_amount(state)
        amount_phrase = f'并把{amount}的付款' if amount else '并把你的付款'
        return (
            f'商家提出“转给别人使用”只是新的替代处理意见，'
            '不等于你的退款请求已经解决。先保存这次回复的完整原文、时间和商家账号，'
            f'{amount_phrase}、当前余额、剩余服务以及门店停业信息对应起来；'
            '如果你不接受转卡，应在书面退款请求中明确写明不接受该替代方案，'
            '要求商家说明经营主体、未履行金额和拒绝退款的依据。'
        )
    if state.case_type == 'consumer' and re.search(
        r'(?:怎么|如何|哪里|怎样).{0,8}(?:查询|查找|确认|核实)?.{0,8}(?:经营主体|商家主体|对方主体)'
        r'|(?:查询|查找|确认|核实).{0,8}(?:经营主体|商家主体|对方主体)',
        message,
    ):
        surname = _recorded_surname(state)
        surname_phrase = f'“可能姓{surname}”' if surname else '一个姓氏'
        return (
            f'先不要用{surname_phrase}直接确定退款义务主体，姓名只能作为联系人线索。'
            '按这个顺序核对：先查看支付记录中的商户全称和商户订单号，再看会员协议、'
            '发票、收据、平台订单、门店公示的营业执照或公众号认证信息；取得名称或统一社会信用代码后，'
            '到国家企业信用信息公示系统核对登记主体和当前登记状态。'
            '如果仍只有门店简称，可在投诉材料中同时提交门店地址、付款记录和聊天账号，'
            '明确说明主体待核实，请平台或属地市场监管部门根据交易线索协助确认。'
        )
    if (
        state.case_type == 'consumer'
        and '投诉' in message
        and '起诉' in message
    ):
        amount = _recorded_amount(state)
        amount_phrase = f'按目前{amount}的预付消费争议' if amount else '按目前这笔预付消费争议'
        return (
            f'{amount_phrase}，建议先投诉：这一步成本较低，也便于取得处理回执，'
            '同时把诉讼材料作为后备，不必把两条路线理解成只能二选一。'
            '先确认实际收款和经营主体，整理付款、余额、停业及拒绝退款记录后提交平台或12315投诉；'
            '投诉不能自动带来退款，也不能替代对期限和管辖的核对。若投诉未解决，再根据主体状态、'
            '送达线索和投入评估是否起诉；发现主体注销、失联或财产异常时，应尽早人工核对正式救济。'
        )
    current_details = str(state.facts.get('details', '')).strip()
    if current_details and current_details in message:
        return (
            f'你本轮补充的争点是“{current_details}”。'
            f'{profile.response} 先保存这次回复的完整原文、时间和上下文，'
            '再将对方的新说法与合同、付款、履行及其他已有材料逐项对应；'
            '目前先按争议主张核对，不能只凭对方单方表述直接下结论。'
        )
    if re.search(r'更正|说错了|实际是|准确说', message):
        return (
            f'这次更正已替换当前方案采用的对应事实，旧说法只保留在更正记录中。'
            '下面只列更正造成的方案变化和当前最相关的一步。'
        )
    if re.search(r'对方.{0,20}(?:说|称|主张|回复|否认|拒绝|不承认)', message):
        return (
            f'这次对方的新说法已作为待核实的争点记录。'
            f'{profile.response} 先保留完整原文和上下文，再把对方说法与已有材料逐项对应。'
        )
    if re.search(r'材料|证据|准备什么|怎么准备', message):
        available = [
            task.name for task in state.consultation.evidence_tasks
            if task.status in {'用户称有，尚未上传', '已上传，内容与真实性待核对'}
        ]
        named = '、'.join(available[:3]) or '本轮提到的原始材料'
        return (
            f'先围绕当前争点整理{named}，保留完整内容、形成时间和来源；'
            '材料能证明什么、不能证明什么要分开写，缺失部分使用报告中的合法替代方式。'
        )
    return (
        f'我已按这次消息重新核对当前事实、材料和路线。'
        f'{profile.response} 下面只展示本轮变化与最相关的一步，完整更新保留在右侧报告。'
    )


def _answered_slot_acknowledgement(slot: str, value: str) -> str:
    """Acknowledge a short interview answer without replaying case guidance."""
    if slot == 'location':
        impact = '后续会按该地区核对办理渠道和地区性规则，但暂不据此直接确定具体管辖机关。'
    elif slot == 'event_time':
        impact = '后续会用这个时间核对规则版本和可能涉及的程序期限；仍需确认它对应停业、通知还是其他关键事件。'
    else:
        impact = '后续问题和方案会使用这项信息，不再按未知处理。'
    return f'{LABELS.get(slot, slot)}我按“{value}”记录。{impact}'


def _most_relevant_follow_up_step(message: str, report: dict) -> dict:
    """Pick one existing grounded action for a compact later-turn reply."""
    steps = report.get('action_plan', [])
    if not steps:
        return {}
    if re.search(r'材料|证据|准备什么|怎么准备', message) and len(steps) > 1:
        return steps[1]
    if re.search(r'起诉|仲裁|正式程序|下一步', message):
        return next(
            (step for step in steps if re.search(r'正式|提交|仲裁|起诉', step.get('title', ''))),
            steps[min(2, len(steps) - 1)],
        )
    if re.search(r'对方|抗辩|回复|拒绝|否认|不承认', message):
        return steps[-1]
    return steps[0]


_DETAILED_PLAN_PATTERN = (
    r'详细(?:的)?(?:实施)?方案|完整(?:的)?(?:实施)?方案|实施方案|'
    r'写清.{0,24}(?:步骤|证据|材料|渠道|不顺利)|'
    r'(?:方案|步骤).{0,10}(?:详细|完整)'
)


def _wants_detailed_plan(message: str) -> bool:
    """A detailed-plan request, but not a refusal of one.

    "不用重复完整方案" contains the same keywords as a real request, so the
    match has to go through the shared negation/scope policy instead of a bare
    search. Otherwise asking for a single step hands back the whole plan.
    """
    if not wants_plan(message):
        return False
    return has_asserted(message, _DETAILED_PLAN_PATTERN, policy=SENTENCE_BROAD)


def _detailed_plan_lines(report: dict) -> list[str]:
    lines = ['**按现有事实，详细实施方案**']
    for index, step in enumerate(report.get('action_plan', []), 1):
        instructions = '；'.join(step.get('instructions', []))
        materials = '、'.join(step.get('materials', [])) or '按受理渠道要求核对'
        lines += [
            f'{index}. **{step["title"]}**',
            f'   - **何时办理**：{step.get("suggested_date", "")}；{step.get("when", "")}',
            f'   - **办理渠道**：{step.get("channel", "")}',
            f'   - **证据与材料**：{materials}',
            f'   - **具体操作**：{instructions}',
            f'   - **完成标志**：{step.get("completion", "")}',
            f'   - **不顺利时**：{step.get("fallback", "")}',
        ]
    return lines


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
    detailed_plan_request = _wants_detailed_plan(message)
    next_step_only = wants_next_step_only(message)
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
        label = LABELS.get(previous_slot, previous_slot)
        pieces.append(f'明白，“{label}”暂时记为待核实，不会反复追问同一个问题。')
    if state.evidence_collection_exhausted:
        pieces.append('现有材料就按这些整理，不会再重复让你补同样的材料；缺的部分会列出合法替代办法。')
    is_follow_up = dossier.turns > 1
    answered_previous_slot = bool(previous_slot and previous_slot in state.facts)
    narrative_domains = identify_domains(state.user_narrative)
    domain_reframed = bool(
        re.search(r'更正|说错了|其实是|实际是|准确说', message)
        and narrative_domains
        and narrative_domains[0] not in {'general', state.case_type}
    )
    if detailed_plan_request:
        dossier.reply_mode = 'detailed_plan'
        current_analysis = (
            '下面按当前已记录的事实与材料直接展开完整实施方案；'
            '尚未确认的地区、主体或期限会明确保留为核对项，不用单步摘要代替方案。'
        )
    elif answered_previous_slot and not has_explicit_question(message):
        dossier.reply_mode = 'acknowledgement'
        current_analysis = _answered_slot_acknowledgement(
            previous_slot, str(state.facts[previous_slot])
        )
    elif had_plan or (is_follow_up and not domain_reframed):
        dossier.reply_mode = 'follow_up'
        current_analysis = dossier.analysis or _follow_up_analysis(message, state, profile)
    else:
        dossier.reply_mode = 'opening'
        current_analysis = dossier.analysis or _case_opening(state, profile)
    dossier.analysis = current_analysis
    dossier.reply_mode_history.append(dossier.reply_mode)
    pieces.append(current_analysis)
    pieces.append('')
    if rules and dossier.turns == 1:
        rule = rules[0]
        pieces += [f'可以先核对这条规则：{rule["summary"]}（[{rule["law_name"]}{rule["article"]}]({rule["source_url"]})）。是否适用还要结合发生时间和具体事实。', '']
    produce = explicit_plan or had_plan or not missing or dossier.turns >= 6
    composer = WordingComposer(dossier)
    if produce:
        report = build_consultation_report(state)
        if not detailed_plan_request:
            pieces += decision_delta_reply_lines(report.get('decision_delta', {}))
        pieces.append(report['strategy_comparison']['decision_reason'])
        if detailed_plan_request:
            dossier.reply_granularity = 'detailed_plan'
            pieces += _detailed_plan_lines(report)
            pieces += [
                '',
                '右侧“报告”已同步更新，可继续下载 Word / PDF；聊天中的步骤与当前报告使用同一份事实状态。',
            ]
        elif next_step_only or had_plan:
            dossier.reply_granularity = 'single_step'
            step = _most_relevant_follow_up_step(message, report)
            if step:
                pieces.append(
                    f'{composer.single_step_lead()}**{step["title"]}**'
                    f'（建议{step["suggested_date"]}开始）：{step["instructions"][0]}'
                )
            pieces += ['', composer.report_pointer()]
        else:
            dossier.reply_granularity = 'plan_summary'
            pieces += [composer.plan_intro(), *[f'{i}. **{s["title"]}**（建议{s["suggested_date"]}开始）：{s["instructions"][0]}' for i, s in enumerate(report['action_plan'], 1)], '', '完整方案已同步到右侧“报告”，可下载 Word / PDF：包含办理入口、具体操作、材料、费用比较、期限核对和沟通草稿。日程是行动建议，不能替代法定期限。后续补充材料会更新方案。']
        action = LegalAction.GENERATE_DOCUMENT
        reason = '先提供现有信息下可执行的阶段方案，保留事实和法源核验缺口。'
    else:
        if not answered_previous_slot:
            dossier.reply_granularity = 'interview'
            task = _next_evidence_task(dossier.evidence_tasks)
            pieces += [f'现在可以先做的是：{task.alternative if task.status == "暂无法提供" else task.how} 这些材料主要用于说明{task.proves}。']
        else:
            # A bare answer to the pending question must not also trigger the
            # "prepare this material now" paragraph.
            dossier.reply_granularity = 'acknowledge_only'
        action = LegalAction.ASK_FACT
        reason = '已记录本轮短答并继续接谈。' if answered_previous_slot else '按地区、时间、诉求和本领域关键争点逐轮接谈。'
    if missing:
        slot = missing[0]
        # Keep canonical common slots; only the area-specific question can be rephrased.
        question = (dossier.follow_up or profile.question) if slot == 'details' else QUESTIONS[slot]
        already_asked = question in dossier.question_history
        if already_asked:
            question = profile.question if slot == 'details' else QUESTIONS[slot]
        state.pending_fact_ids = [slot]
        state.pending_questions = [question]
        if question not in dossier.question_history:
            dossier.question_history.append(question)
        if slot == 'evidence_inventory' and not state.evidence_collection_exhausted:
            state.pending_evidence_requests = [t.name for t in dossier.evidence_tasks if not t.source_refs][:2]
            action = LegalAction.REQUEST_EVIDENCE if not produce else action
        if had_plan and already_asked:
            pieces += ['', f'{LABELS.get(slot, slot)}还缺，不过这不影响先回答你这轮的问题，需要时再补。']
        else:
            pieces += ['', question]
    else:
        pieces += ['', '可以继续告诉我对方的新回复、补充材料，或者说明希望先推进哪一步。']
    if not produce:
        dossier.stage = '事实与证据接谈'
    state.record_action(action, reason, 'general_consultation', f'{domain_label(state.case_type)}：已整理 {len(state.facts)} 项事实、{len(dossier.evidence_tasks)} 项取证任务。')
    return {'case_state': state, 'reply': _join_pieces(pieces), 'requires_user': True}


def _join_pieces(pieces: list[str]) -> str:
    """Join reply pieces without leaving stacked blank lines."""
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(pieces)).strip()
