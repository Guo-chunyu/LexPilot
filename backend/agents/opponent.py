"""Structured employer/opposing-counsel simulation for labor disputes."""

from __future__ import annotations

from backend.legal_rl.state import CaseState, EvidenceStatus, RiskItem


DEFENSES = {
    "probation_termination": [
        "用人单位可能主张劳动者在试用期内被证明不符合已明确告知的录用条件。",
        "用人单位可能主张已有客观考核标准和考核记录支持解除。",
    ],
    "unlawful_termination": [
        "用人单位可能主张解除基于严重违纪或合法有效的规章制度。",
        "用人单位可能否认已经作出最终解除决定。",
    ],
    "unsigned_contract": [
        "用人单位可能主张双方已签署电子合同或劳动者拒绝签署。",
        "用人单位可能争议实际用工起始日期或双倍工资计算期间。",
    ],
    "wage_arrears": [
        "用人单位可能主张争议款项属于绩效、报销或未满足条件的奖金。",
        "用人单位可能争议工资标准、已支付金额或仲裁时效。",
    ],
    "overtime": [
        "用人单位可能主张加班未经安排或审批，相关在线记录不能证明实际工作。",
        "用人单位可能主张已安排调休或实行特殊工时制度。",
    ],
    "compensation": [
        "用人单位可能主张解除不属于应支付补偿或赔偿金的法定情形。",
        "用人单位可能争议工作年限、月工资基数或已支付款项。",
    ],
}


def simulate_opponent(state: CaseState) -> dict:
    weak_gaps = [
        gap for gap in state.evidence_gaps
        if gap.status in {EvidenceStatus.MISSING, EvidenceStatus.PARTIAL, EvidenceStatus.CONFLICT}
    ]
    weak_points = [f"{gap.name}：{gap.reason}" for gap in weak_gaps]
    missing = []
    for gap in weak_gaps:
        for name in gap.missing_evidence[:2]:
            if name not in missing:
                missing.append(name)
    base = 0.25 + 0.1 * len(weak_gaps) + 0.25 * state.contradiction_score
    risk_level = min(round(base, 2), 1.0)
    analysis = {
        "arguments": DEFENSES.get(state.dispute_type, DEFENSES["unlawful_termination"]),
        "weak_points": weak_points,
        "missing_evidence": missing,
        "possible_defenses": DEFENSES.get(state.dispute_type, []),
        "risk_level": risk_level,
    }
    state.opponent_analysis = analysis
    state.risks = [
        RiskItem(
            name="对方抗辩风险",
            description=(weak_points[0] if weak_points else "当前主要要素已有初步支持。"),
            level=risk_level,
        )
    ]
    return analysis

