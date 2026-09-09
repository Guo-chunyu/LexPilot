"""Regression tests for reversible self-help and human-handoff guidance."""

from backend.legal_domain.consultation.intake import refresh_evidence
from backend.legal_domain.consultation.reporting import (
    build_consultation_report,
    report_markdown,
)
from backend.legal_rl.state import CaseState


def make_case(domain='debt', **facts):
    state = CaseState(case_type=domain, user_narrative='需要法律事项处理方案')
    state.consultation.domain_ids = [domain]
    state.consultation.jurisdiction_status = 'MAINLAND_LOCATION_REPORTED'
    state.apply_facts(facts)
    refresh_evidence(state)
    build_consultation_report(state)
    return state


def test_ordinary_early_case_keeps_reversible_self_help_path():
    state = make_case('debt', location='深圳', goal='追回借款')
    bridge = state.final_report['support_bridge']

    assert bridge['model'] == 'deterministic_support_bridge_v1'
    assert bridge['mode'] == 'self_help'
    assert bridge['human_review_recommended'] is False
    assert bridge['outcome_probability'] is None
    assert bridge['contact_script']
    assert bridge['first_steps']
    assert state.final_report['quality_audit']['support_bridge_present'] is True
    assert state.final_report['quality_audit']['support_bridge_traceable'] is True
    assert state.final_report['quality_audit']['support_bridge_probability_free'] is True
    assert '自助—人工接力通行证' in report_markdown(state)


def test_urgent_signal_requires_immediate_handoff_without_waiting_for_materials():
    state = CaseState(case_type='family', user_narrative='有人身安全风险')
    state.consultation.domain_ids = ['family']
    state.consultation.jurisdiction_status = 'MAINLAND_LOCATION_REPORTED'
    state.consultation.urgent_actions = ['先联系警方并处理人身安全风险。']
    refresh_evidence(state)
    build_consultation_report(state)
    bridge = state.final_report['support_bridge']

    assert bridge['mode'] == 'immediate_handoff'
    assert bridge['human_review_recommended'] is True
    assert bridge['reasons'][0]['signal_id'] == 'urgent_action'
    assert '不要为补齐应用内信息延误行动' in bridge['explanation']
    assert bridge['outcome_probability'] is None


def test_active_procedure_and_explicit_support_need_are_explainable():
    state = make_case(
        'debt',
        location='深圳',
        procedure='已经起诉并收到法院传票',
        constraints='我看不懂线上操作，需要人帮忙',
    )
    bridge = state.final_report['support_bridge']
    signal_ids = {item['signal_id'] for item in bridge['reasons']}

    assert bridge['mode'] == 'priority_review'
    assert {'active_procedure', 'stated_support_need'} <= signal_ids
    assert bridge['human_review_recommended'] is True
    assert all(item['signal_id'] and item['explanation'] for item in bridge['reasons'])
    state.consultation.urgent_actions = ['先到安全地点并联系当地警方。']
    refresh_evidence(state)
    build_consultation_report(state)
    bridge = state.final_report['support_bridge']

    assert bridge['mode'] == 'immediate_handoff'
    assert bridge['human_review_recommended'] is True
    assert bridge['reasons'][0]['signal_id'] == 'urgent_action'
    assert '不要为补齐应用内信息延误行动' in bridge['explanation']


def test_active_procedure_and_conflict_are_traceable_review_reasons():
    state = CaseState(case_type='debt', user_narrative='借款争议')
    state.consultation.domain_ids = ['debt']
    state.consultation.jurisdiction_status = 'MAINLAND_LOCATION_REPORTED'
    state.apply_facts({'procedure': '已经起诉并收到法院传票'})
    state.consultation.conflicts = [{
        'fact': '金额',
        'previous': '三万元',
        'current': '两万元',
        'source_ref': '对话第2轮',
        'status': '存在不同陈述，请核对',
    }]
    refresh_evidence(state)
    build_consultation_report(state)
    bridge = state.final_report['support_bridge']
    signals = {item['signal_id'] for item in bridge['reasons']}

    assert bridge['mode'] == 'priority_review'
    assert {'active_procedure', 'fact_conflict'} <= signals
    assert state.final_report['quality_audit']['support_bridge_traceable'] is True
    assert state.final_report['quality_audit']['support_bridge_probability_free'] is True


def test_explicit_access_need_selects_guided_self_help():
    state = make_case('debt', constraints='我不会操作网上立案，需要人帮忙')
    bridge = state.final_report['support_bridge']

    assert bridge['mode'] == 'guided_self_help'


def test_chat_records_support_need_before_handoff():
    from backend.workflow import LexPilotEngine
    result = LexPilotEngine().process(
        '朋友借钱不还，已经起诉并收到法院传票。我看不懂线上操作，需要人帮忙，请给我具体方案。'
    )
    state = result['case_state']
    bridge = state.final_report['support_bridge']
    assert '看不懂' in state.facts['constraints']
    assert bridge['mode'] == 'priority_review'
    assert any(item['signal_id'] == 'stated_support_need' for item in bridge['reasons'])
    assert bridge['privacy_checklist']
