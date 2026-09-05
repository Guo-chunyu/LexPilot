"""Generate deterministic labor cases for software/RL testing, not legal truth."""

from __future__ import annotations

import json
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parents[1] / "datasets" / "synthetic_cases"


TEMPLATES = {
    "probation_termination": {
        "narrative": "我在公司工作{months}个月，公司以试用期表现不合格为由通知我不用上班。",
        "facts": {
            "employment_duration_months": 8,
            "has_written_contract": True,
            "contract_term_months": 36,
            "probation_period_months": 6,
            "recruitment_conditions_disclosed": False,
            "assessment_evidence_exists": False,
            "termination_reason": "试用期表现不合格",
            "written_termination_notice": False,
            "monthly_salary": 10000,
            "termination_type": "可能违法解除",
        },
        "evidence": ["劳动合同", "微信聊天记录", "工资流水", "社保记录"],
        "issues": ["试用期约定是否合法", "录用条件是否明确", "解除证据是否充分", "是否构成违法解除"],
        "actions": ["固定微信解除通知", "核对合同期限和试用期", "申请劳动仲裁"],
    },
    "unlawful_termination": {
        "narrative": "我在公司工作{months}个月后被口头辞退，公司没有给出完整证据。",
        "facts": {
            "employment_duration_months": 30,
            "has_written_contract": True,
            "termination_reason": "严重违反规章制度",
            "written_termination_notice": False,
            "employer_rules_disclosed": False,
            "disciplinary_evidence_exists": False,
            "monthly_salary": 12000,
            "termination_type": "可能违法解除",
        },
        "evidence": ["劳动合同", "微信聊天记录", "工资流水", "社保记录"],
        "issues": ["解除事实", "规章制度效力", "解除理由证据", "赔偿金"],
        "actions": ["要求书面解除理由", "固定规章制度公示情况", "申请劳动仲裁"],
    },
    "unsigned_contract": {
        "narrative": "我入职后一直工作但公司没有和我签劳动合同，目前已工作{months}个月。",
        "facts": {
            "employment_start_date": "2025-01-01",
            "employment_end_date": "2025-12-31",
            "has_written_contract": False,
            "monthly_salary": 9000,
            "unsigned_months": 12,
            "employment_duration_months": 12,
        },
        "evidence": ["工资流水", "社保记录", "工作聊天记录", "入职登记表"],
        "issues": ["实际劳动关系", "未签书面合同期间", "双倍工资计算"],
        "actions": ["整理入职及工资证据", "计算可主张期间", "申请劳动仲裁"],
    },
    "wage_arrears": {
        "narrative": "公司拖欠我{months}个月工资，多次催要仍未支付。",
        "facts": {
            "arrears_months": 3,
            "arrears_amount": 30000,
            "monthly_salary": 10000,
            "employment_active": True,
            "payment_due_date": "每月10日",
        },
        "evidence": ["劳动合同", "工资流水", "银行流水", "催款记录"],
        "issues": ["工资标准", "欠付金额", "仲裁时效"],
        "actions": ["制作欠薪月份清单", "保存催款记录", "投诉或申请劳动仲裁"],
    },
    "overtime": {
        "narrative": "公司长期安排我加班，累计约{months}0小时但没有支付加班费。",
        "facts": {
            "work_schedule": "标准工时制",
            "overtime_hours": 80,
            "overtime_period": "2025-01至2025-06",
            "overtime_approved": True,
            "monthly_salary": 11000,
        },
        "evidence": ["考勤记录", "加班审批", "工作聊天记录", "工资流水"],
        "issues": ["加班事实", "用人单位安排", "计算基数"],
        "actions": ["区分工作日和休息日加班", "导出考勤和审批", "核对工资支付记录"],
    },
    "compensation": {
        "narrative": "公司提出解除劳动合同，我工作{months}个月，想核算经济补偿或赔偿金。",
        "facts": {
            "employment_duration_months": 42,
            "monthly_salary": 15000,
            "termination_type": "无过失性解除",
            "notice_months": 0,
            "local_average_salary": 12000,
        },
        "evidence": ["劳动合同", "解除通知", "工资流水", "社保记录"],
        "issues": ["解除类型", "工作年限", "月工资基数", "N/N+1/2N"],
        "actions": ["确认解除法律依据", "核对工作年限", "按适用公式计算"],
    },
}


def generate(output_dir: Path = OUTPUT_DIR, count_per_type: int = 10) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    case_number = 1
    for dispute_type, template in TEMPLATES.items():
        for variant in range(count_per_type):
            difficulty = ("simple", "medium", "complex")[variant % 3]
            facts = dict(template["facts"])
            months = float(facts.get("employment_duration_months", facts.get("arrears_months", variant + 1)))
            facts["scenario_variant"] = variant + 1
            key_facts = [key for key in facts if key != "scenario_variant"]
            if difficulty == "simple":
                visible_count, evidence_count = 3, 1
            elif difficulty == "medium":
                visible_count, evidence_count = 2, 0
            else:
                visible_count, evidence_count = 1, 0
            initial_facts = {key: facts[key] for key in key_facts[:visible_count]}
            case = {
                "schema_version": 1,
                "case_id": f"labor_{case_number:03d}",
                "dispute_type": dispute_type,
                "difficulty": difficulty,
                "initial_narrative": template["narrative"].format(months=int(months)),
                "initial_facts": initial_facts,
                "initial_evidence": template["evidence"][:evidence_count],
                "facts": facts,
                "available_evidence": template["evidence"],
                "key_facts": key_facts,
                "key_evidence": template["evidence"][:3],
                "legal_issues": template["issues"],
                "recommended_actions": template["actions"],
                "termination_condition": {
                    "minimum_fact_completeness": 0.70,
                    "minimum_evidence_completeness": 0.45,
                    "requires_law": True,
                    "requires_opponent_simulation": True,
                    "requires_judge_approval": True,
                },
                "human_reviewed": False,
                "review_status": "pending_law_student_review",
                "usage_notice": "仅用于软件测试和 RL baseline，未经法学成员复核不得作为法律真值。",
            }
            path = output_dir / f"{case['case_id']}.json"
            path.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
            paths.append(path)
            case_number += 1
    return paths


if __name__ == "__main__":
    generated = generate()
    print(f"generated={len(generated)} directory={OUTPUT_DIR}")

