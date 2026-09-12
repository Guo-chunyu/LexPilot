"""Report the residual gap set of the enumerative consultation coverage matrix.

Usage:
    python scripts/report_consultation_coverage.py
    python scripts/report_consultation_coverage.py --json evaluation/consultation_coverage.json

The matrix walks every domain's evidence slots against a fixed set of natural
availability frames plus the "a counterparty claim must not replace the user's
figure" probes. A clean run means every combination currently reaches a
consistent structured state. The script never writes unless --json is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.workflow import LexPilotEngine  # noqa: E402
from evaluation.consultation_coverage import (  # noqa: E402
    audit_assertion_probe,
    audit_coverage_probe,
    generate_assertion_probes,
    generate_coverage_probes,
)


def run_probe(probe, audit):
    engine = LexPilotEngine()
    state = None
    for message in probe.messages:
        state = engine.process(message, state)['case_state']
    return audit(probe, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', type=Path, default=None)
    args = parser.parse_args()

    families = [
        ('material', generate_coverage_probes(), audit_coverage_probe),
        ('assertion', generate_assertion_probes(), audit_assertion_probe),
    ]
    gaps: dict[str, str] = {}
    total = 0
    for family, probes, audit in families:
        failed = 0
        for probe in probes:
            total += 1
            failures = run_probe(probe, audit)
            if failures:
                failed += 1
                gaps[probe.probe_id] = '; '.join(failures)
        print(f'{family:<10} probes={len(probes):<4} gaps={failed}')
    print(f'\ntotal probes={total} gaps={len(gaps)}')
    for probe_id, reason in sorted(gaps.items()):
        print(f'  {probe_id}  ->  {reason}')
    if not gaps:
        print('  (none)')

    if args.json is not None:
        payload = {
            'schema_version': 1,
            'probe_total': total,
            'gap_total': len(gaps),
            'gaps': dict(sorted(gaps.items())),
        }
        out = args.json if args.json.is_absolute() else ROOT / args.json
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'\nwrote {out}')
    return 1 if gaps else 0


if __name__ == '__main__':
    raise SystemExit(main())
