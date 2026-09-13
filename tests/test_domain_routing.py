"""Domain routing checks independent from retrieval labels."""

import json
from pathlib import Path

import pytest

from backend.legal_domain.consultation.profiles import identify_domains


@pytest.mark.parametrize(
    'text',
    [
        # Round-29: common spoken debt phrasings previously fell to ``general``.
        '朋友2019年借我3万元一直没还，请给我方案。',
        '朋友借我5万元，到现在都没还，请给我方案。',
        '我借出去的钱要不回来，请给我方案。',
        '我把钱借出去3万元，对方赖着不给，请给我方案。',
    ],
)
def test_colloquial_debt_phrasings_route_to_debt(text):
    assert identify_domains(text)[0] == 'debt'


def test_public_benchmark_queries_route_without_given_domain():
    benchmark = Path(__file__).parents[1] / "eval" / "consultation_benchmark.json"
    cases = json.loads(benchmark.read_text(encoding="utf-8"))
    errors = []
    for case in cases:
        routed = identify_domains(case["query"])[0]
        if routed != case["domain"]:
            errors.append((case["id"], case["domain"], routed))
    assert not errors
