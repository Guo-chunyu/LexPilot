"""Stage 6 constraint extraction coverage matrix — locked by failing tests."""

from __future__ import annotations

from evaluation.consultation_constraint_coverage import (
    audit_phrasing_probe,
    audit_withdrawal_probe,
    generate_phrasing_probes,
    generate_withdrawal_probes,
)


def test_all_phrasing_probes_pass() -> None:
    for probe in generate_phrasing_probes():
        failures = audit_phrasing_probe(probe)
        assert not failures, f'phrasing probe failed: {probe.probe_id}: {failures}'


def test_all_withdrawal_probes_pass() -> None:
    for probe in generate_withdrawal_probes():
        failures = audit_withdrawal_probe(probe)
        assert not failures, f'withdrawal probe failed: {probe.probe_id}: {failures}'


def test_expected_negative_constraints_not_recorded() -> None:
    """Spot check: a normal sentence must not be recorded as a constraint."""
    from backend.legal_domain.consultation.intake import ingest_text
    from backend.legal_rl.state import CaseState

    state = CaseState()
    ingest_text('请给我方案', state)
    assert 'constraints' not in state.facts or not state.facts['constraints']


def test_contact_method_constraint_takes_one_formulation() -> None:
    """Spot check: contact-method constraint persists under varying wording."""
    from backend.legal_domain.consultation.intake import ingest_text
    from backend.legal_rl.state import CaseState

    state = CaseState()
    ingest_text('只接受书面沟通', state)
    assert 'constraints' in state.facts
    assert '书面' in state.facts['constraints']
