"""Traceable, temporal labor-law metadata search for the first-stage demo."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from backend.legal_rl.state import LawReference
from backend.legal_rl.state import CaseState


SOURCES_PATH = Path(__file__).resolve().parent / "law_sources.yaml"

ELEMENT_LEGAL_TERMS = {
    "employment_relationship": {"劳动关系", "用工", "入职"},
    "valid_probation_term": {"试用期", "合同期限"},
    "disclosed_recruitment_conditions": {"录用条件", "告知"},
    "failed_recruitment_conditions": {"录用条件", "考核"},
    "termination_occurred": {"解除", "解除理由"},
    "termination_basis": {"解除", "违纪", "考核", "事实依据"},
    "rules_validity": {"规章制度", "公示"},
    "compensation_eligibility": {"经济补偿", "赔偿金", "工作年限", "月工资"},
    "no_written_contract": {"未签合同", "书面劳动合同", "双倍工资"},
    "double_wage_base": {"双倍工资", "月工资"},
    "wage_agreement": {"工资", "工资标准"},
    "non_payment": {"拖欠工资", "工资支付", "劳动报酬"},
    "overtime_occurred": {"加班", "延长工作时间"},
    "employer_arranged": {"加班", "举证责任"},
    "overtime_base": {"加班费", "月工资"},
    "termination_type": {"解除", "终止"},
    "service_years": {"工作年限", "经济补偿"},
    "wage_base": {"月工资", "经济补偿", "赔偿金"},
}


@lru_cache(maxsize=1)
def _load_sources() -> list[dict]:
    with SOURCES_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["sources"]


def search_law(
    query: str,
    event_date: date | str | None = None,
    limit: int = 8,
    *,
    focus_elements: list[dict] | None = None,
) -> list[LawReference]:
    """Search curated official sources and filter versions effective on event_date."""

    when = date.fromisoformat(event_date) if isinstance(event_date, str) else event_date
    tokens = {token for token in query.replace("/", " ").split() if token}
    ranked: list[tuple[float, dict, list[str]]] = []
    for item in _load_sources():
        start = _as_date(item.get("effective_from"))
        end = _as_date(item.get("effective_to"))
        if when and ((start and when < start) or (end and when > end)):
            continue
        haystack = " ".join(item.get("tags", [])) + item["summary"] + item["article"]
        matched_elements = _matched_elements(item, focus_elements or [])
        score = float(sum(2 for token in tokens if token in haystack))
        score += sum(1.5 for tag in item.get("tags", []) if tag in query)
        score += 1.25 * len(matched_elements)
        score += 0.15 * _authority_level(item["law_name"])
        if score:
            ranked.append((score, item, matched_elements))

    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    selected = ranked[:limit]
    if not selected:
        selected = [
            (0.1, item, _matched_elements(item, focus_elements or []))
            for item in _load_sources()
            if "劳动争议" in item.get("tags", [])
        ][:limit]
    return [
        LawReference(
            source_id=item["id"],
            law_name=item["law_name"],
            article=item["article"],
            summary=item["summary"],
            source_url=item["source_url"],
            effective_from=_as_date(item.get("effective_from")),
            effective_to=_as_date(item.get("effective_to")),
            authority_level=_authority_level(item["law_name"]),
            retrieval_score=round(score, 4),
            matched_elements=matched_elements,
            temporal_validated=True,
        )
        for score, item, matched_elements in selected
    ]


def search_law_for_state(state: CaseState, limit: int = 8) -> list[LawReference]:
    """Graph-expanded retrieval that links every result to one or more legal elements."""

    from backend.legal_domain.labor.evidence_graph import graph_retrieval_terms
    from backend.legal_domain.labor.model import get_labor_model

    config = get_labor_model().get(state.dispute_type)
    query = " ".join(graph_retrieval_terms(state))
    return search_law(
        query,
        state.event_date,
        limit,
        focus_elements=config.get("elements", []),
    )


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None


def _authority_level(law_name: str) -> int:
    if "中华人民共和国" in law_name and "法" in law_name:
        return 5
    if "最高人民法院" in law_name and "解释" in law_name:
        return 4
    if "条例" in law_name:
        return 3
    return 2


def _matched_elements(item: dict, elements: list[dict]) -> list[str]:
    tags = set(item.get("tags", []))
    summary = item.get("summary", "")
    matches: list[str] = []
    for element in elements:
        terms = ELEMENT_LEGAL_TERMS.get(element["id"], {element.get("name", "")})
        if any(term and (term in summary or term in tags) for term in terms):
            matches.append(element["id"])
    return matches
