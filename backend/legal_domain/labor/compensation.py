"""Deterministic and traceable labor compensation calculations."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CompensationMethod(str, Enum):
    N = "N"
    N_PLUS_1 = "N+1"
    TWO_N = "2N"
    UNSIGNED_DOUBLE_WAGE = "UNSIGNED_DOUBLE_WAGE"


class CompensationResult(BaseModel):
    method: CompensationMethod
    inputs: dict[str, float]
    formula: str
    coefficient: float = Field(ge=0)
    amount: float = Field(ge=0)
    basis: list[dict[str, str]]
    assumptions: list[str] = Field(default_factory=list)


class CompensationCalculator:
    """Calculate N, N+1, 2N and unsigned-contract double wage."""

    @staticmethod
    def calculate(
        method: CompensationMethod | str,
        monthly_salary: float,
        service_months: float = 0,
        unsigned_months: float = 0,
        local_average_salary: float | None = None,
    ) -> CompensationResult:
        selected = CompensationMethod(method)
        if monthly_salary < 0 or service_months < 0 or unsigned_months < 0:
            raise ValueError("Salary and month counts must be non-negative")

        salary_base = Decimal(str(monthly_salary))
        assumptions: list[str] = []
        capped_years = False
        if local_average_salary and local_average_salary > 0:
            cap = Decimal(str(local_average_salary)) * Decimal("3")
            if salary_base > cap:
                salary_base = cap
                capped_years = True
                assumptions.append("月工资高于当地上年度职工月平均工资三倍，按三倍封顶基数计算。")

        if selected == CompensationMethod.UNSIGNED_DOUBLE_WAGE:
            eligible_months = min(max(unsigned_months - 1.0, 0.0), 11.0)
            coefficient = Decimal(str(eligible_months))
            amount = salary_base * coefficient
            formula = f"{_fmt(salary_base)} × {eligible_months:g}个可计双倍工资月份"
            basis = [{
                "law": "中华人民共和国劳动合同法",
                "article": "第八十二条",
                "source": "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/fl/202011/t20201102_394622_wap.html",
            }]
        else:
            n = _service_year_coefficient(service_months)
            if capped_years and n > Decimal("12"):
                n = Decimal("12")
                assumptions.append("适用三倍工资封顶时，计算经济补偿的年限最高按十二年。")
            if selected == CompensationMethod.N:
                coefficient = n
            elif selected == CompensationMethod.N_PLUS_1:
                coefficient = n + Decimal("1")
                assumptions.append("N+1 仅适用于符合法定无过失性解除且未提前三十日书面通知等情形。")
            else:
                coefficient = n * Decimal("2")
                assumptions.append("2N 以解除被认定违法且不继续履行为前提。")
            amount = salary_base * coefficient
            formula = f"{_fmt(salary_base)} × {float(coefficient):g}个月工资"
            basis = [
                {
                    "law": "中华人民共和国劳动合同法",
                    "article": "第四十七条",
                    "source": "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html",
                }
            ]
            if selected == CompensationMethod.N_PLUS_1:
                basis.append({
                    "law": "中华人民共和国劳动合同法",
                    "article": "第四十条",
                    "source": "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/fl/202011/t20201102_394622_wap.html",
                })
            elif selected == CompensationMethod.TWO_N:
                basis.append({
                    "law": "中华人民共和国劳动合同法",
                    "article": "第八十七条",
                    "source": "https://www.mohrss.gov.cn/xxgk2020/fdzdgknr/zcfg/fl/202011/t20201102_394622_wap.html",
                })

        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return CompensationResult(
            method=selected,
            inputs={
                "monthly_salary": monthly_salary,
                "service_months": service_months,
                "unsigned_months": unsigned_months,
                "local_average_salary": local_average_salary or 0,
            },
            formula=formula,
            coefficient=float(coefficient),
            amount=float(rounded),
            basis=basis,
            assumptions=assumptions,
        )


def estimate_from_state(facts: dict[str, Any], dispute_type: str) -> dict[str, Any]:
    salary = facts.get("monthly_salary")
    if salary is None:
        return {
            "status": "INSUFFICIENT_INPUT",
            "missing_inputs": ["monthly_salary"],
            "message": "缺少月工资，暂不能计算。",
        }
    if dispute_type == "unsigned_contract":
        missing = [] if facts.get("unsigned_months") is not None else ["unsigned_months"]
        if missing:
            return {"status": "INSUFFICIENT_INPUT", "missing_inputs": missing, "message": "缺少未签合同月数。"}
        method = CompensationMethod.UNSIGNED_DOUBLE_WAGE
    elif "违法" in str(facts.get("termination_type", "")) or dispute_type in {"unlawful_termination", "probation_termination"}:
        method = CompensationMethod.TWO_N
    else:
        method = CompensationMethod.N
    result = CompensationCalculator.calculate(
        method=method,
        monthly_salary=float(salary),
        service_months=float(facts.get("employment_duration_months", 0)),
        unsigned_months=float(facts.get("unsigned_months", 0)),
        local_average_salary=(
            float(facts["local_average_salary"])
            if facts.get("local_average_salary") is not None
            else None
        ),
    )
    payload = result.model_dump(mode="json")
    payload["status"] = "ESTIMATE_ONLY"
    payload["message"] = "仅按当前输入计算，最终适用 N、N+1 或 2N 取决于解除性质及当地裁审口径。"
    return payload


def _service_year_coefficient(service_months: float) -> Decimal:
    months = Decimal(str(service_months))
    full_years = months // Decimal("12")
    remainder = months - full_years * Decimal("12")
    if remainder >= Decimal("6"):
        fraction = Decimal("1")
    elif remainder > 0:
        fraction = Decimal("0.5")
    else:
        fraction = Decimal("0")
    return full_years + fraction


def _fmt(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):f}"

