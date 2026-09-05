from datetime import date

from backend.legal_domain.labor.compensation import CompensationCalculator
from backend.legal_domain.labor.legal_search import search_law


def test_compensation_n_n_plus_1_two_n_and_unsigned_wage():
    assert CompensationCalculator.calculate("N", 10000, service_months=8).amount == 10000
    assert CompensationCalculator.calculate("N+1", 10000, service_months=8).amount == 20000
    assert CompensationCalculator.calculate("2N", 10000, service_months=8).amount == 20000
    unsigned = CompensationCalculator.calculate("UNSIGNED_DOUBLE_WAGE", 10000, unsigned_months=12)
    assert unsigned.coefficient == 11
    assert unsigned.amount == 110000
    assert unsigned.basis[0]["article"] == "第八十二条"


def test_temporal_law_search_filters_future_interpretation():
    before = search_law("劳动争议 司法解释", event_date=date(2024, 1, 1), limit=20)
    after = search_law("劳动争议 司法解释", event_date=date(2026, 1, 1), limit=20)
    assert not any(law.article == "法释〔2025〕12号" for law in before)
    assert any(law.article == "法释〔2025〕12号" for law in after)
    assert all(law.source_url.startswith("https://") for law in after)

