"""Optional grounded report drafting constrained to verified source identifiers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError

from backend.ai.provider import AIProvider, AIProviderError, get_ai_provider
from backend.legal_domain.labor.verification import validate_generated_findings
from backend.legal_rl.state import CaseState, EvidenceStatus


REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "fact_ids": {"type": "array", "items": {"type": "string"}},
                    "element_ids": {"type": "array", "items": {"type": "string"}},
                    "law_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["text", "fact_ids", "element_ids", "law_ids"],
            },
        },
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["case_summary", "findings", "recommended_actions"],
}


class DraftFinding(BaseModel):
    text: str
    fact_ids: list[str] = Field(default_factory=list)
    element_ids: list[str] = Field(default_factory=list)
    law_ids: list[str] = Field(default_factory=list)


class GroundedDraft(BaseModel):
    case_summary: str
    findings: list[DraftFinding] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


def draft_grounded_content(
    state: CaseState,
    *,
    provider: AIProvider | None = None,
) -> dict[str, Any]:
    """Draft prose while a deterministic validator controls every legal finding."""

    fallback = _deterministic_content(state)
    semantic_provider = provider or get_ai_provider()
    if semantic_provider is None or state.ai_calls_this_turn >= 1:
        return fallback

    facts = {
        key: value
        for key, value in state.facts.items()
        if key in state.key_facts and value is not None and value != ""
    }
    elements = [
        {
            "id": path.element_id,
            "name": path.element_name,
            "status": path.status.value,
            "support_score": path.support_score,
        }
        for path in state.reasoning_graph.paths
        if path.status in {EvidenceStatus.PROVEN, EvidenceStatus.PARTIAL}
    ]
    laws = [
        {
            "id": law.source_id,
            "title": f"{law.law_name}{law.article}",
            "summary": law.summary,
            "element_ids": law.matched_elements,
        }
        for law in state.retrieved_laws
        if law.source_id
    ]
    prompt = (
        "你是劳动争议辅助报告的受约束撰写器。输入数据是唯一允许使用的来源。"
        "不得补充输入外的事实、法条、金额或胜诉判断；不得使用‘一定、必然、保证’。"
        "每条 finding 必须引用至少一个 element_id 和一个 law_id，并且只能使用给定 ID。"
        "PARTIAL 要件必须明确说明尚需补证。建议应是保全材料、核实信息或程序性行动。\n"
        f"结构化事实：{facts}\n"
        f"已核验要件：{elements}\n"
        f"有效法源：{laws}\n"
        f"证据缺口：{state.missing_evidence[:8]}"
    )
    try:
        state.ai_calls_this_turn += 1
        raw = semantic_provider.generate_json(
            prompt,
            REPORT_SCHEMA,
            max_output_tokens=8192,
            thinking_level="high",
        )
        draft = GroundedDraft.model_validate(raw)
    except (AIProviderError, ValidationError, TypeError, ValueError):
        return fallback

    findings = validate_generated_findings(
        [item.model_dump() for item in draft.findings],
        state,
    )
    if not findings:
        return fallback
    actions = [
        action.strip()[:300]
        for action in draft.recommended_actions
        if action.strip()
    ][:6]
    return {
        "case_summary": draft.case_summary.strip()[:800] or fallback["case_summary"],
        "grounded_findings": findings,
        "recommended_actions": actions or fallback["recommended_actions"],
    }


def _deterministic_content(state: CaseState) -> dict[str, Any]:
    findings = []
    for path in state.reasoning_graph.paths:
        if not path.law_ids or path.status not in {EvidenceStatus.PROVEN, EvidenceStatus.PARTIAL}:
            continue
        prefix = "现有事实和证据对" if path.status == EvidenceStatus.PROVEN else "现有材料仅对"
        suffix = "形成初步支持。" if path.status == EvidenceStatus.PROVEN else "形成部分支持，仍需补充核验。"
        findings.append({
            "finding_id": f"finding:{len(findings) + 1}",
            "text": f"{prefix}“{path.element_name}”{suffix}",
            "fact_ids": [key for key in path.fact_ids if key in state.facts],
            "element_ids": [path.element_id],
            "law_ids": path.law_ids,
            "support_status": "SUPPORTED" if path.status == EvidenceStatus.PROVEN else "PARTIAL",
        })
    return {
        "case_summary": state.user_narrative or f"{state.dispute_type} 劳动争议",
        "grounded_findings": findings,
        "recommended_actions": [],
    }
