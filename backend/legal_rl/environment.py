"""Gymnasium environment for simulated sequential labor-case investigation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from backend.agents.judge import evaluate_case_state
from backend.agents.opponent import simulate_opponent
from backend.agents.report import build_final_report
from backend.legal_domain.labor.case_search import search_similar_cases
from backend.legal_domain.labor.compensation import estimate_from_state
from backend.legal_domain.labor.evidence_gap import detect_evidence_gaps
from backend.legal_domain.labor.legal_search import search_law_for_state
from backend.legal_domain.labor.model import get_labor_model
from backend.legal_rl.actions import ACTION_TO_NODE, LegalAction
from backend.legal_rl.observation import state_to_vector
from backend.legal_rl.reward import calculate_reward
from backend.legal_rl.state import CaseState


class LegalDecisionEnv(gym.Env):
    """Expose hidden case truth through actions without calling a real user."""

    metadata = {"render_modes": []}

    def __init__(self, cases: list[dict] | dict | str | Path, max_steps: int = 20, seed: int = 42) -> None:
        super().__init__()
        self.cases = _load_cases(cases)
        if not self.cases:
            raise ValueError("LegalDecisionEnv requires at least one simulated case")
        self.max_steps = max_steps
        self.action_space = spaces.Discrete(len(LegalAction), seed=seed)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(8,), dtype=np.float32)
        self.state = CaseState(max_steps=max_steps)
        self.scenario: dict[str, Any] = {}
        self._case_index = -1

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if options and "case_index" in options:
            self._case_index = int(options["case_index"]) % len(self.cases)
        else:
            self._case_index = (self._case_index + 1) % len(self.cases)
        self.scenario = self.cases[self._case_index]
        self.state = CaseState(
            case_id=self.scenario["case_id"],
            dispute_type=self.scenario["dispute_type"],
            user_narrative=self.scenario.get("initial_narrative", ""),
            facts=dict(self.scenario.get("initial_facts", {})),
            max_steps=self.max_steps,
        )
        for name in self.scenario.get("initial_evidence", []):
            self.state.add_evidence(name, source="initial_case")
        get_labor_model().prepare_state(self.state)
        detect_evidence_gaps(self.state)
        return state_to_vector(self.state), {"case_id": self.state.case_id}

    def step(self, action: int | LegalAction):
        previous = self.state.model_copy(deep=True)
        invalid = False
        try:
            selected = LegalAction(int(action))
        except (ValueError, TypeError):
            selected = LegalAction.ESCALATE_HUMAN
            invalid = True
        if selected == LegalAction.ESCALATE_HUMAN and self.state.step_count < self.max_steps - 1:
            invalid = True

        before_signature = _progress_signature(self.state)
        result = self._execute(selected, invalid=invalid)
        detect_evidence_gaps(self.state)
        after_signature = _progress_signature(self.state)
        redundant = before_signature == after_signature and selected not in {
            LegalAction.STOP, LegalAction.ESCALATE_HUMAN
        }
        premature = selected == LegalAction.STOP and not (
            self.state.judge_result and self.state.judge_result.can_stop
        )
        successful = selected == LegalAction.STOP and not premature
        if successful:
            self.state.done = True
            build_final_report(self.state)

        breakdown = calculate_reward(
            previous,
            self.state,
            selected,
            invalid_action=invalid,
            redundant_action=redundant,
            successful_resolution=successful,
            premature_stop=premature,
        )
        self.state.record_action(
            selected,
            reason="simulator action",
            node=ACTION_TO_NODE[selected],
            result=result,
            reward_breakdown=breakdown.model_dump(),
        )
        terminated = bool(self.state.done or self.state.escalated)
        truncated = self.state.step_count >= self.max_steps and not terminated
        info = {
            "case_id": self.state.case_id,
            "action": selected.name,
            "reward_breakdown": breakdown.model_dump(),
            "state": self.state.public_dict(),
            "success": successful,
            "premature_stop": premature,
            "redundant_action": redundant,
            "invalid_action": invalid,
        }
        return state_to_vector(self.state), breakdown.total, terminated, truncated, info

    def _execute(self, action: LegalAction, invalid: bool = False) -> str:
        if invalid:
            return "动作编号无效，转人工复核。"
        truth = self.scenario.get("facts", {})
        available = self.scenario.get("available_evidence", [])
        if action == LegalAction.ASK_FACT:
            for key in self.scenario.get("key_facts", list(truth)):
                if key not in self.state.facts and key in truth:
                    self.state.apply_facts({key: truth[key]})
                    return f"模拟用户补充事实：{key}"
            return "没有新的关键事实可披露。"
        if action == LegalAction.REQUEST_EVIDENCE:
            present = {item.name for item in self.state.evidence}
            for name in available:
                if name not in present:
                    self.state.add_evidence(name, source="simulator")
                    return f"模拟环境提供证据：{name}"
            return "没有新的可用证据。"
        if action == LegalAction.SEARCH_LAW:
            self.state.retrieved_laws = search_law_for_state(self.state)
            return f"检索到 {len(self.state.retrieved_laws)} 条可追溯法源。"
        if action == LegalAction.SEARCH_CASE:
            self.state.retrieved_cases = search_similar_cases(self.state.dispute_type)
            if not self.state.retrieved_cases:
                self.state.retrieved_cases = [{"case_id": self.state.case_id, "dispute_type": self.state.dispute_type, "human_reviewed": False}]
            return f"检索到 {len(self.state.retrieved_cases)} 个同类模拟案例。"
        if action == LegalAction.SIMULATE_OPPONENT:
            analysis = simulate_opponent(self.state)
            return f"生成 {len(analysis['arguments'])} 项可能抗辩。"
        if action == LegalAction.VERIFY:
            result = evaluate_case_state(self.state)
            return f"Judge can_stop={result.can_stop}: {result.reason}"
        if action == LegalAction.CALCULATE:
            self.state.compensation_estimate = estimate_from_state(self.state.facts, self.state.dispute_type)
            return self.state.compensation_estimate.get("message", "完成赔偿估算。")
        if action == LegalAction.GENERATE_DOCUMENT:
            build_final_report(self.state)
            return "已生成结构化法律行动方案草稿。"
        if action == LegalAction.STOP:
            return "策略请求停止。"
        self.state.escalated = True
        self.state.done = True
        return "案件超出自动流程把握，转人工复核。"


def _load_cases(value: list[dict] | dict | str | Path) -> list[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    path = Path(value)
    if path.is_dir():
        cases = []
        for file_path in sorted(path.glob("*.json")):
            with file_path.open("r", encoding="utf-8") as handle:
                cases.append(json.load(handle))
        return cases
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else [data]


def _progress_signature(state: CaseState) -> tuple:
    return (
        len(state.facts), len(state.evidence), len(state.retrieved_laws),
        len(state.retrieved_cases), bool(state.opponent_analysis),
        bool(state.judge_result), bool(state.compensation_estimate), bool(state.final_report),
    )
