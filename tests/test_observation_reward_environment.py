import numpy as np

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.environment import LegalDecisionEnv
from backend.legal_rl.observation import OBSERVATION_NAMES, state_to_vector
from backend.legal_rl.policy import RuleBasedPolicy
from backend.legal_rl.reward import calculate_reward
from backend.legal_rl.state import CaseState


def test_state_vector_is_eight_normalized_values():
    state = CaseState(
        fact_completeness=0.5,
        evidence_completeness=0.25,
        legal_confidence=1.0,
        issue_coverage=0.4,
        contradiction_score=0.2,
        key_facts=["a", "b"],
        missing_facts=["b"],
        key_evidence=["x", "y", "z", "q"],
        missing_evidence=["y"],
        step_count=5,
        max_steps=10,
    )
    vector = state_to_vector(state)
    assert vector.shape == (len(OBSERVATION_NAMES),) == (8,)
    assert vector.dtype == np.float32
    assert np.all((vector >= 0) & (vector <= 1))
    assert vector[5] == 0.5
    assert vector[6] == 0.25


def test_reward_breakdown_rewards_information_and_penalizes_stop():
    previous = CaseState(fact_completeness=0.2, evidence_completeness=0.1)
    current = CaseState(fact_completeness=0.5, evidence_completeness=0.4)
    gain = calculate_reward(previous, current, LegalAction.ASK_FACT)
    early = calculate_reward(previous, previous, LegalAction.STOP, premature_stop=True)
    assert gain.fact_gain > 0
    assert gain.evidence_gain > 0
    assert early.premature_stop == -5.0
    assert early.total < gain.total


def test_environment_reset_step_and_rule_policy_completion():
    env = LegalDecisionEnv("datasets/synthetic_cases", max_steps=20)
    observation, info = env.reset(options={"case_index": 1})
    assert observation.shape == (8,)
    assert info["case_id"] == "labor_002"
    policy = RuleBasedPolicy()
    actions = []
    final_info = {}
    for _ in range(20):
        action = policy.predict(env.state)
        actions.append(action)
        _, _, terminated, truncated, final_info = env.step(action)
        if terminated or truncated:
            break
    assert LegalAction.SEARCH_LAW in actions
    assert LegalAction.REQUEST_EVIDENCE in actions
    assert LegalAction.SIMULATE_OPPONENT in actions
    assert LegalAction.VERIFY in actions
    assert actions[-1] == LegalAction.STOP
    assert final_info["success"] is True
