"""Conversation wording for fact and evidence follow-ups."""

from __future__ import annotations

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState


NATURAL_FACT_QUESTIONS = {
    "has_written_contract": "你和公司签过书面劳动合同吗？",
    "contract_term_months": "合同约定的是多长期限？比如一年、三年，或者无固定期限。",
    "probation_period_months": "合同里写的试用期是多久？",
    "recruitment_conditions_disclosed": "入职时，公司有没有明确告诉你具体的录用条件？",
    "assessment_evidence_exists": "公司辞退你时，有没有给你看过考核标准或考核记录？",
    "termination_reason": "公司当时明确说的解除理由是什么？",
    "written_termination_notice": "公司有没有给你书面的解除通知？如果有，上面写的理由是什么？",
    "employer_rules_disclosed": "公司提到的规章制度，以前有没有向你公示过，或者让你签收过？",
    "disciplinary_evidence_exists": "公司有没有拿出材料来证明它所说的解除理由？",
    "employment_duration_months": "你在这家公司连续工作了多久？",
    "employment_start_date": "你实际是哪一天入职的？",
    "employment_end_date": "现在劳动关系已经结束了吗？如果结束了，大概是哪一天？",
    "monthly_salary": "解除前一年的平均月工资大概是多少？直接说“一万”或“10000元”都可以。",
    "unsigned_months": "从入职满一个月到补签合同或离职，中间大约有几个月？",
    "arrears_months": "公司拖欠的是哪几个月的工资？",
    "arrears_amount": "目前一共还欠你多少工资？",
    "employment_active": "你现在还在这家公司上班吗？",
    "payment_due_date": "你们通常约定每月几号发工资？",
    "work_schedule": "你平时几点上班、几点下班，每周休息几天？",
    "overtime_hours": "你大概有多少加班时间？工作日、休息日和法定节假日可以分开说。",
    "overtime_period": "这些加班主要发生在哪段时间？",
    "overtime_approved": "这些加班是公司安排、审批过，或者事后确认过的吗？",
    "termination_type": "这次劳动关系是公司辞退、你主动离职，还是双方协商解除？",
    "notice_months": "公司是提前三十天书面通知你的，还是另外多付了一个月工资？",
    "local_average_salary": "你知道当地上一年度的职工月平均工资吗？不知道也没关系。",
}


FOLLOW_UP_LEADS = {
    "contract_term_months": "好，签合同这一点我记下了。",
    "probation_period_months": "明白，我们再看合同里的试用期约定。",
    "recruitment_conditions_disclosed": "好的，我再确认一下入职时的情况。",
    "assessment_evidence_exists": "知道了。接下来要看公司说你不合格时有没有依据。",
    "termination_reason": "前面的情况清楚了，我还想确认公司当时的说法。",
    "written_termination_notice": "明白。再确认一下解除手续。",
    "monthly_salary": "前面的情况基本清楚了。为了估算可能涉及的金额，",
    "employment_duration_months": "好的。工作年限会影响后面的金额估算，",
    "unsigned_months": "明白。为了算清未签合同的时间，",
    "arrears_amount": "好的。为了把欠薪金额算清楚，",
    "overtime_hours": "了解。为了进一步估算加班费，",
}


REPHRASED_QUESTIONS = {
    "monthly_salary": (
        "刚才这个数字我没有识别准确，我换个问法：你平时一个月工资大约多少钱？"
        "像“一万”“10000元”或“每月一万”都可以。"
    ),
    "contract_term_months": "我换个更直接的问法：劳动合同写的是几年？如果是无固定期限，也可以直接这样说。",
    "probation_period_months": "我换个说法：合同上写了几个月试用期？",
    "employment_duration_months": "我再确认一下：从入职到现在或离职，一共工作了几年几个月？",
}


def compose_fact_follow_up(
    state: CaseState,
    fallback_questions: list[str],
    previous_pending_fact_ids: list[str],
    latest_user_message: str = "",
) -> str:
    """Turn a ranked fact request into a contextual, conversational reply."""

    fact_id = state.pending_fact_ids[0] if state.pending_fact_ids else ""
    fallback = fallback_questions[0] if fallback_questions else "请再补充一下相关情况。"
    question = NATURAL_FACT_QUESTIONS.get(fact_id, fallback)
    repeated = bool(fact_id and fact_id in previous_pending_fact_ids)

    generated_transition = state.reply_transition if not repeated else ""

    if repeated:
        reply = REPHRASED_QUESTIONS.get(
            fact_id,
            f"这条信息我还没确认下来，我换个更直接的问法：{question}如果确实不清楚，直接告诉我“不知道”就可以。",
        )
    elif generated_transition:
        separator = "" if generated_transition.endswith(("，", "：")) else " "
        reply = f"{generated_transition}{separator}{question}"
    elif not any(record.action == LegalAction.ASK_FACT for record in state.action_history):
        reply = f"我先和你一起把情况理清。{question}"
    else:
        lead = FOLLOW_UP_LEADS.get(fact_id)
        if lead:
            separator = "" if lead.endswith(("，", "：")) else " "
            reply = f"{lead}{separator}{question}"
        else:
            transitions = (
                "明白，这一点我记下了。",
                "好的，我们接着往下梳理。",
                "了解，再确认一个细节。",
            )
            follow_up_count = sum(
                record.action == LegalAction.ASK_FACT for record in state.action_history
            )
            reply = f"{transitions[follow_up_count % len(transitions)]}{question}"

    # Store exactly what the user saw so older serialized sessions remain recoverable.
    state.pending_questions = [question] if fact_id else fallback_questions
    return reply


def compose_evidence_follow_up(
    requests: list[str],
    latest_user_message: str = "",
    transition: str = "",
) -> str:
    """Ask for evidence without sounding like an abrupt system instruction."""

    items = "\n".join(f"- {name}" for name in requests)
    transition = transition or "情况我已经大致理清了。"
    separator = "" if transition.endswith(("，", "：")) else " "
    return (
        f"{transition}{separator}接下来最好把关键材料固定下来，你可以先看看手头有没有：\n\n"
        f"{items}\n\n有的话可以直接上传；暂时没有也没关系，告诉我现有的材料就行。"
    )
