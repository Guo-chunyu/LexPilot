"""Build an auditable fact-evidence-element-law graph for each labor case."""

from __future__ import annotations

from typing import Any

from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.state import (
    CaseState,
    EvidenceReasoningGraph,
    EvidenceStatus,
    ReasoningEdge,
    ReasoningNode,
    ReasoningPath,
)


def build_evidence_graph(state: CaseState) -> EvidenceReasoningGraph:
    """Materialize the domain schema and current evidence into explainable paths."""

    config = get_labor_model().get(state.dispute_type)
    gaps = {gap.element_id: gap for gap in state.evidence_gaps}
    present_evidence = {item.name for item in state.evidence}
    nodes: list[ReasoningNode] = [
        ReasoningNode(
            node_id=f"case:{state.case_id}",
            node_type="case",
            label=config.get("name", state.dispute_type),
            status="ACTIVE" if not state.done else "COMPLETE",
        )
    ]
    edges: list[ReasoningEdge] = []
    paths: list[ReasoningPath] = []
    node_ids = {nodes[0].node_id}

    all_fact_ids = list(state.key_facts)
    for element in config.get("elements", []):
        for fact_id in element.get("required_facts", []):
            if fact_id not in all_fact_ids:
                all_fact_ids.append(fact_id)
    for fact_id in all_fact_ids:
        known = _known(state.facts.get(fact_id))
        node = ReasoningNode(
            node_id=f"fact:{fact_id}",
            node_type="fact",
            label=fact_id,
            status="KNOWN" if known else "MISSING",
            value=_safe_value(state.facts.get(fact_id)) if known else "",
        )
        _append_node(nodes, node_ids, node)
        edges.append(ReasoningEdge(
            source=f"case:{state.case_id}",
            target=node.node_id,
            relation="HAS_FACT" if known else "NEEDS_FACT",
        ))

    for evidence_name in state.key_evidence:
        present = evidence_name in present_evidence
        _append_node(nodes, node_ids, ReasoningNode(
            node_id=f"evidence:{evidence_name}",
            node_type="evidence",
            label=evidence_name,
            status="PRESENT" if present else "MISSING",
        ))

    for law in state.retrieved_laws:
        law_id = law.source_id or _law_fallback_id(law.law_name, law.article)
        _append_node(nodes, node_ids, ReasoningNode(
            node_id=f"law:{law_id}",
            node_type="law",
            label=f"{law.law_name}{law.article}",
            status="VALID" if law.temporal_validated else "OUT_OF_TIME",
            value=law.summary,
        ))

    for element in config.get("elements", []):
        element_id = element["id"]
        element_node_id = f"element:{element_id}"
        gap = gaps.get(element_id)
        status = gap.status if gap else EvidenceStatus.MISSING
        _append_node(nodes, node_ids, ReasoningNode(
            node_id=element_node_id,
            node_type="legal_element",
            label=element["name"],
            status=status.value,
        ))
        edges.append(ReasoningEdge(
            source=f"case:{state.case_id}",
            target=element_node_id,
            relation="HAS_LEGAL_ELEMENT",
        ))

        fact_ids = list(element.get("required_facts", []))
        for fact_id in fact_ids:
            edges.append(ReasoningEdge(
                source=f"fact:{fact_id}",
                target=element_node_id,
                relation="SUPPORTS" if _known(state.facts.get(fact_id)) else "REQUIRED_BY",
                rationale="该结构化事实是判断此法律要件的必要输入。",
            ))

        evidence_names = list(element.get("evidence_any", []))
        for evidence_name in evidence_names:
            edges.append(ReasoningEdge(
                source=f"evidence:{evidence_name}",
                target=element_node_id,
                relation="CORROBORATES" if evidence_name in present_evidence else "REQUESTED_FOR",
                rationale="该材料可以支持或反驳此法律要件。",
            ))

        matched_law_ids: list[str] = []
        for law in state.retrieved_laws:
            law_id = law.source_id or _law_fallback_id(law.law_name, law.article)
            if element_id in law.matched_elements or _law_matches_element(law.summary, element):
                matched_law_ids.append(law_id)
                edges.append(ReasoningEdge(
                    source=f"law:{law_id}",
                    target=element_node_id,
                    relation="GOVERNS",
                    rationale="法条内容或检索标签与该法律要件匹配。",
                ))

        known_fact_ratio = sum(_known(state.facts.get(key)) for key in fact_ids) / max(len(fact_ids), 1)
        evidence_ratio = sum(name in present_evidence for name in evidence_names) / max(len(evidence_names), 1)
        law_ratio = 1.0 if matched_law_ids else 0.0
        support = 0.45 * known_fact_ratio + 0.35 * min(evidence_ratio * 2, 1.0) + 0.20 * law_ratio
        if status == EvidenceStatus.CONFLICT:
            support *= 0.35
        support = round(max(0.0, min(support, 1.0)), 4)
        paths.append(ReasoningPath(
            element_id=element_id,
            element_name=element["name"],
            fact_ids=fact_ids,
            evidence_names=[name for name in evidence_names if name in present_evidence],
            law_ids=matched_law_ids,
            status=status,
            support_score=support,
            explanation=_path_explanation(status, known_fact_ratio, evidence_ratio, bool(matched_law_ids)),
        ))

    focus = [
        path.element_id
        for path in sorted(
            paths,
            key=lambda item: (
                {EvidenceStatus.CONFLICT: 0, EvidenceStatus.MISSING: 1, EvidenceStatus.PARTIAL: 2, EvidenceStatus.PROVEN: 3}[item.status],
                item.support_score,
            ),
        )[:3]
    ]
    graph = EvidenceReasoningGraph(nodes=nodes, edges=edges, paths=paths, focus_element_ids=focus)
    state.reasoning_graph = graph
    return graph


def graph_retrieval_terms(state: CaseState) -> list[str]:
    """Expand a legal query through unresolved graph elements and known fact concepts."""

    config = get_labor_model().get(state.dispute_type)
    terms = list(config.get("legal_queries", []))
    focus = set(state.reasoning_graph.focus_element_ids)
    for element in config.get("elements", []):
        if not focus or element["id"] in focus:
            terms.append(element["name"])
    for key in state.facts:
        if key in state.key_facts:
            terms.append(key.replace("_", " "))
    return list(dict.fromkeys(term for term in terms if term))


def _append_node(nodes: list[ReasoningNode], node_ids: set[str], node: ReasoningNode) -> None:
    if node.node_id not in node_ids:
        nodes.append(node)
        node_ids.add(node.node_id)


def _known(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _safe_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)[:160]


def _law_fallback_id(law_name: str, article: str) -> str:
    return f"{law_name}:{article}".replace(" ", "_")


def _law_matches_element(summary: str, element: dict[str, Any]) -> bool:
    from backend.legal_domain.labor.legal_search import ELEMENT_LEGAL_TERMS

    keywords = ELEMENT_LEGAL_TERMS.get(element["id"], {element.get("name", "")})
    return any(keyword and keyword in summary for keyword in keywords)


def _path_explanation(
    status: EvidenceStatus,
    fact_ratio: float,
    evidence_ratio: float,
    has_law: bool,
) -> str:
    parts = [f"必要事实覆盖 {fact_ratio:.0%}", f"关联证据覆盖 {evidence_ratio:.0%}"]
    parts.append("已关联有效法源" if has_law else "尚未关联直接法源")
    if status == EvidenceStatus.CONFLICT:
        parts.append("存在冲突，系统禁止形成确定性结论")
    return "；".join(parts) + "。"
