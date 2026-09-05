"""Loader and helpers for the labor-dispute configuration model."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.legal_rl.state import CaseState


PACKAGE_DIR = Path(__file__).resolve().parent


class LaborDomainModel:
    """Read-only domain model backed by human-reviewable YAML files."""

    def __init__(self, issues_path: Path | None = None) -> None:
        path = issues_path or PACKAGE_DIR / "issues.yaml"
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        self.version = data["version"]
        self.disputes: dict[str, dict[str, Any]] = data["disputes"]

    def classify(self, narrative: str) -> str:
        text = narrative.lower()
        ordered = [
            "unsigned_contract",
            "wage_arrears",
            "overtime",
            "probation_termination",
            "unlawful_termination",
            "compensation",
        ]
        for dispute_id in ordered:
            config = self.disputes[dispute_id]
            if any(alias.lower() in text for alias in config.get("aliases", [])):
                return dispute_id
        if any(word in text for word in ("辞退", "解除", "不用来了", "不用上班")):
            return "unlawful_termination"
        return "unlawful_termination"

    def get(self, dispute_type: str) -> dict[str, Any]:
        return self.disputes.get(dispute_type, self.disputes["unlawful_termination"])

    def prepare_state(self, state: CaseState) -> CaseState:
        if state.dispute_type == "unknown":
            state.dispute_type = self.classify(state.user_narrative)
        config = self.get(state.dispute_type)
        state.key_facts = [item["id"] for item in config["key_facts"]]
        state.missing_facts = [
            fact for fact in state.key_facts if not _has_value(state.facts.get(fact))
        ]
        state.legal_issues = [element["name"] for element in config["elements"]]
        evidence_names: list[str] = []
        for element in config["elements"]:
            for name in element.get("evidence_any", []):
                if name not in evidence_names:
                    evidence_names.append(name)
        state.key_evidence = evidence_names
        present = {item.name for item in state.evidence}
        state.missing_evidence = [name for name in evidence_names if name not in present]
        return state

    def question_specs(self, dispute_type: str) -> list[dict[str, Any]]:
        specs = self.get(dispute_type)["key_facts"]
        return sorted(specs, key=lambda item: item.get("priority", 0), reverse=True)


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != []


@lru_cache(maxsize=1)
def get_labor_model() -> LaborDomainModel:
    return LaborDomainModel()

