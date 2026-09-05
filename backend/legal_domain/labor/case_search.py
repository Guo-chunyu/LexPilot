"""Local synthetic-case search used by the SEARCH_CASE action."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "datasets" / "synthetic_cases"


def search_similar_cases(dispute_type: str, limit: int = 3, dataset_dir: Path | None = None) -> list[dict]:
    root = dataset_dir or DEFAULT_DATASET
    matches: list[dict] = []
    if not root.exists():
        return matches
    for path in sorted(root.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                case = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if case.get("dispute_type") == dispute_type:
            matches.append({
                "case_id": case.get("case_id"),
                "dispute_type": dispute_type,
                "difficulty": case.get("difficulty"),
                "legal_issues": case.get("legal_issues", []),
                "recommended_actions": case.get("recommended_actions", []),
                "human_reviewed": case.get("human_reviewed", False),
            })
        if len(matches) >= limit:
            break
    return matches

