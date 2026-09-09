"""Domain routing checks independent from retrieval labels."""

import json
from pathlib import Path

from backend.legal_domain.consultation.profiles import identify_domains


def test_public_benchmark_queries_route_without_given_domain():
    benchmark = Path(__file__).parents[1] / "eval" / "consultation_benchmark.json"
    cases = json.loads(benchmark.read_text(encoding="utf-8"))
    errors = []
    for case in cases:
        routed = identify_domains(case["query"])[0]
        if routed != case["domain"]:
            errors.append((case["id"], case["domain"], routed))
    assert not errors
