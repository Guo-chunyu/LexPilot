"""Run one deterministic red-team generator through the public engine."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.workflow import LexPilotEngine
from evaluation import consultation_red_team as matrix


def run(generator_name: str, seed: int) -> list[dict]:
    generator = getattr(matrix, generator_name)
    results = []
    for case in generator(seed):
        engine = LexPilotEngine()
        state = None
        replies = []
        for message in case.messages:
            result = engine.process(message, state)
            state = result['case_state']
            replies.append(result['reply'])
        results.append({
            'case_id': case.case_id,
            'failures': matrix.audit_red_team_result(case, state, replies),
        })
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('generator')
    parser.add_argument('seed', type=int)
    args = parser.parse_args()
    output = run(args.generator, args.seed)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(1 if any(item['failures'] for item in output) else 0)
