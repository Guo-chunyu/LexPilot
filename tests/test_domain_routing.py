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


@pytest.mark.parametrize(
    'text',
    [
        # Round-30: common colloquial collision phrasings previously fell to general.
        '我开车把人撞了，对方要求赔偿，请给我方案。',
        '我被车撞了，对方不赔医药费，请给我方案。',
        '我的车停在路边被撞了，找不到人，请给我方案。',
        '我被追尾了，对方不赔，请给我方案。',
    ],
)
def test_colloquial_traffic_phrasings_route_to_traffic(text):
    assert identify_domains(text)[0] == 'traffic'


@pytest.mark.parametrize(
    'text',
    [
        # Round-35: rent disputes previously lost to debt's generic "欠我".
        '租客拖欠我两个月租金，请给我方案。',
        '对方拖欠租金一直不给，请给我方案。',
        '租客欠我租金还赖着不走，请给我方案。',
    ],
)
def test_rent_arrears_phrasings_route_to_housing(text):
    assert identify_domains(text)[0] == 'housing'


@pytest.mark.parametrize(
    'text',
    [
        # Round-40: the debtor side previously scored 0 (only "欠我" existed).
        '我欠他3万元',
        '我欠对方钱',
        '我欠张三3万',
    ],
)
def test_debtor_side_phrasings_route_to_debt(text):
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
