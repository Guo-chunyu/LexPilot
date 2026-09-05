"""Deterministic grounding, citation, temporal-validity, and refusal checks."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from backend.legal_domain.labor.evidence_graph import build_evidence_graph
from backend.legal_rl.state import (
    CaseState,
    ClaimVerification,
    EvidenceStatus,
    VerificationResult,
)


OFFICIAL_SOURCE_SUFFIXES = (
    ".gov.cn",
    ".court.gov.cn",
    ".npc.gov.cn",
    ".mohrss.gov.cn",
    ".samr.gov.cn",
)


def verify_case_grounding(state: CaseState) -> VerificationResult:
    """Compute whether the available case record can support a grounded report."""

    graph = build_evidence_graph(state)
    accepted_sources = {
        item.fact_id
        for item in state.fact_provenance
        if item.accepted and item.quote
    }
    known_facts = {key for key in state.key_facts if _known(state.facts.get(key))}
    traceable = known_facts & accepted_sources
    fact_traceability = len(traceable) / max(len(known_facts), 1) if known_facts else 0.0

    citation_checks = [_citation_is_valid(law.source_url, law.article) for law in state.retrieved_laws]
    temporal_checks = [_law_effective_on(law.effective_from, law.effective_to, state.event_date) for law in state.retrieved_laws]
    citation_score = sum(citation_checks) / max(len(citation_checks), 1)
    temporal_score = sum(temporal_checks) / max(len(temporal_checks), 1)

    claims: list[ClaimVerification] = []
    supported_weights: list[float] = []
    for path in graph.paths:
        if path.status == EvidenceStatus.PROVEN:
            status, weight = "SUPPORTED", 1.0
        elif path.status == EvidenceStatus.PARTIAL:
            status, weight = "PARTIAL", 0.5
        elif path.status == EvidenceStatus.CONFLICT:
            status, weight = "CONFLICT", 0.0
        else:
            status, weight = "UNSUPPORTED", 0.0
        if not path.law_ids:
            weight = min(weight, 0.5)
            if status == "SUPPORTED":
                status = "PARTIAL"
        supported_weights.append(weight)
        claims.append(ClaimVerification(
            claim_id=f"element:{path.element_id}",
            claim=f"案件要件“{path.element_name}”的当前支持状态",
            status=status,
            fact_ids=[key for key in path.fact_ids if _known(state.facts.get(key))],
            evidence_names=path.evidence_names,
            law_ids=path.law_ids,
            reason=path.explanation,
        ))

    claim_score = sum(supported_weights) / max(len(supported_weights), 1)
    has_conflict = any(claim.status == "CONFLICT" for claim in claims)
    can_generate = (
        state.fact_completeness >= 0.70
        and state.evidence_completeness >= 0.45
        and bool(state.retrieved_laws)
        and citation_score >= 0.80
        and temporal_score == 1.0
        and claim_score >= 0.40
        and not has_conflict
    )
    refusal_reason = _refusal_reason(
        state,
        citation_score=citation_score,
        temporal_score=temporal_score,
        claim_score=claim_score,
        has_conflict=has_conflict,
    )
    result = VerificationResult(
        status="VERIFIED" if can_generate else "INSUFFICIENT_SUPPORT",
        fact_traceability_score=round(fact_traceability, 4),
        claim_support_score=round(claim_score, 4),
        citation_validity_score=round(citation_score, 4),
        temporal_validity_score=round(temporal_score, 4),
        can_generate=can_generate,
        refusal_reason="" if can_generate else refusal_reason,
        claims=claims,
    )
    state.verification_result = result
    return result


def validate_generated_findings(findings: list[dict], state: CaseState) -> list[dict]:
    """Drop generated claims that cite unknown IDs or unresolved/conflicting elements."""

    known_fact_ids = {key for key, value in state.facts.items() if _known(value)}
    known_law_ids = {
        law.source_id
        for law in state.retrieved_laws
        if law.source_id and _citation_is_valid(law.source_url, law.article)
    }
    path_by_id = {path.element_id: path for path in state.reasoning_graph.paths}
    accepted: list[dict] = []
    for index, finding in enumerate(findings):
        fact_ids = list(dict.fromkeys(finding.get("fact_ids", [])))
        law_ids = list(dict.fromkeys(finding.get("law_ids", [])))
        element_ids = list(dict.fromkeys(finding.get("element_ids", [])))
        text = str(finding.get("text", "")).strip()
        if not text or not law_ids or not element_ids:
            continue
        if not set(fact_ids).issubset(known_fact_ids) or not set(law_ids).issubset(known_law_ids):
            continue
        if not set(element_ids).issubset(path_by_id):
            continue
        paths = [path_by_id[element_id] for element_id in element_ids]
        if any(path.status in {EvidenceStatus.MISSING, EvidenceStatus.CONFLICT} for path in paths):
            continue
        path_fact_ids = {fact_id for path in paths for fact_id in path.fact_ids}
        path_law_ids = {law_id for path in paths for law_id in path.law_ids}
        if not set(fact_ids).issubset(path_fact_ids) or not set(law_ids).issubset(path_law_ids):
            continue
        support_status = "SUPPORTED" if all(path.status == EvidenceStatus.PROVEN for path in paths) else "PARTIAL"
        accepted.append({
            "finding_id": f"finding:{index + 1}",
            "text": text[:500],
            "fact_ids": fact_ids,
            "element_ids": element_ids,
            "law_ids": law_ids,
            "support_status": support_status,
        })
    return accepted


def _citation_is_valid(url: str, article: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    official = any(host == suffix.removeprefix(".") or host.endswith(suffix) for suffix in OFFICIAL_SOURCE_SUFFIXES)
    return parsed.scheme == "https" and official and bool(article.strip())


def _law_effective_on(start: date | None, end: date | None, event_date: date | None) -> bool:
    if event_date is None:
        return True
    return not ((start and event_date < start) or (end and event_date > end))


def _known(value: object) -> bool:
    return value is not None and value != "" and value != []


def _refusal_reason(
    state: CaseState,
    *,
    citation_score: float,
    temporal_score: float,
    claim_score: float,
    has_conflict: bool,
) -> str:
    if has_conflict:
        return "案件事实或证据存在冲突，系统暂不生成确定性法律结论。"
    if state.fact_completeness < 0.70:
        return "关键事实不足，系统将继续追问而不是推测。"
    if state.evidence_completeness < 0.45:
        return "核心证据链不足，系统将先提示补充材料。"
    if not state.retrieved_laws:
        return "尚未找到可追溯的适用法源，系统拒绝生成无依据结论。"
    if citation_score < 0.80:
        return "部分引用无法通过官方来源核验，系统拒绝输出确定性结论。"
    if temporal_score < 1.0:
        return "存在与案件发生时间不匹配的法源，系统需要重新检索。"
    if claim_score < 0.40:
        return "法律要件支持度不足，当前只能输出信息缺口提示。"
    return "当前材料尚未达到可验证生成门槛。"
