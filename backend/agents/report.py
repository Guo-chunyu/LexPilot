"""Build the structured final report consumed by API and Streamlit."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.ai.reporting import draft_grounded_content
from backend.legal_domain.labor.verification import verify_case_grounding
from backend.legal_rl.state import CaseState, EvidenceStatus


class FinalLegalReport(BaseModel):
    generation_status: str
    case_summary: str
    legal_issues: list[str]
    facts: list[dict]
    evidence_status: list[dict]
    missing_evidence: list[str]
    opponent_arguments: list[str]
    legal_basis: list[dict]
    grounded_findings: list[dict]
    verification: dict
    risk_analysis: list[dict]
    recommended_actions: list[str]
    compensation_estimate: dict
    confidence: float = Field(ge=0.0, le=1.0)
    disclaimer: str
    action_plan: list[dict] = Field(default_factory=list)
    evidence_checklist: list[dict] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    deadlines: list[dict] = Field(default_factory=list)
    documents: list[dict] = Field(default_factory=list)


def build_final_report(state: CaseState) -> FinalLegalReport:
    from backend.legal_domain.consultation.intake import refresh_evidence
    from backend.legal_domain.consultation.reporting import action_plan, plan_documents
    from backend.legal_domain.consultation.profiles import PROFILES
    verification = verify_case_grounding(state)
    recommendations = []
    if state.missing_facts:
        recommendations.append("补充关键事实：" + "、".join(state.missing_facts[:4]))
    missing = []
    for gap in state.evidence_gaps:
        if gap.status != EvidenceStatus.PROVEN:
            for item in gap.missing_evidence[:2]:
                if item not in missing:
                    missing.append(item)
    if missing:
        if state.evidence_collection_exhausted:
            recommendations.append(
                "目前未取得的材料已标记为证据缺口；如后续取得，再补充核验："
                + "、".join(missing[:6])
            )
        else:
            recommendations.append("优先固定或调取证据：" + "、".join(missing[:6]))
    recommendations.extend([
        "保存原始聊天记录、通知、工资及社保材料并做好时间线备份。",
        "在法定时效内向有管辖权的劳动人事争议仲裁委员会核实并提交申请。",
    ])
    if not verification.can_generate:
        recommendations.insert(0, verification.refusal_reason)
    # A clear "no more materials" answer should return immediately. The verified
    # structure already contains the facts, evidence paths and laws needed for a
    # safe stage report, so no remote wording call is necessary here.
    use_ai_draft = verification.can_generate and not state.evidence_collection_exhausted
    draft = draft_grounded_content(state) if use_ai_draft else {
        "case_summary": state.user_narrative or f"{state.dispute_type} 劳动争议",
        "grounded_findings": [],
        "recommended_actions": [],
    }
    recommendations = list(dict.fromkeys([
        *draft.get("recommended_actions", []),
        *recommendations,
    ]))
    # Reuse the practical plan structure without replacing the specialist's
    # evidence graph, completeness metrics or verified labor-law findings.
    original_gaps, original_missing, original_score = state.evidence_gaps, state.missing_evidence, state.evidence_completeness
    refresh_evidence(state)
    state.evidence_gaps, state.missing_evidence, state.evidence_completeness = original_gaps, original_missing, original_score
    report = FinalLegalReport(
        generation_status="VERIFIED" if verification.can_generate else "INSUFFICIENT_SUPPORT",
        case_summary=draft.get("case_summary") or state.user_narrative or f"{state.dispute_type} 劳动争议",
        legal_issues=state.legal_issues,
        facts=[{"name": key, "value": value} for key, value in state.facts.items()],
        evidence_status=[gap.model_dump(mode="json") for gap in state.evidence_gaps],
        missing_evidence=missing,
        opponent_arguments=state.opponent_analysis.get("arguments", []),
        legal_basis=[law.model_dump(mode="json") for law in state.retrieved_laws],
        grounded_findings=draft.get("grounded_findings", []),
        verification=verification.model_dump(mode="json"),
        risk_analysis=[risk.model_dump(mode="json") for risk in state.risks],
        recommended_actions=recommendations,
        compensation_estimate=state.compensation_estimate,
        confidence=state.overall_confidence,
        disclaimer="本报告用于信息整理与决策辅助，不替代执业律师基于完整证据和当地裁审口径出具的法律意见。",
        action_plan=action_plan(state),
        evidence_checklist=[t.model_dump() for t in state.consultation.evidence_tasks],
        costs=[PROFILES['labor_dispute'].costs],
        deadlines=[{"name": "劳动仲裁时效及收到文书后的救济期限", "status": "须结合请求类型与具体日期核对", "trigger": str(state.event_date or "发生日、解除日或履行期尚待核实"), "action": "先向有管辖权的受理窗口核对起算日期、特殊规则、中断等影响；不把材料收集结束日当作起算日。"}],
        documents=plan_documents(state),
    )
    state.final_report = report.model_dump(mode="json")
    return report
