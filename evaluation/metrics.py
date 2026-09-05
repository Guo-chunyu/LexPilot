"""Metrics required by the first-stage task specification."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvaluationAccumulator:
    episodes: int = 0
    successes: int = 0
    fact_recalls: list[float] = field(default_factory=list)
    evidence_recalls: list[float] = field(default_factory=list)
    steps: list[int] = field(default_factory=list)
    redundant_actions: int = 0
    total_actions: int = 0
    premature_stops: int = 0
    rewards: list[float] = field(default_factory=list)

    def result(self) -> dict[str, float | int]:
        return {
            "episodes": self.episodes,
            "task_success_rate": _mean_bool(self.successes, self.episodes),
            "critical_fact_recall": _mean(self.fact_recalls),
            "evidence_recall": _mean(self.evidence_recalls),
            "average_steps": _mean(self.steps),
            "redundant_action_rate": _mean_bool(self.redundant_actions, self.total_actions),
            "premature_stop_rate": _mean_bool(self.premature_stops, self.episodes),
            "average_reward": _mean(self.rewards),
        }


def recall(found: set[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(found & expected) / len(expected)


def _mean(values: list[float | int]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _mean_bool(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0

