"""Evidence what-if cards should explain decisions without predicting outcomes."""

import json

from backend.legal_domain.consultation.reporting import report_markdown
from backend.workflow import LexPilotEngine


def test_counterfactual_sandbox_prioritizes_evidence_user_already_has():
    state = LexPilotEngine().process(
        '我在深圳，朋友借钱不还，只有转账记录，没有借条，请给我方案。'
    )['case_state']
    sandbox = state.final_report['evidence_counterfactuals']

    assert sandbox['model'] == 'deterministic_evidence_counterfactuals_v1'
    assert sandbox['cards'][0]['name'] == '转账记录'
    assert sandbox['next_best_evidence_id'] == sandbox['cards'][0]['evidence_id']
    assert sandbox['cards'][0]['priority'] == '优先整理'
    assert state.final_report['quality_audit']['counterfactual_probability_free'] is True
    assert state.final_report['quality_audit']['counterfactual_card_count'] == len(sandbox['cards'])


def test_counterfactual_cards_cover_support_conflict_and_unavailable_without_odds():
    state = LexPilotEngine().process(
        '朋友借钱不还，只有转账记录，没有借条，请给我方案。'
    )['case_state']
    sandbox = state.final_report['evidence_counterfactuals']
    serialized = json.dumps(sandbox, ensure_ascii=False)

    assert all(card['if_supports'] and card['if_conflicts'] and card['if_unavailable']
               for card in sandbox['cards'])
    assert all(card['outcome_probability'] is None for card in sandbox['cards'])
    assert '不要删除、截断或隐藏不利内容' in serialized
    assert '不预测胜率' in sandbox['explanation']
    assert '证据反事实沙盘' in report_markdown(state)
    assert '如果材料冲突：' in report_markdown(state)


def test_labor_stage_report_also_contains_counterfactual_sandbox():
    state = LexPilotEngine().process(
        '我是员工，公司拖欠工资，我有工资流水，请给我方案。'
    )['case_state']

    assert state.case_type == 'labor_dispute'
    assert state.final_report['evidence_counterfactuals']['cards']
    assert state.final_report['evidence_counterfactuals']['model'].endswith('_v1')
