"""Shared action executor for the LangGraph workflow and offline demo."""

from __future__ import annotations

from dataclasses import dataclass
import re

from backend.agents.ask_fact import ask_fact_node
from backend.agents.dialogue import (
    compose_evidence_follow_up,
    compose_fact_follow_up,
    wants_multiple_questions,
    NATURAL_FACT_QUESTIONS,
)
from backend.agents.judge import evaluate_case_state
from backend.agents.opponent import simulate_opponent
from backend.agents.report import build_final_report
from backend.legal_domain.labor.case_search import search_similar_cases
from backend.legal_domain.labor.compensation import estimate_from_state
from backend.legal_domain.labor.evidence_gap import detect_evidence_gaps
from backend.legal_domain.labor.facts import extract_labor_facts
from backend.legal_domain.labor.legal_search import search_law_for_state
from backend.legal_rl.actions import ACTION_TO_NODE, LegalAction
from backend.legal_rl.policy import LegalPolicy, PolicyDecision, RuleBasedPolicy
from backend.legal_rl.state import CaseState, EvidenceStatus


@dataclass
class ActionExecution:
    result: str
    reply: str = ""
    requires_user: bool = False


def execute_action(
    state: CaseState,
    decision: PolicyDecision,
    latest_user_message: str = "",
) -> ActionExecution:
    """Execute one policy action against the real CaseState."""

    action = decision.action
    previous_pending_fact_ids = list(state.pending_fact_ids)
    state.pending_questions = []
    state.pending_fact_ids = []
    state.pending_evidence_requests = []

    if action == LegalAction.ASK_FACT:
        # The user may ask to be asked several things at once ("一次说两条").
        question_limit = 2 if wants_multiple_questions(latest_user_message) else 1
        questions = ask_fact_node(state, limit=question_limit)
        reply = compose_fact_follow_up(
            state,
            questions,
            previous_pending_fact_ids,
            latest_user_message,
        )
        selected = next(
            (item for item in state.inquiry_candidates if item.fact_id in state.pending_fact_ids),
            None,
        )
        result = f"提出 {len(questions)} 个关键问题。"
        if selected:
            result += f" 信息价值评分 {selected.score:.2f}：{selected.reason}"
        execution = ActionExecution(
            result=result,
            reply=reply,
            requires_user=True,
        )
    elif action == LegalAction.REQUEST_EVIDENCE:
        requests = _select_evidence_requests(state)
        if requests:
            state.pending_evidence_requests = requests
            reply = compose_evidence_follow_up(
                requests,
                latest_user_message,
                state.reply_transition,
                state,
            )
            execution = ActionExecution(
                result=f"请求 {len(requests)} 项证据。",
                reply=reply,
                requires_user=True,
            )
        else:
            state.evidence_collection_exhausted = True
            execution = ActionExecution(result="没有尚可追问的新材料，继续按现有材料处理。")
    elif action == LegalAction.SEARCH_LAW:
        state.retrieved_laws = search_law_for_state(state)
        detect_evidence_gaps(state)
        linked = sum(bool(law.matched_elements) for law in state.retrieved_laws)
        execution = ActionExecution(
            result=f"检索到 {len(state.retrieved_laws)} 条时效有效法源，其中 {linked} 条已关联案件要件。"
        )
    elif action == LegalAction.SEARCH_CASE:
        state.retrieved_cases = search_similar_cases(state.dispute_type)
        if not state.retrieved_cases:
            state.retrieved_cases = [{
                "case_id": "synthetic_pending",
                "dispute_type": state.dispute_type,
                "human_reviewed": False,
                "note": "暂无已审核同类案例，仅保留检索接口。",
            }]
        execution = ActionExecution(result=f"检索到 {len(state.retrieved_cases)} 个同类案例记录。")
    elif action == LegalAction.SIMULATE_OPPONENT:
        analysis = simulate_opponent(state)
        execution = ActionExecution(result=f"形成 {len(analysis['arguments'])} 项对方可能抗辩。")
    elif action == LegalAction.VERIFY:
        verdict = evaluate_case_state(state)
        execution = ActionExecution(result=f"Judge can_stop={verdict.can_stop}: {verdict.reason}")
    elif action == LegalAction.CALCULATE:
        state.compensation_estimate = estimate_from_state(state.facts, state.dispute_type)
        execution = ActionExecution(result=state.compensation_estimate.get("message", "完成赔偿估算。"))
    elif action == LegalAction.GENERATE_DOCUMENT:
        report = build_final_report(state)
        if report.generation_status == "VERIFIED":
            execution = ActionExecution(result="已生成通过证据链核验的结构化法律行动方案。")
        else:
            execution = ActionExecution(
                result="材料未达到可验证生成门槛，仅生成信息缺口清单。",
                reply=report.verification.get("refusal_reason", "当前信息不足，系统暂不生成确定性结论。"),
            )
    elif action == LegalAction.STOP:
        if state.judge_result and state.judge_result.can_stop:
            if not state.final_report:
                build_final_report(state)
            state.done = True
            execution = ActionExecution(
                result="案件信息达到阶段性输出门槛。",
                reply=_report_reply(state),
            )
        else:
            execution = ActionExecution(
                result="Judge 未允许停止。",
                reply="当前信息仍不足，系统不会提前输出确定性法律结论。",
            )
    else:
        state.done = True
        state.escalated = True
        if state.evidence_collection_exhausted and not state.final_report:
            build_final_report(state)
        execution = ActionExecution(
            result=(
                "用户已确认无更多材料，形成信息不足的阶段性结果。"
                if state.evidence_collection_exhausted
                else "转人工复核。"
            ),
            reply=(
                _evidence_exhausted_reply(state)
                if state.evidence_collection_exhausted
                else "案件存在无法由当前自动流程可靠处理的缺失或冲突，建议转劳动法律师人工复核。"
            ),
        )

    state.record_action(
        action=action,
        reason=decision.reason,
        node=ACTION_TO_NODE[action],
        result=execution.result,
    )
    return execution


def prepare_labor_turn(message: str, state: CaseState) -> CaseState:
    """Apply specialist and shared intake extraction for every labor entry point."""
    # The shared consultation path advances this counter itself. The specialist
    # path must do the same, otherwise later labour turns are still treated as
    # first turns by the shared extractors and by fact provenance labels.
    state.consultation.turns += 1
    case = extract_labor_facts(message, state)
    # The shared intake owns material availability, later-turn counterparty
    # positions, constraints and the procedural record for every domain. Running
    # it unconditionally keeps the labour specialist path from silently dropping
    # those, while `contextual=False` leaves the interview's own pending-answer
    # semantics to `extract_labor_facts`. While the interview is still waiting
    # for an answer, the turn is a scoped answer and must not be read as a global
    # "these are all my materials" statement.
    from backend.legal_domain.consultation.intake import (
        ingest_text,
        retracted_urgent_actions,
        urgent_actions,
    )
    ingest_text(message, case, contextual=False, scoped_inventory=bool(case.pending_questions))
    # Round-47: the shared consultation path computes urgent actions; the labour
    # specialist path did not, so a labour case with violence or an imminent
    # deadline showed no safety warning at all. Mirror the shared behaviour.
    retracted = retracted_urgent_actions(message)
    if retracted:
        case.consultation.urgent_actions = [
            action for action in case.consultation.urgent_actions if action not in retracted
        ]
    case.consultation.urgent_actions = list(dict.fromkeys([
        *case.consultation.urgent_actions,
        *urgent_actions(message, case),
    ]))
    detect_evidence_gaps(case)
    return case


class LexPilotEngine:
    """Offline-compatible runner that mirrors the LangGraph policy loop."""

    def __init__(self, policy: LegalPolicy | None = None, max_auto_steps: int = 12) -> None:
        self.policy = policy or RuleBasedPolicy()
        self.max_auto_steps = max_auto_steps

    def process(self, message: str, state: CaseState | dict | None = None) -> dict:
        case = CaseState.from_value(state)
        from backend.legal_domain.consultation.profiles import route_case
        from backend.legal_domain.consultation.service import process_consultation
        from backend.legal_domain.consultation.perspective import uses_general_consultation
        route_case(message, case)
        if uses_general_consultation(case, message):
            return process_consultation(message, case)
        case = prepare_labor_turn(message, case)
        from backend.legal_domain.consultation.intake import wants_plan, wants_next_step_only
        # A request for only the first step must win over a full plan: a message
        # such as "不用重复完整方案，只告诉我第一步该做什么" contains both keywords,
        # and answering it with the whole plan repeats what the user refused.
        if wants_next_step_only(message):
            return labor_single_step(case)
        if wants_plan(message):
            return labor_stage_plan(case, message)
        reply = ""
        execution = ActionExecution(result="")
        for _ in range(self.max_auto_steps):
            decision = self.policy.decide(case)
            execution = execute_action(case, decision, message)
            if execution.reply:
                reply = execution.reply
            if execution.requires_user or case.done:
                break
        else:
            decision = PolicyDecision(
                action=LegalAction.ESCALATE_HUMAN,
                reason="单次调用超过自动动作上限。",
            )
            execution = execute_action(case, decision, message)
            reply = execution.reply
        return {
            "case_state": case,
            "reply": reply or execution.result,
            "requires_user": execution.requires_user,
        }


def labor_stage_plan(state: CaseState, message: str = "") -> dict:
    """An explicit request may obtain a provisional plan before the stop gate."""
    report = build_final_report(state)
    state.pending_questions = []
    state.pending_fact_ids = []
    state.pending_evidence_requests = []
    state.done = False
    state.record_action(LegalAction.GENERATE_DOCUMENT, "用户请求按现有材料先形成具体行动步骤。", "generate_document", "已整理取证、办理渠道、材料、时间节点和替代路线。")
    from backend.legal_domain.consultation.wording import WordingComposer
    composer = WordingComposer(state.consultation)
    steps_text = '\n'.join(
        f'{i}. **{step["title"]}**：{step["instructions"][0]}'
        for i, step in enumerate(report.action_plan, 1)
    )
    limit = 2 if wants_multiple_questions(message) else 1
    follow_up = _proactive_information_block(state, limit=limit)
    urgent = _urgent_block(state)
    reply = (
        (urgent + '\n' if urgent else '')
        + f'{composer.stage_plan_intro()}\n\n{steps_text}\n\n'
        f'{composer.stage_plan_outro()}\n\n{follow_up}'
    )
    return {"case_state": state, "reply": reply, "requires_user": True}


def labor_single_step(state: CaseState) -> dict:
    """Answer a request for only the current first step, not the whole plan."""
    if not state.final_report:
        build_final_report(state)
    report = state.final_report or {}
    steps = report.get('action_plan', []) if report else []
    state.pending_questions = []
    state.pending_fact_ids = []
    state.pending_evidence_requests = []
    state.done = False
    state.record_action(
        LegalAction.GENERATE_DOCUMENT,
        "用户只问当前第一步，给出聚焦的单步答案。",
        "generate_document",
        "已给出当前最优先的一步。",
    )
    urgent = _urgent_block(state)
    prefix = urgent + '\n' if urgent else ''
    if not steps:
        return {
            "case_state": state,
            "reply": (
                prefix
                + "现在最先做的是把已知事实和手头材料固定下来："
                "导出工资流水、保存工作群聊天和考勤截图，并记清入职日期和离职日期。\n\n"
                + _proactive_information_block(state, limit=1)
            ),
            "requires_user": True,
        }
    step = steps[0]
    lines = [f'现在最先做这一步：**{step.get("title", "")}**']
    if step.get('instructions'):
        lines.append(f'- 具体操作：{step["instructions"][0]}')
    if step.get('channel'):
        lines.append(f'- 办理渠道：{step["channel"]}')
    return {
        "case_state": state,
        "reply": prefix + "\n".join(lines) + "\n\n" + _proactive_information_block(state, limit=1),
        "requires_user": True,
    }


def _urgent_block(state: CaseState) -> str:
    """Surface urgent actions in labour replies (the shared path already does this)."""
    urgent = list(dict.fromkeys(state.consultation.urgent_actions))
    if not urgent:
        return ''
    return '\n'.join(['**先处理紧急事项**', *(f'- {item}' for item in urgent), ''])


def _proactive_information_block(state: CaseState, limit: int = 1) -> str:
    """Close a plan / report reply by either asking for the next missing facts or
    telling the user the report is already complete enough.

    The user report showed two gaps: (1) after handing back a plan the system
    never asked for the still-missing facts, so the user had to ask themselves;
    (2) when the report was already usable the user was never told. This block
    owns both behaviours.
    """
    missing = [
        fact_id for fact_id in state.missing_facts
        if fact_id not in state.consultation.declined_slots
    ]
    complete_head = (
        '现有信息已经比较完整，可以形成较完整的阶段性报告；'
        '后续拿到新材料可以继续补充，报告会同步更新。'
    )
    if not missing:
        return complete_head
    questions = _rank_missing_questions(state, limit)
    if not questions:
        return complete_head
    body = '\n'.join(f'{index}. {question}' for index, question in enumerate(questions, 1))
    if state.fact_completeness >= 0.8:
        return f'{complete_head}\n\n如方便，也可再补充：\n{body}'
    return f'为了把报告补完整，还想请你补充：\n{body}'


def _rank_missing_questions(state: CaseState, limit: int = 1) -> list[str]:
    """Rank the highest-value missing facts and naturalise their wording.

    ``select_questions`` also stores ``pending_fact_ids`` / ``pending_questions``,
    so the user's next message is matched to the answer.
    """
    if not state.missing_facts:
        return []
    from backend.legal_domain.labor.inquiry import select_questions
    questions = select_questions(state, limit=limit)
    return [
        NATURAL_FACT_QUESTIONS.get(fact_id, question)
        for fact_id, question in zip(state.pending_fact_ids, questions)
    ]


def _select_evidence_requests(state: CaseState, limit: int = 2) -> list[str]:
    if state.evidence_collection_exhausted:
        return []
    requests: list[str] = []
    unavailable = set(state.unavailable_evidence)
    ordered = sorted(
        state.evidence_gaps,
        key=lambda gap: {
            EvidenceStatus.CONFLICT: 0,
            EvidenceStatus.MISSING: 1,
            EvidenceStatus.PARTIAL: 2,
            EvidenceStatus.PROVEN: 3,
        }[gap.status],
    )
    for gap in ordered:
        if gap.status == EvidenceStatus.PROVEN:
            continue
        for name in gap.missing_evidence:
            if name not in unavailable and name not in requests:
                requests.append(name)
            if len(requests) >= limit:
                return requests
    return requests


def _evidence_exhausted_reply(state: CaseState) -> str:
    available = list(dict.fromkeys(item.name for item in state.evidence))
    unavailable = list(dict.fromkeys(state.unavailable_evidence))
    lines = [
        "明白，现有材料就这些。我已经记录下来，不会再重复让你补同样的材料。",
        "",
        "我已按目前的事实和已上传文件完成阶段性梳理；没有取得的材料只会标记为“暂未提供”，不会被当成已经证明。",
    ]
    if available:
        lines.append("- 已纳入分析：" + "、".join(available[:6]))
    if unavailable:
        lines.append("- 暂未提供：" + "、".join(unavailable[:6]))
    lines.extend([
        "",
        "现有证据还不足以支持确定性结论，阶段报告已保留当前分析和缺口。后续如果拿到新材料，可以继续补充；准备仲裁前建议再由劳动法律师核对一次。",
    ])
    return "\n".join(lines)


def _report_reply(state: CaseState) -> str:
    report = state.final_report
    acknowledgement = (
        "明白，现有材料就这些。我已经记录下来，不会再重复让你补同样的材料。\n\n"
        if state.evidence_collection_exhausted
        else ""
    )
    urgent = _urgent_block(state)
    return (
        (urgent + '\n' if urgent else '')
        + acknowledgement
        + "已按现有事实和材料形成结构化阶段性行动方案。\n\n"
        f"- 事实完整度：{state.fact_completeness:.0%}\n"
        f"- 证据完整度：{state.evidence_completeness:.0%}\n"
        f"- 法律确定性：{state.legal_confidence:.0%}\n"
        f"- 总体置信度：{state.overall_confidence:.0%}\n\n"
        + "\n".join(f"- {item}" for item in report.get("recommended_actions", []))
        + "\n\n"
        + _proactive_information_block(state, limit=1)
    )
