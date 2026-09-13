"""Round-27: a wage-arrears total must not be read as the monthly wage."""

import pytest

from backend.legal_domain.labor.facts import _monthly_salary_amount


@pytest.mark.parametrize(
    'text, expected',
    [
        # Arrears constructions — the amount is the sum owed, not the wage.
        ('公司拖欠我工资3万元', None),
        ('老板拖欠我工资2万', None),
        ('公司补发工资5万元', None),
        ('公司克扣我工资1万元', None),
        ('公司少发我工资3000元', None),
        # Genuine monthly-wage expressions must still parse.
        ('月工资8000元', 8000.0),
        ('月薪1.2万', 12000.0),
        ('每个月10000元', 10000.0),
        ('一个月一万', 10000.0),
        ('税前工资一个月是12,500元', 12500.0),
        ('一万块一个月', 10000.0),
        # An explicit monthly marker wins even alongside an arrears clause.
        ('公司拖欠我工资3万元，月薪是1万元', 10000.0),
        ('每月工资3万元，公司拖欠了两个月', 30000.0),
    ],
)
def test_arrears_is_not_monthly_wage(text, expected):
    assert _monthly_salary_amount(text) == expected
