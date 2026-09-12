"""Coverage report for Stage 6 constraint extraction matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.consultation_constraint_coverage import (
    audit_phrasing_probe,
    audit_withdrawal_probe,
    generate_phrasing_probes,
    generate_withdrawal_probes,
)


def run_phrasing_probes() -> list[tuple[str, list[str]]]:
    results: list[tuple[str, list[str]]] = []
    for probe in generate_phrasing_probes():
        failures = audit_phrasing_probe(probe)
        if failures:
            results.append((probe.probe_id, failures))
    return results


def run_withdrawal_probes() -> list[tuple[str, list[str]]]:
    results: list[tuple[str, list[str]]] = []
    for probe in generate_withdrawal_probes():
        failures = audit_withdrawal_probe(probe)
        if failures:
            results.append((probe.probe_id, failures))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    phrasing = run_phrasing_probes()
    withdrawal = run_withdrawal_probes()

    total_phrasing = len(generate_phrasing_probes())
    total_withdrawal = len(generate_withdrawal_probes())

    if args.json:
        json.dump(
            {
                'phrasing': {'probes': total_phrasing, 'failures': phrasing},
                'withdrawal': {'probes': total_withdrawal, 'failures': withdrawal},
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write('\n')
    else:
        print(f'phrasing  probes={total_phrasing}  gaps={len(phrasing)}')
        for label, failures in phrasing:
            print(f'  {label}')
            for failure in failures:
                print(f'    - {failure}')
        print(f'withdrawal probes={total_withdrawal}  gaps={len(withdrawal)}')
        for label, failures in withdrawal:
            print(f'  {label}')
            for failure in failures:
                print(f'    - {failure}')
    return 0 if not (phrasing or withdrawal) else 1


if __name__ == '__main__':
    raise SystemExit(main())
