"""CLI for training the first-stage DQN baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from backend.legal_rl.dqn import save_dqn, train_dqn
from backend.legal_rl.environment import LegalDecisionEnv


def main() -> None:
    parser = argparse.ArgumentParser(description="Train LexPilot DQN baseline")
    parser.add_argument("--cases", default="datasets/synthetic_cases")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--output", default="models/dqn_labor.pt")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cases = Path(args.cases)
    model, rewards = train_dqn(
        lambda: LegalDecisionEnv(cases, seed=args.seed),
        episodes=args.episodes,
        seed=args.seed,
    )
    output = save_dqn(model, args.output, metadata={
        "episodes": args.episodes,
        "seed": args.seed,
        "last_10_mean_reward": sum(rewards[-10:]) / max(len(rewards[-10:]), 1),
    })
    print(f"model={output}")
    print(f"episodes={len(rewards)} last_reward={rewards[-1] if rewards else 0}")


if __name__ == "__main__":
    main()

