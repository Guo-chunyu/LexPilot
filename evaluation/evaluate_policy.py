"""Compare Random, Rule-Based and DQN policies in the same simulator."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from backend.legal_rl.environment import LegalDecisionEnv
from backend.legal_rl.policy import LegalPolicy, RLPolicy, RandomPolicy, RuleBasedPolicy
from evaluation.metrics import EvaluationAccumulator, recall


def evaluate_policy(policy: LegalPolicy, cases_dir: Path, episodes: int = 60, seed: int = 42) -> dict:
    env = LegalDecisionEnv(cases_dir, seed=seed)
    metrics = EvaluationAccumulator()
    for episode in range(episodes):
        env.reset(seed=seed + episode, options={"case_index": episode})
        total_reward = 0.0
        success = False
        episode_premature_stop = False
        for _ in range(env.max_steps):
            action = policy.predict(env.state)
            _, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            metrics.total_actions += 1
            metrics.redundant_actions += int(info["redundant_action"])
            episode_premature_stop = episode_premature_stop or bool(info["premature_stop"])
            success = success or bool(info["success"])
            if terminated or truncated:
                break
        scenario = env.scenario
        found_facts = set(env.state.facts)
        found_evidence = {item.name for item in env.state.evidence}
        metrics.episodes += 1
        metrics.successes += int(success)
        metrics.premature_stops += int(episode_premature_stop)
        metrics.fact_recalls.append(recall(found_facts, set(scenario.get("key_facts", []))))
        metrics.evidence_recalls.append(recall(found_evidence, set(scenario.get("key_evidence", []))))
        metrics.steps.append(env.state.step_count)
        metrics.rewards.append(total_reward)
    return metrics.result()


def evaluate_all(
    cases_dir: str | Path = "datasets/synthetic_cases",
    model_path: str | Path = "models/dqn_labor.pt",
    episodes: int = 60,
    seed: int = 42,
) -> dict[str, dict]:
    cases = Path(cases_dir)
    model = Path(model_path)
    policies: dict[str, LegalPolicy] = {
        "random": RandomPolicy(seed=seed),
        "rule_based": RuleBasedPolicy(),
        "dqn": RLPolicy.load(model, allow_fallback=True),
    }
    results = {
        name: evaluate_policy(policy, cases, episodes=episodes, seed=seed)
        for name, policy in policies.items()
    }
    results["dqn"]["model_loaded"] = bool(getattr(policies["dqn"], "model", None))
    return results


def write_results(results: dict[str, dict], json_path: Path, csv_path: Path) -> None:
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [{"policy": policy, **metrics} for policy, metrics in results.items()]
    fieldnames = ["policy"] + sorted({key for row in rows for key in row if key != "policy"})
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="datasets/synthetic_cases")
    parser.add_argument("--model", default="models/dqn_labor.pt")
    parser.add_argument("--episodes", type=int, default=60)
    parser.add_argument("--json", default="evaluation_results.json")
    parser.add_argument("--csv", default="evaluation_results.csv")
    args = parser.parse_args()
    results = evaluate_all(args.cases, args.model, args.episodes)
    write_results(results, Path(args.json), Path(args.csv))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
