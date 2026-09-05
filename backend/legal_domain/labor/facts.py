"""Deterministic labor fact extraction used before optional LLM enrichment."""

from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.state import CaseState


EVIDENCE_KEYWORDS = {
    "劳动合同": ("我有劳动合同", "合同原件", "上传劳动合同", "提供劳动合同"),
    "工资流水": ("工资流水", "银行流水", "工资转账"),
    "微信聊天记录": ("微信", "聊天记录"),
    "解除通知": ("解除通知", "辞退通知", "书面通知"),
    "社保记录": ("社保记录", "社保缴费"),
    "考勤记录": ("考勤", "打卡记录"),
    "考核记录": ("考核记录", "绩效记录", "试用期考核"),
    "加班审批": ("加班审批", "加班申请"),
}

NUMBER_PATTERN = r"[0-9零〇一二两三四五六七八九十百千万点\.]+"

BOOLEAN_FACTS = {
    "has_written_contract",
    "recruitment_conditions_disclosed",
    "assessment_evidence_exists",
    "written_termination_notice",
    "employer_rules_disclosed",
    "disciplinary_evidence_exists",
    "employment_active",
    "overtime_approved",
}


def extract_labor_facts(
    text: str,
    state: CaseState | None = None,
    *,
    enable_semantic: bool = True,
    source_type: str = "user_message",
    source_ref: str = "",
    recognize_evidence_mentions: bool = True,
    interpret_pending_answer: bool = True,
    document_evidence_names: tuple[str, ...] = (),
) -> CaseState:
    """Merge facts from one user message into the same CaseState."""

    case = state or CaseState(user_narrative=text)
    case.ai_calls_this_turn = 0
    case.reply_transition = ""
    if not case.user_narrative:
        case.user_narrative = text
    pending_questions = list(case.pending_questions)
    pending_fact_ids = list(getattr(case, "pending_fact_ids", []))
    pending_evidence_requests = list(case.pending_evidence_requests)
    previous_dispute_type = case.dispute_type
    model = get_labor_model()
    facts: dict[str, Any] = {}
    recognized_evidence = False

    duration = re.search(rf"(?:工作|入职|干了)\s*({NUMBER_PATTERN})\s*个?月", text)
    if duration:
        facts["employment_duration_months"] = _parse_number(duration.group(1))

    is_standalone_contract = (
        source_type == "uploaded_file"
        and "劳动合同" in document_evidence_names
        and not any(name in document_evidence_names for name in ("工资流水", "工资单", "银行流水"))
    )
    if is_standalone_contract:
        facts.update(_extract_contract_document_facts(text))
    else:
        salary = _monthly_salary_amount(text)
        if salary is not None:
            facts["monthly_salary"] = salary

    probation = re.search(rf"试用期(?:约定)?(?:是|为|写了|写的是)?\s*({NUMBER_PATTERN})\s*个?月", text)
    if probation:
        facts["probation_period_months"] = _parse_number(probation.group(1))

    contract_term = re.search(rf"合同(?:期限|期)?(?:是|为|写了|写的是)?\s*({NUMBER_PATTERN})\s*(年|个?月)", text)
    if contract_term:
        value = _parse_number(contract_term.group(1))
        facts["contract_term_months"] = value * 12 if "年" in contract_term.group(2) else value

    unsigned = any(marker in text for marker in ("没签劳动合同", "未签劳动合同", "没有劳动合同", "没签合同"))
    signed = any(marker in text for marker in ("签了劳动合同", "签订了劳动合同", "有劳动合同", "签了合同"))
    if unsigned:
        facts["has_written_contract"] = False
    elif signed:
        facts["has_written_contract"] = True

    if "表现不合格" in text or "不符合录用条件" in text:
        facts["termination_reason"] = "试用期表现不合格/不符合录用条件"
    elif any(marker in text for marker in ("辞退", "开除", "不用来了", "不用上班")):
        facts.setdefault("termination_reason", "用人单位通知解除，具体理由待核实")

    if any(marker in text for marker in ("没有书面通知", "没收到书面", "只有微信")):
        facts["written_termination_notice"] = False
    elif any(marker in text for marker in ("收到书面解除", "有解除通知", "书面通知")):
        facts["written_termination_notice"] = True

    if any(marker in text for marker in ("没有告知录用条件", "没说过录用条件", "未告知录用条件")):
        facts["recruitment_conditions_disclosed"] = False
    elif any(marker in text for marker in ("告知了录用条件", "签收录用条件", "明确录用条件")):
        facts["recruitment_conditions_disclosed"] = True

    if any(marker in text for marker in ("没有考核记录", "没做考核", "未出示考核")):
        facts["assessment_evidence_exists"] = False
        facts["disciplinary_evidence_exists"] = False
    elif any(marker in text for marker in ("有考核记录", "出示了考核", "有绩效记录")):
        facts["assessment_evidence_exists"] = True
        facts["disciplinary_evidence_exists"] = True

    if any(marker in text for marker in ("没有赔偿", "没有补偿", "没拿到赔偿", "未支付补偿")):
        facts["compensation_received"] = False

    arrears = re.search(r"拖欠\s*(\d+(?:\.\d+)?)\s*个?月", text)
    if arrears:
        facts["arrears_months"] = float(arrears.group(1))
    overtime = re.search(r"加班\s*(\d+(?:\.\d+)?)\s*小时", text)
    if overtime:
        facts["overtime_hours"] = float(overtime.group(1))

    if interpret_pending_answer:
        facts.update(
            _extract_contextual_facts(
                text,
                case,
                pending_questions,
                pending_fact_ids,
                facts,
                model,
            )
        )
    case.apply_facts(facts)
    if facts:
        for fact_id in facts:
            case.add_fact_provenance(
                fact_id,
                source_type=source_type,
                source_ref=source_ref,
                quote=_fact_source_quote(text, fact_id),
                extraction_method="rules",
            )
    if recognize_evidence_mentions:
        for evidence_name, keywords in EVIDENCE_KEYWORDS.items():
            if any(_affirmed_mention(text, keyword) for keyword in keywords):
                recognized_evidence = True
                case.add_evidence(evidence_name, source="user_message")
    if pending_evidence_requests and _confirms_all(text):
        recognized_evidence = True
        for evidence_name in pending_evidence_requests:
            case.add_evidence(evidence_name, source="contextual_user_answer")
    if pending_evidence_requests and _declines_remaining_evidence(text):
        recognized_evidence = True
        case.mark_evidence_unavailable(pending_evidence_requests, exhausted=True)

    if case.dispute_type == "unknown":
        case.dispute_type = model.classify(case.user_narrative + "\n" + text)
    rule_understood = bool(facts) or recognized_evidence or _locally_understood_without_fact(text)
    rule_understood = rule_understood or (
        previous_dispute_type == "unknown" and case.dispute_type != "unknown"
    )
    if enable_semantic and not rule_understood and text.strip():
        # Optional and failure-safe: a missing key or remote error never blocks the core flow.
        from backend.ai.semantic import enrich_case_from_text

        enrich_case_from_text(text, case)
    return model.prepare_state(case)


def _extract_contract_document_facts(text: str) -> dict[str, Any]:
    """Extract contract-specific values without treating a promised wage as average pay."""

    facts: dict[str, Any] = {}
    contract_range = _dated_range(text, r"合同期限")
    if contract_range:
        start, end, months = contract_range
        facts.update({
            "contract_start_date": start.isoformat(),
            "contract_end_date": end.isoformat(),
            "contract_term_months": months,
        })
    probation_range = _dated_range(text, r"试用期")
    if probation_range:
        start, end, months = probation_range
        facts.update({
            "probation_start_date": start.isoformat(),
            "probation_end_date": end.isoformat(),
            "probation_period_months": months,
        })

    probation_pay = re.search(
        rf"试用期(?:的)?(?:月|每月)?(?:基本)?工资(?:标准)?(?:是|为)?\s*[￥¥]?\s*({NUMBER_PATTERN})\s*元",
        text,
    )
    if probation_pay:
        facts["probation_monthly_salary"] = _parse_number(probation_pay.group(1))
    regular_pay = re.search(
        rf"(?:转正后|试用期满后)(?:的)?(?:月|每月)?(?:基本)?工资(?:标准)?(?:是|为)?\s*[￥¥]?\s*({NUMBER_PATTERN})\s*元",
        text,
    )
    if regular_pay:
        facts["regular_monthly_salary"] = _parse_number(regular_pay.group(1))
    return facts


def _dated_range(text: str, label: str) -> tuple[date, date, float] | None:
    date_pattern = r"(\d{4})[年./-](\d{1,2})[月./-](\d{1,2})日?"
    match = re.search(
        rf"{label}.{{0,18}}?自?\s*{date_pattern}\s*(?:起)?\s*(?:至|到)\s*{date_pattern}\s*(?:止)?",
        text,
    )
    if not match:
        return None
    try:
        start = date(*(int(value) for value in match.group(1, 2, 3)))
        end = date(*(int(value) for value in match.group(4, 5, 6)))
    except ValueError:
        return None
    if end < start:
        return None
    months = max(round((end - start).days / 30.4375), 1)
    return start, end, float(months)


def _fact_source_quote(text: str, fact_id: str) -> str:
    concepts = {
        "has_written_contract": ("劳动合同",),
        "contract_start_date": ("合同期限",),
        "contract_end_date": ("合同期限",),
        "contract_term_months": ("合同期限",),
        "probation_start_date": ("试用期",),
        "probation_end_date": ("试用期",),
        "probation_period_months": ("试用期",),
        "probation_monthly_salary": ("试用期月工资", "试用期工资"),
        "regular_monthly_salary": ("转正后", "试用期满后"),
        "monthly_salary": ("月工资", "月薪", "每月", "一个月"),
    }.get(fact_id, ())
    chunks = [chunk.strip() for chunk in re.split(r"[\n。；;]", text) if chunk.strip()]
    for chunk in chunks:
        if any(concept in chunk for concept in concepts):
            return " ".join(chunk.split())[:240]
    return " ".join(text.split())[:240]


def _extract_contextual_facts(
    text: str,
    case: CaseState,
    pending_questions: list[str],
    pending_fact_ids: list[str],
    explicit_facts: dict[str, Any],
    model,
) -> dict[str, Any]:
    """Interpret short answers against the exact question asked last turn."""

    if not pending_questions and not pending_fact_ids:
        return {}
    pending_ids = _resolve_pending_fact_ids(
        pending_questions,
        pending_fact_ids,
        model.question_specs(case.dispute_type),
    )
    contextual: dict[str, Any] = {}

    for fact_id in pending_ids:
        if fact_id in explicit_facts:
            continue
        if fact_id in BOOLEAN_FACTS:
            answer = _contextual_boolean_answer(text, fact_id)
            if answer is not None:
                contextual[fact_id] = answer
        elif fact_id == "monthly_salary":
            value = _monthly_salary_amount(text)
            if value is None:
                value = _bare_amount(text)
            if value is not None:
                contextual[fact_id] = value
        elif fact_id in {"contract_term_months", "probation_period_months", "employment_duration_months", "unsigned_months"}:
            value = _bare_duration_months(text)
            if value is not None:
                contextual[fact_id] = value
        elif fact_id in {"termination_reason", "termination_type", "work_schedule", "overtime_period"}:
            answer = text.strip(" ，。；;\n\t")
            if answer and _yes_no_answer(answer) is None:
                contextual[fact_id] = answer

    # A compact answer to the contract question often carries the contract term too.
    if "has_written_contract" in pending_ids and contextual.get("has_written_contract") is True:
        term = re.search(rf"({NUMBER_PATTERN})\s*年", text)
        if term and "contract_term_months" not in explicit_facts:
            contextual["contract_term_months"] = _parse_number(term.group(1)) * 12
    return contextual


def _resolve_pending_fact_ids(
    questions: list[str],
    stored_ids: list[str],
    specs: list[dict[str, Any]],
) -> list[str]:
    """Prefer stable fact IDs and tolerate wording changes in older sessions."""

    valid_ids = {spec["id"] for spec in specs}
    resolved = [fact_id for fact_id in stored_ids if fact_id in valid_ids]
    normalized_specs = {
        _normalize_text(spec["question"]): spec["id"]
        for spec in specs
    }
    for question in questions:
        normalized = _normalize_text(question)
        exact = normalized_specs.get(normalized)
        if exact and exact not in resolved:
            resolved.append(exact)
            continue
        if not normalized:
            continue
        candidates = [
            (
                SequenceMatcher(None, normalized, spec_question).ratio(),
                fact_id,
            )
            for spec_question, fact_id in normalized_specs.items()
        ]
        score, closest = max(candidates, default=(0.0, ""))
        if score >= 0.55 and closest not in resolved:
            resolved.append(closest)
    return resolved


def _contextual_boolean_answer(text: str, fact_id: str) -> bool | None:
    """Understand natural short answers in the semantic frame of the last question."""

    normalized = _normalize_text(text)
    if any(
        marker in normalized
        for marker in ("不清楚", "不知道", "不确定", "记不清", "想不起来", "忘记了", "好像", "可能")
    ):
        return None

    concept_groups = {
        "has_written_contract": (
            "签订", "签署", "签了", "签过", "书面合同",
        ),
        "assessment_evidence_exists": (
            "出示", "提供", "展示", "发给", "收到", "看过", "考核过",
        ),
        "written_termination_notice": (
            "收到", "签收", "书面通知", "解除通知", "辞退通知", "发给",
        ),
        "employer_rules_disclosed": (
            "公示", "告知", "告诉", "签收", "发放", "看过", "培训过",
        ),
        "disciplinary_evidence_exists": (
            "出示", "提供", "展示", "发给", "收到", "看过",
        ),
        "overtime_approved": (
            "安排", "审批", "批准", "同意", "确认", "要求加班",
        ),
    }
    if fact_id == "employment_active":
        active = _concept_polarity(text, ("在职", "还在上班", "仍在工作", "劳动关系存续"))
        if active is not None:
            return active
        ended = _concept_polarity(text, ("离职", "辞职", "解除", "终止", "被辞退", "不用上班"))
        if ended is not None:
            return not ended
    if fact_id == "recruitment_conditions_disclosed":
        disclosure = _concept_polarity(text, ("告知", "告诉", "说明", "讲过", "说过"))
        if disclosure is not None:
            return disclosure
        retained = _concept_polarity(text, ("发给", "签收", "留存", "签字确认"))
        if retained is not None:
            return retained

    concepts = concept_groups.get(fact_id)
    if concepts:
        polarity = _concept_polarity(text, concepts)
        if polarity is not None:
            return polarity
    return _yes_no_answer(text)


def _concept_polarity(text: str, concepts: tuple[str, ...]) -> bool | None:
    """Return whether a relevant action was affirmed, with basic negation scope."""

    compact = re.sub(r"\s+", "", text)
    values: list[bool] = []
    for concept in concepts:
        for match in re.finditer(re.escape(concept), compact):
            prefix = compact[:match.start()]
            clause = re.split(r"[，。；;！？!?]|但是|但|不过|然而|而是", prefix)[-1]
            negated = bool(re.search(r"(?:没有|没|未|无|从未|并未|不曾).{0,8}$", clause))
            values.append(not negated)
    if any(values):
        return True
    if values:
        return False
    return None


def _yes_no_answer(text: str) -> bool | None:
    normalized = _normalize_text(text)
    if any(marker in normalized for marker in ("不清楚", "不知道", "不确定", "记不清", "想不起来", "忘记了")):
        return None
    if any(marker in normalized for marker in ("不是没有", "并非没有", "不能说没有")):
        return True
    if any(marker in normalized for marker in ("没有", "没签", "没收到", "没告知", "没出示", "未签", "未收到", "未告知", "无")):
        return False
    if normalized in {"否", "不是", "没有的", "没", "未"}:
        return False
    if re.match(r"^(?:是的?|对的?|嗯+|没错|确实|当然|有(?:的|过)?)(?:$|[^没未不无])", normalized):
        return True
    if any(marker in normalized for marker in ("签了", "签过", "收到", "告知", "告诉", "出示", "提供", "留存", "签收", "存在", "仍在", "经过")):
        return True
    return None


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s，。！？、；;,.!：:?？]", "", text)


def _bare_duration_months(text: str) -> float | None:
    match = re.search(rf"({NUMBER_PATTERN})\s*(年|个?月)", text)
    if not match:
        return None
    value = _parse_number(match.group(1))
    return value * 12 if "年" in match.group(2) else value


def _bare_amount(text: str) -> float | None:
    if re.search(rf"{NUMBER_PATTERN}\s*(?:[kKwW]|位)", text):
        return None
    match = re.search(rf"[￥¥]?\s*({NUMBER_PATTERN})\s*(?:元)?", text.strip())
    if not match or any(unit in text for unit in ("年", "个月", "小时")):
        return None
    return _parse_number(match.group(1))


def _monthly_salary_amount(text: str) -> float | None:
    """Parse common spoken monthly-pay expressions without confusing duration for pay."""

    normalized = text.replace(",", "").replace("，", "")
    if re.search(rf"{NUMBER_PATTERN}\s*(?:[kKwW]|位)", normalized):
        return None
    amount = rf"[￥¥]?\s*({NUMBER_PATTERN})\s*(?:元|块钱|块)?"
    fillers = r"(?:大概|大约|约|差不多|是|为|有|能拿|拿)?"
    patterns = (
        rf"(?:每个月|每月|一个月|月薪|月工资)\s*(?:工资|薪资|收入|到手|税前)?\s*{fillers}\s*{amount}",
        rf"(?:平均月工资|月平均工资|工资|薪资|收入|到手|税前)\s*(?:一个月|每个月|每月)?\s*{fillers}\s*{amount}",
        rf"{amount}\s*(?:一个月|每个月|每月|/\s*月)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return _parse_number(match.group(1))
    return None


def _parse_number(raw: str) -> float:
    token = raw.strip().replace(",", "").replace("两", "二").replace("〇", "零")
    if re.fullmatch(r"\d+(?:\.\d+)?", token):
        return float(token)
    arabic_unit = re.fullmatch(r"(\d+(?:\.\d+)?)(万|千)", token)
    if arabic_unit:
        multiplier = 10000 if arabic_unit.group(2) == "万" else 1000
        return float(arabic_unit.group(1)) * multiplier
    if "点" in token:
        integer, decimal = token.split("点", 1)
        digits = {"零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
        return float(f"{int(_parse_number(integer))}." + "".join(digits[ch] for ch in decimal))

    digits = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    section = 0
    number = 0
    for char in token:
        if char in digits:
            number = digits[char]
        elif char in units:
            section += (number or 1) * units[char]
            number = 0
        elif char == "万":
            total += (section + number or 1) * 10000
            section = 0
            number = 0
    return float(total + section + number)


def _confirms_all(text: str) -> bool:
    normalized = re.sub(r"[\s，。！？、；;,.!]", "", text)
    return any(marker in normalized for marker in ("都有", "全部有", "都有的", "均有", "都可以提供"))


def _declines_remaining_evidence(text: str) -> bool:
    """Recognize that the user has no more material, not that one fact is false."""

    normalized = _normalize_text(text)
    exact_answers = {
        "没有", "没了", "没有了", "都没有", "全都没有", "暂时没有",
        "手头没有", "拿不到", "无法提供", "无法补充", "没别的了",
    }
    if normalized in exact_answers:
        return True
    return any(marker in normalized for marker in (
        "剩下的没有", "其余的没有", "没有其他材料", "没有别的材料",
        "没有可以补充", "现有材料就这些", "目前就这些", "手头就这些",
        "只有这些材料", "能提供的就这些",
    ))


def _affirmed_mention(text: str, keyword: str) -> bool:
    """Do not turn '没有考核记录' into evidence merely by keyword match."""

    for match in re.finditer(re.escape(keyword), text):
        prefix = text[max(0, match.start() - 5):match.start()]
        if not any(marker in prefix for marker in ("没有", "没", "无", "未", "不存在")):
            return True
    return False


def _locally_understood_without_fact(text: str) -> bool:
    """Skip a remote call when the user clearly cannot answer or sends social filler."""

    normalized = _normalize_text(text)
    uncertainty = (
        "不清楚", "不知道", "不确定", "记不清", "想不起来", "忘记了",
        "暂时没有材料", "手头没有", "拿不到", "无法提供", "没有其他材料",
        "没有别的材料", "没有可以补充", "现有材料就这些", "已上传", "上传了",
    )
    if any(marker in normalized for marker in uncertainty):
        return True
    return normalized in {
        "没有", "没了", "没有了", "都没有", "全都没有", "暂时没有",
        "谢谢", "好的谢谢", "明白了", "知道了", "辛苦了",
    }
