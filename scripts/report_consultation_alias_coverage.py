"""Coverage report for Stage 5 evidence alias matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.legal_domain.consultation.profiles import PROFILES
from evaluation.consultation_alias_coverage import (
    audit_alias_probe,
    audit_scope_probe,
    generate_alias_probes,
    generate_scope_probes,
)


def _probe_label(probe_id: str, **extra: str) -> str:
    parts = [probe_id]
    parts.extend(f'{k}={v}' for k, v in extra.items())
    return ' '.join(parts)


def run_alias_probes() -> list[tuple[str, list[str]]]:
    results: list[tuple[str, list[str]]] = []
    for probe in generate_alias_probes():
        failures = audit_alias_probe(probe)
        if failures:
            results.append((_probe_label(probe.probe_id, phrase=probe.phrase), failures))
    return results


def run_scope_probes() -> list[tuple[str, list[str]]]:
    from evaluation.consultation_alias_coverage import EVIDENCE_ALIASES

    results: list[tuple[str, list[str]]] = []
    for probe in generate_scope_probes():
        siblings = tuple(name for name in EVIDENCE_ALIASES if name != probe.canonical)
        failures = audit_scope_probe(probe, siblings)
        if failures:
            results.append(
                (
                    _probe_label(probe.probe_id, canonical=probe.canonical, sentence=probe.sentence),
                    failures,
                )
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    alias_failures = run_alias_probes()
    scope_failures = run_scope_probes()

    total_alias = len(generate_alias_probes())
    total_scope = len(generate_scope_probes())

    if args.json:
        json.dump(
            {
                'alias': {'probes': total_alias, 'failures': alias_failures},
                'scope': {'probes': total_scope, 'failures': scope_failures},
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write('\n')
    else:
        print(f'alias   probes={total_alias}  gaps={len(alias_failures)}')
        for label, failures in alias_failures:
            print(f'  {label}')
            for failure in failures:
                print(f'    - {failure}')
        print(f'scope   probes={total_scope}  gaps={len(scope_failures)}')
        for label, failures in scope_failures:
            print(f'  {label}')
            for failure in failures:
                print(f'    - {failure}')

        # also list enrolled alias counts per profile, so missing-alias issues
        # surface here without a hand-picked red-team round.
        print(f'\nprofiles={len(PROFILES)}')
    return 0 if not (alias_failures or scope_failures) else 1


if __name__ == '__main__':
    raise SystemExit(main())
