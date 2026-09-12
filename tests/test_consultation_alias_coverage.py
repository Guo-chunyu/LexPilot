"""Stage 5 evidence alias coverage matrix - locked by failing test.

The Stage 1 coverage matrix probes actor x verb x material x availability-frame.
This module adds the missing axis: natural alias coverage + scope-negation
boundaries. If a new alias is missing, this test fails; if a new alias is added
without smoke coverage, the test reminds us to add probes.
"""

from __future__ import annotations

from backend.legal_domain.consultation.intake import EVIDENCE_ALIASES
from evaluation.consultation_alias_coverage import (
    audit_alias_probe,
    audit_scope_probe,
    generate_alias_probes,
    generate_scope_probes,
)


def test_all_registered_aliases_have_probes() -> None:
    """Every key in EVIDENCE_ALIASES must have at least one natural phrasing
    probe, otherwise the matrix is hollow for that alias."""
    canonical_names = set(EVIDENCE_ALIASES.keys())
    probed_names = {probe.canonical for probe in generate_alias_probes()}
    missing = canonical_names - probed_names
    assert not missing, f'canonical materials without alias probes: {sorted(missing)}'


def test_all_alias_probes_pass() -> None:
    for probe in generate_alias_probes():
        failures = audit_alias_probe(probe)
        assert not failures, (
            f'alias probe failed: {probe.probe_id} phrase={probe.phrase!r} '
            f'failures={failures}'
        )


def test_all_scope_probes_pass() -> None:
    siblings = tuple(name for name in EVIDENCE_ALIASES if name)
    for probe in generate_scope_probes():
        failures = audit_scope_probe(probe, siblings)
        assert not failures, (
            f'scope probe failed: {probe.probe_id} canonical={probe.canonical} '
            f'sentence={probe.sentence!r} failures={failures}'
        )


def test_scope_probe_keeps_sibling_when_other_material_unavailable() -> None:
    """"我有转账记录，借条我这边拿不到" must NOT mark 转账记录 unavailable."""
    siblings = tuple(EVIDENCE_ALIASES.keys())
    failures = audit_scope_probe(
        type('P', (), {
            'probe_id': 'sibling_safety',
            'canonical': '转账记录',
            'sentence': '我有转账记录，借条我这边拿不到',
            'expect_mentioned': True,
            'expect_unavailable': False,
        })(),
        siblings,
    )
    assert not failures, failures
