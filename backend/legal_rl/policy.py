"""Rule, random and DQN-backed policy implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from random import Random

from pydantic import BaseModel

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.observation import state_to_vector
from backend.legal_rl.state import CaseState, EvidenceStatus


class PolicyDecision(BaseModel):
    action: LegalAction
    reason: str


class LegalPolicy(ABC):
    """Policies decide the next action; they never generate natural language."""

    @abstractmethod
    def decide(self, state: CaseState) -> PolicyDecision:
        raise NotImplementedError

    def predict(self, state: CaseState) -> LegalAction:
        return self.decide(state).action


class RuleBasedPolicy(LegalPolicy):
    """Transparent baseline centralized in one module."""

    def decide(self, state: CaseState) -> PolicyDecision:
        if state.done:
            return PolicyDecision(action=LegalAction.STOP, reason="案件流程已经结束。")
        if state.step_count >= state.max_steps:
            return PolicyDecision(action=LegalAction.ESCALATE_HUMAN, reason="已达到最大决策步数。")
        compensation_relevant = state.dispute_type in {
            "probation_termination", "unlawful_termination", "unsigned_contract", "compensation"
        }
        if state.fact_completeness < 0.70 and state.missing_facts:
            return PolicyDecision(action=LegalAction.ASK_FACT, reason="关键事实完整度低于 70%。")
        if compensation_relevant and "monthly_salary" in state.missing_facts:
            return PolicyDecision(action=LegalAction.ASK_FACT, reason="赔偿估算仍缺少月工资基数。")
        if state.dispute_type == "unsigned_contract" and "unsigned_months" in state.missing_facts:
            return PolicyDecision(action=LegalAction.ASK_FACT, reason="双倍工资估算仍缺少未签合同期间。")
        if state.evidence_completeness < 0.65 and not state.evidence_collection_exhausted:
            return PolicyDecision(action=LegalAction.REQUEST_EVIDENCE, reason="核心证据链尚未达到 65% 的调查目标。")
        if not state.retrieved_laws:
            return PolicyDecision(action=LegalAction.SEARCH_LAW, reason="尚无可追溯的劳动法依据。")
        if not state.retrieved_cases:
            return PolicyDecision(action=LegalAction.SEARCH_CASE, reason="需要检索同类模拟案例用于策略对照。")
        if not state.opponent_analysis:
            return PolicyDecision(action=LegalAction.SIMULATE_OPPONENT, reason="尚未检验用人单位可能抗辩。")
        if compensation_relevant and not state.compensation_estimate and state.facts.get("monthly_salary") is not None:
            return PolicyDecision(action=LegalAction.CALCULATE, reason="已具备赔偿金额的基础输入。")
        if state.facts.get("document_requested") and not state.final_report:
            return PolicyDecision(action=LegalAction.GENERATE_DOCUMENT, reason="用户请求生成结构化行动方案。")
        if state.judge_result is None:
            return PolicyDecision(action=LegalAction.VERIFY, reason="需要 Judge 检查事实、证据、法源与冲突。")
        if state.judge_result.can_stop:
            return PolicyDecision(action=LegalAction.STOP, reason=state.judge_result.reason)
        if state.missing_facts:
            return PolicyDecision(action=LegalAction.ASK_FACT, reason=state.judge_result.reason)
        if (
            any(gap.status != EvidenceStatus.PROVEN for gap in state.evidence_gaps)
            and not state.evidence_collection_exhausted
        ):
            return PolicyDecision(action=LegalAction.REQUEST_EVIDENCE, reason=state.judge_result.reason)
        if state.evidence_collection_exhausted:
            return PolicyDecision(
                action=LegalAction.ESCALATE_HUMAN,
                reason="用户已确认没有更多材料，停止重复追问并按现有材料形成阶段性结果。",
            )
        return PolicyDecision(action=LegalAction.ESCALATE_HUMAN, reason=state.judge_result.reason)


class RandomPolicy(LegalPolicy):
    def __init__(self, seed: int = 42) -> None:
        self._random = Random(seed)

    def decide(self, state: CaseState) -> PolicyDecision:
        action = self._random.choice(list(LegalAction))
        return PolicyDecision(action=action, reason="随机基线策略。")


class RLPolicy(LegalPolicy):
    """Load a trained DQN; safely fall back to the rule baseline when unavailable."""

    def __init__(self, model=None, fallback: LegalPolicy | None = None, device: str = "cpu") -> None:
        self.model = model
        self.fallback = fallback or RuleBasedPolicy()
        self.device = device

    @classmethod
    def load(cls, path: str | Path, device: str = "cpu", allow_fallback: bool = True) -> "RLPolicy":
        try:
            import torch
            from backend.legal_rl.dqn import DQNNetwork

            checkpoint = torch.load(Path(path), map_location=device, weights_only=False)
            model = DQNNetwork(
                input_dim=int(checkpoint.get("input_dim", 8)),
                output_dim=int(checkpoint.get("output_dim", len(LegalAction))),
                hidden_dim=int(checkpoint.get("hidden_dim", 64)),
            )
            model.load_state_dict(checkpoint["model_state_dict"])
            model.eval()
            return cls(model=model, device=device)
        except Exception:
            if allow_fallback:
                return cls(model=None, device=device)
            raise

    def decide(self, state: CaseState) -> PolicyDecision:
        if self.model is None:
            fallback = self.fallback.decide(state)
            return PolicyDecision(action=fallback.action, reason=f"DQN 不可用，回退规则策略：{fallback.reason}")
        import torch

        vector = torch.as_tensor(state_to_vector(state), dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q_values = self.model(vector).squeeze(0)
            allowed = {action.value for action in valid_actions(state)}
            masked = torch.full_like(q_values, float("-inf"))
            for action_id in allowed:
                masked[action_id] = q_values[action_id]
            action_id = int(masked.argmax().item())
        return PolicyDecision(action=LegalAction(action_id), reason="DQN 根据结构化状态向量选择离散动作。")


def create_policy(policy_type: str = "rule", model_path: str | None = None) -> LegalPolicy:
    selected = policy_type.lower().strip()
    if selected == "random":
        return RandomPolicy()
    if selected in {"dqn", "rl"}:
        path = Path(model_path or "models/dqn_labor.pt").resolve()
        modified_ns = path.stat().st_mtime_ns if path.exists() else -1
        return _load_rl_policy(str(path), modified_ns)
    return RuleBasedPolicy()


@lru_cache(maxsize=8)
def _load_rl_policy(path: str, modified_ns: int) -> RLPolicy:
    """Load each checkpoint version once instead of once per graph action."""

    del modified_ns
    return RLPolicy.load(path)


def valid_actions(state: CaseState) -> list[LegalAction]:
    """Safety mask: remove impossible/redundant actions without ranking the rest."""

    if state.done:
        return [LegalAction.STOP]
    allowed: list[LegalAction] = []
    if state.missing_facts:
        allowed.append(LegalAction.ASK_FACT)
    if state.evidence_completeness < 0.65 and not state.evidence_collection_exhausted:
        allowed.append(LegalAction.REQUEST_EVIDENCE)
    if not state.retrieved_laws:
        allowed.append(LegalAction.SEARCH_LAW)
    if not state.retrieved_cases:
        allowed.append(LegalAction.SEARCH_CASE)
    if not state.opponent_analysis:
        allowed.append(LegalAction.SIMULATE_OPPONENT)
    compensation_relevant = state.dispute_type in {
        "probation_termination", "unlawful_termination", "unsigned_contract", "compensation"
    }
    has_calculation_inputs = state.facts.get("monthly_salary") is not None
    if state.dispute_type == "unsigned_contract":
        has_calculation_inputs = has_calculation_inputs and state.facts.get("unsigned_months") is not None
    if compensation_relevant and has_calculation_inputs and not state.compensation_estimate:
        allowed.append(LegalAction.CALCULATE)
    if state.facts.get("document_requested") and not state.final_report:
        allowed.append(LegalAction.GENERATE_DOCUMENT)
    if state.retrieved_laws and state.opponent_analysis and state.judge_result is None:
        allowed.append(LegalAction.VERIFY)
    if state.judge_result and state.judge_result.can_stop:
        allowed.append(LegalAction.STOP)
    if state.step_count >= state.max_steps - 1:
        allowed.append(LegalAction.ESCALATE_HUMAN)
    return list(dict.fromkeys(allowed)) or [LegalAction.ESCALATE_HUMAN]
