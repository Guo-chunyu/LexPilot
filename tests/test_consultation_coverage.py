"""Guards for the enumerative coverage matrix itself.

The matrix is only meaningful if it keeps spanning every domain and every
evidence slot. These tests fail if coverage silently shrinks, for example when a
domain gains a material that no probe exercises.
"""

from collections import Counter

from backend.legal_domain.consultation.profiles import PROFILES
from evaluation.consultation_coverage import (
    DOMAIN_OPENERS,
    FRAME_TEMPLATES,
    generate_assertion_probes,
    generate_coverage_probes,
)

# `general` is the fallback profile used before a domain is identified; it has
# no routing opener of its own, so it is outside the coverage contract.
ROUTEABLE_DOMAINS = sorted(set(PROFILES) - {'general'})


def test_every_profiled_domain_has_a_coverage_opener():
    missing = sorted(set(ROUTEABLE_DOMAINS) - set(DOMAIN_OPENERS))
    assert not missing, f'domains without a coverage opener: {missing}'


def test_every_evidence_slot_is_exercised_by_at_least_one_frame():
    probes = generate_coverage_probes()
    covered = {(probe.domain, probe.material) for probe in probes}
    expected = {
        (domain, name)
        for domain in ROUTEABLE_DOMAINS
        for name, *_ in PROFILES[domain].evidence
    }
    assert expected - covered == set(), 'evidence slots with no coverage probe'


def test_every_frame_is_applied_to_every_evidence_slot():
    probes = generate_coverage_probes()
    per_slot = Counter((probe.domain, probe.material) for probe in probes)
    frames = len(FRAME_TEMPLATES)
    thin = sorted(slot for slot, count in per_slot.items() if count != frames)
    assert not thin, f'evidence slots missing frames: {thin}'


def test_assertion_probes_cover_the_documented_domains():
    domains = {probe.domain for probe in generate_assertion_probes()}
    assert domains == {'debt', 'housing', 'contract', 'consumer', 'enforcement'}
