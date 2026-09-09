"""End-to-end red-team cases that exercise the public consultation paths."""

import json
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

import backend.api as api_module
from backend.workflow import LexPilotEngine
from backend.legal_domain.consultation.reporting import report_markdown
from backend.legal_domain.labor.evidence_gap import detect_evidence_gaps
from backend.legal_rl.state import EvidenceStatus
from evaluation.consultation_red_team import (
    audit_red_team_result,
    generate_anonymous_uploads,
    generate_automatic_variants,
    generate_round_two_variants,
    generate_round_three_variants,
    generate_round_four_variants,
    generate_round_five_variants,
    generate_round_six_variants,
    generate_round_seven_variants,
    generate_red_team_cases,
)
from tests.test_streamlit_app import APP_PATH


DEBT_CORRECTION = (
    '2025-03-12朋友借款5万元，约定一个月后归还，已还1万元剩4万元，'
    '没有借条，有转账和微信，催款三次且对方拒绝，请给我具体方案。'
)
REPEATED_DEBT_QUESTION = '当时约定什么时候还？对方有没有说这笔钱是赠与、货款，或者已经还过一部分？'
DEBT_LITIGATION_FOLLOWUP = (
    '我目前有银行转账记录和完整微信聊天，可以证明转款、借款用途、约定一个月后还款，'
    '以及对方承认还欠4万元并拒绝还款。没有借条，也没有其他材料。此前已经催款三次，'
    '不想再重复催款或协商，请按现有材料更新为起诉准备方案。'
)
ABSOLUTE_SUGGESTED_DATE = re.compile(r'建议\s*20\d{2}-\d{2}-\d{2}\s*开始')
ISO_DATE = re.compile(r'20\d{2}-\d{2}-\d{2}')
UNKNOWN_REPAYMENT_TERM = '期限仍无法确定'
FAMILY_DOUBLE_NEGATIVE_SAFETY = '准备离婚，不是没有人身安全风险，请给我紧急方案。'
LABOR_EMPLOYER_AMOUNT_START = '我是公司负责人，员工申请仲裁称欠薪5万元。'
LABOR_EMPLOYER_AMOUNT_CORRECTION = '更正一下，员工请求金额实际是4万元，请按单位立场给我答辩方案。'
CONSUMER_EXHAUSTED_START = '健身房关门不退款，我只有付款截图，没有其他材料，请先给我方案。'
CONSUMER_EVIDENCE_CORRECTION = '更正一下，我后来找到了订单和完整聊天，不是只有截图，请更新方案。'
TRAFFIC_WITH_MEDICAL_MATERIALS = '交通事故仍在治疗，保险公司没有拒赔，只是要求补充病历和票据，请给我方案。'
CORPORATE_INSPECTION_REFUSAL = '我是公司股东，已经书面要求查账两次，公司明确拒绝，请给我后续方案。'
HOUSING_FORMAL_ROLE_CORRECTION = '本人并非出租人，而是承租人；退租后的押金被对方扣留，请按承租人立场给我方案。'


def _assert_corporate_inspection_refusal_advances_route(state) -> None:
    assert state.case_type == 'corporate'
    assert '查账两次' in state.facts.get('procedure', '')
    assert state.final_report['strategy_comparison']['recommended_route'] == 'mediation'
    assert not any('先提出一次' in step['title'] for step in state.final_report['action_plan'])


def test_corporate_inspection_refusal_advances_engine_route():
    result = LexPilotEngine().process(CORPORATE_INSPECTION_REFUSAL)
    _assert_corporate_inspection_refusal_advances_route(result['case_state'])


def test_corporate_inspection_refusal_advances_api_route():
    thread_id = 'red_team_corporate_inspection_refusal'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': CORPORATE_INSPECTION_REFUSAL,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_corporate_inspection_refusal_advances_route(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_corporate_inspection_refusal_advances_streamlit_route():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(CORPORATE_INSPECTION_REFUSAL).run(timeout=20)
    _assert_corporate_inspection_refusal_advances_route(at.session_state['case_state'])


def _assert_formal_housing_role_correction(state) -> None:
    assert state.case_type == 'housing'
    perspective = state.final_report['strategy_comparison']['client_role']
    assert perspective['id'] == 'tenant'
    assert '承租人' in state.facts.get('parties', '')


def test_formal_housing_role_correction_reaches_engine():
    result = LexPilotEngine().process(HOUSING_FORMAL_ROLE_CORRECTION)
    _assert_formal_housing_role_correction(result['case_state'])


def test_formal_housing_role_correction_reaches_api():
    thread_id = 'red_team_formal_housing_role'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': HOUSING_FORMAL_ROLE_CORRECTION,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_formal_housing_role_correction(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_formal_housing_role_correction_reaches_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(HOUSING_FORMAL_ROLE_CORRECTION).run(timeout=20)
    _assert_formal_housing_role_correction(at.session_state['case_state'])


def _assert_debt_correction_is_respected(state, reply: str) -> None:
    assert state.case_type == 'debt'
    assert re.search(r'约定一个月后(?:归还|还款)', state.facts['details'])
    assert '已还1万元剩4万元' in state.facts['details']
    assert '催款三次且对方拒绝' in state.facts['procedure']
    assert state.final_report['strategy_comparison']['recommended_route'] != 'negotiation'
    assert REPEATED_DEBT_QUESTION not in reply


def _assert_double_negative_safety_is_urgent(state, reply: str) -> None:
    assert state.case_type == 'family'
    assert state.consultation.urgent_actions
    assert '**先处理紧急事项**' in reply


def test_double_negative_safety_reaches_engine_urgent_path():
    result = LexPilotEngine().process(FAMILY_DOUBLE_NEGATIVE_SAFETY)
    _assert_double_negative_safety_is_urgent(result['case_state'], result['reply'])


def test_double_negative_safety_reaches_api_urgent_path():
    thread_id = 'red_team_double_negative_safety'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': FAMILY_DOUBLE_NEGATIVE_SAFETY,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_double_negative_safety_is_urgent(
        api_module.CaseState.from_value(response.json()['case_state']), response.json()['reply']
    )


def test_double_negative_safety_reaches_streamlit_urgent_path():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(FAMILY_DOUBLE_NEGATIVE_SAFETY).run(timeout=20)
    _assert_double_negative_safety_is_urgent(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )


def _assert_employer_wage_case_stays_in_labor_domain(state) -> None:
    assert state.case_type == 'labor_dispute'
    assert state.final_report['strategy_comparison']['client_role']['id'] == 'employer'
    assert '4万元' in state.facts['amount']


def test_employer_wage_arbitration_routes_through_labor_engine():
    engine = LexPilotEngine()
    first = engine.process(LABOR_EMPLOYER_AMOUNT_START)
    second = engine.process(LABOR_EMPLOYER_AMOUNT_CORRECTION, first['case_state'])
    _assert_employer_wage_case_stays_in_labor_domain(second['case_state'])


def test_employer_wage_arbitration_routes_through_labor_api():
    thread_id = 'red_team_employer_wage_domain'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': LABOR_EMPLOYER_AMOUNT_START})
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': LABOR_EMPLOYER_AMOUNT_CORRECTION,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_employer_wage_case_stays_in_labor_domain(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_employer_wage_arbitration_routes_through_labor_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(LABOR_EMPLOYER_AMOUNT_START).run(timeout=20)
    at.chat_input[0].set_value(LABOR_EMPLOYER_AMOUNT_CORRECTION).run(timeout=20)
    _assert_employer_wage_case_stays_in_labor_domain(at.session_state['case_state'])


def _assert_new_consumer_evidence_reopens_collection(state, reply: str) -> None:
    assert state.case_type == 'consumer'
    assert state.evidence_collection_exhausted is False
    statuses = {item.name: item.status for item in state.consultation.evidence_tasks}
    assert statuses['订单与消费合同'] == '用户称有，尚未上传'
    assert statuses['售后沟通记录'] == '用户称有，尚未上传'
    assert '现有材料就按这些整理' not in reply


def test_new_consumer_evidence_reopens_collection_in_engine():
    engine = LexPilotEngine()
    first = engine.process(CONSUMER_EXHAUSTED_START)
    second = engine.process(CONSUMER_EVIDENCE_CORRECTION, first['case_state'])
    _assert_new_consumer_evidence_reopens_collection(second['case_state'], second['reply'])


def test_new_consumer_evidence_reopens_collection_in_api():
    thread_id = 'red_team_consumer_evidence_reopened'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': CONSUMER_EXHAUSTED_START})
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': CONSUMER_EVIDENCE_CORRECTION,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_new_consumer_evidence_reopens_collection(
        api_module.CaseState.from_value(response.json()['case_state']), response.json()['reply']
    )


def test_new_consumer_evidence_reopens_collection_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(CONSUMER_EXHAUSTED_START).run(timeout=20)
    at.chat_input[0].set_value(CONSUMER_EVIDENCE_CORRECTION).run(timeout=20)
    _assert_new_consumer_evidence_reopens_collection(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )


def _assert_traffic_event_outweighs_medical_material_terms(state) -> None:
    assert state.case_type == 'traffic'
    assert state.final_report['domain'] == '交通事故'
    assert '事故认定及保险信息' in state.final_report['analysis']
    assert '责任比例、治疗关联和具体损失' in state.final_report['analysis']


def test_traffic_event_with_medical_materials_routes_in_engine():
    result = LexPilotEngine().process(TRAFFIC_WITH_MEDICAL_MATERIALS)
    _assert_traffic_event_outweighs_medical_material_terms(result['case_state'])


def test_traffic_event_with_medical_materials_routes_in_api():
    thread_id = 'red_team_traffic_medical_materials'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': TRAFFIC_WITH_MEDICAL_MATERIALS,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_traffic_event_outweighs_medical_material_terms(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_traffic_event_with_medical_materials_routes_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(TRAFFIC_WITH_MEDICAL_MATERIALS).run(timeout=20)
    _assert_traffic_event_outweighs_medical_material_terms(at.session_state['case_state'])


def _assert_no_invented_action_dates(state, reply: str) -> None:
    public = reply + '\n' + report_markdown(state)
    assert not ABSOLUTE_SUGGESTED_DATE.search(public)
    assert all(not ISO_DATE.fullmatch(str(step.get('suggested_date', '')))
               for step in state.final_report['action_plan'])


def _assert_known_repayment_term_is_not_described_as_unknown(state, reply: str) -> None:
    assert re.search(r'约定一个月后(?:归还|还款)', state.facts['details'])
    assert UNKNOWN_REPAYMENT_TERM not in reply
    assert UNKNOWN_REPAYMENT_TERM not in report_markdown(state)


def test_known_repayment_term_reaches_rule_summary_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_CORRECTION)
    second = engine.process(DEBT_LITIGATION_FOLLOWUP, first['case_state'])
    _assert_known_repayment_term_is_not_described_as_unknown(second['case_state'], second['reply'])


def test_known_repayment_term_reaches_rule_summary_in_api():
    thread_id = 'red_team_debt_known_repayment_term'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_CORRECTION})
        response = client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_LITIGATION_FOLLOWUP})
    finally:
        api_module._sessions.pop(thread_id, None)
    state = api_module.CaseState.from_value(response.json()['case_state'])
    _assert_known_repayment_term_is_not_described_as_unknown(state, response.json()['reply'])


def test_known_repayment_term_reaches_rule_summary_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)
    at.chat_input[0].set_value(DEBT_LITIGATION_FOLLOWUP).run(timeout=20)
    _assert_known_repayment_term_is_not_described_as_unknown(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )


def _assert_litigation_preference_controls_route(state) -> None:
    assert '不想再重复催款或协商' in state.facts.get('constraints', '')
    assert state.final_report['strategy_comparison']['recommended_route'] == 'formal'
    assert not any('调解' in step['title'] for step in state.final_report['action_plan'])


def test_debt_litigation_preference_controls_engine_route():
    engine = LexPilotEngine()
    first = engine.process(DEBT_CORRECTION)
    second = engine.process(DEBT_LITIGATION_FOLLOWUP, first['case_state'])
    _assert_litigation_preference_controls_route(second['case_state'])


def test_debt_litigation_preference_controls_api_route():
    thread_id = 'red_team_debt_litigation_preference'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_CORRECTION})
        response = client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_LITIGATION_FOLLOWUP})
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_litigation_preference_controls_route(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_debt_litigation_preference_controls_streamlit_route():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)
    at.chat_input[0].set_value(DEBT_LITIGATION_FOLLOWUP).run(timeout=20)
    _assert_litigation_preference_controls_route(at.session_state['case_state'])


def _assert_debt_followup_explains_decision_changes(state, reply: str) -> None:
    delta = state.final_report['decision_delta']
    assert delta['status'] == 'changed'
    assert '**本轮方案变化**' in reply
    assert '关键事实与材料说明' in reply
    assert '可以证明转款、借款用途、约定一个月后还款' in reply
    assert '办理偏好与限制' in reply
    assert '不想再重复催款或协商' in reply
    assert '建议路线：调解 → 正式程序' in reply


def test_debt_followup_explains_material_and_constraint_changes_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_CORRECTION)
    second = engine.process(DEBT_LITIGATION_FOLLOWUP, first['case_state'])
    _assert_debt_followup_explains_decision_changes(second['case_state'], second['reply'])


def test_debt_followup_explains_material_and_constraint_changes_in_api():
    thread_id = 'red_team_debt_decision_changes'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_CORRECTION})
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': DEBT_LITIGATION_FOLLOWUP,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_debt_followup_explains_decision_changes(
        api_module.CaseState.from_value(response.json()['case_state']), response.json()['reply']
    )


def test_debt_followup_explains_material_and_constraint_changes_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)
    at.chat_input[0].set_value(DEBT_LITIGATION_FOLLOWUP).run(timeout=20)
    _assert_debt_followup_explains_decision_changes(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )


def _assert_unavailable_iou_is_not_an_upload_action(state, public_text: str) -> None:
    iou = next(item for item in state.final_report['evidence_checklist'] if item['name'] == '借条')
    assert iou['status'] == '暂无法提供'
    assert all('借条' not in step['materials'] for step in state.final_report['action_plan'])
    assert '转账备注、借条和聊天' not in public_text
    assert '上传转账、借条或聊天' not in public_text
    assert '不要倒签或补造借条' in public_text


def test_unavailable_iou_is_not_an_upload_action_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_CORRECTION)
    second = engine.process(DEBT_LITIGATION_FOLLOWUP, first['case_state'])
    public = second['reply'] + '\n' + report_markdown(second['case_state'])
    _assert_unavailable_iou_is_not_an_upload_action(second['case_state'], public)


def test_unavailable_iou_is_not_an_upload_action_in_api_export():
    thread_id = 'red_team_debt_unavailable_iou'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_CORRECTION})
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': DEBT_LITIGATION_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert exported.status_code == 200
    state = api_module.CaseState.from_value(response.json()['case_state'])
    public = response.json()['reply'] + '\n' + exported.content.decode('utf-8')
    _assert_unavailable_iou_is_not_an_upload_action(state, public)


def test_unavailable_iou_is_not_an_upload_action_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)
    at.chat_input[0].set_value(DEBT_LITIGATION_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    public = at.session_state['messages'][-1]['content'] + '\n' + report_markdown(state)
    _assert_unavailable_iou_is_not_an_upload_action(state, public)


def _assert_pending_fact_acknowledgement_is_specific(state, reply: str) -> None:
    assert 'location' in state.consultation.declined_slots
    assert '“适用地区”暂时记为待核实' in reply
    assert '这项先记为待核实' not in reply


def test_unknown_pending_fact_is_acknowledged_by_name_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_CORRECTION)
    second = engine.process('不清楚', first['case_state'])
    _assert_pending_fact_acknowledgement_is_specific(second['case_state'], second['reply'])


def test_unknown_pending_fact_is_acknowledged_by_name_in_api():
    thread_id = 'red_team_specific_pending_ack'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_CORRECTION})
        response = client.post('/chat', json={'thread_id': thread_id, 'query': '不清楚'})
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_pending_fact_acknowledgement_is_specific(
        api_module.CaseState.from_value(response.json()['case_state']), response.json()['reply']
    )


def test_unknown_pending_fact_is_acknowledged_by_name_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)
    at.chat_input[0].set_value('不清楚').run(timeout=20)
    _assert_pending_fact_acknowledgement_is_specific(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )


def test_debt_followup_does_not_invent_absolute_action_dates_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_CORRECTION)
    second = engine.process(DEBT_LITIGATION_FOLLOWUP, first['case_state'])
    _assert_no_invented_action_dates(second['case_state'], second['reply'])


def test_debt_followup_does_not_invent_absolute_action_dates_in_api():
    thread_id = 'red_team_debt_no_invented_dates'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_CORRECTION})
        response = client.post('/chat', json={'thread_id': thread_id, 'query': DEBT_LITIGATION_FOLLOWUP})
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == 200
    state = api_module.CaseState.from_value(response.json()['case_state'])
    _assert_no_invented_action_dates(state, response.json()['reply'])


def test_debt_followup_does_not_invent_absolute_action_dates_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)
    at.chat_input[0].set_value(DEBT_LITIGATION_FOLLOWUP).run(timeout=20)
    _assert_no_invented_action_dates(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )
    assert not at.exception


def test_complete_debt_correction_updates_real_multiturn_engine_state():
    engine = LexPilotEngine()
    first = engine.process('朋友借钱不还，我想追回借款。')
    second = engine.process(DEBT_CORRECTION, first['case_state'])

    _assert_debt_correction_is_respected(second['case_state'], second['reply'])
    assert second['case_state'].facts['goal'] == first['case_state'].facts['goal']


def test_complete_debt_correction_survives_api_session():
    thread_id = 'red_team_complete_debt'
    client = TestClient(api_module.api_app)
    try:
        first = client.post('/chat', json={
            'thread_id': thread_id,
            'query': '朋友借钱不还，我想追回借款。',
        })
        second = client.post('/chat', json={
            'thread_id': thread_id,
            'query': DEBT_CORRECTION,
        })
    finally:
        api_module._sessions.pop(thread_id, None)

    assert first.status_code == 200
    assert second.status_code == 200
    payload = second.json()
    _assert_debt_correction_is_respected(
        api_module.CaseState.from_value(payload['case_state']), payload['reply']
    )


def test_complete_debt_correction_reaches_streamlit_report():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value('朋友借钱不还，我想追回借款。').run(timeout=20)
    at.chat_input[0].set_value(DEBT_CORRECTION).run(timeout=20)

    state = at.session_state['case_state']
    _assert_debt_correction_is_respected(
        state, at.session_state['messages'][-1]['content']
    )
    assert at.get('download_button')
    assert not at.exception


def test_red_team_generator_covers_every_supported_practice_area_and_risk_dimension():
    cases = generate_red_team_cases()
    domains = {case.expected_domain for case in cases}
    tags = {tag for case in cases for tag in case.tags}

    assert domains >= {
        'debt', 'family', 'housing', 'consumer', 'contract', 'criminal',
        'administrative', 'corporate', 'intellectual_property', 'inheritance',
        'traffic', 'medical', 'tort', 'enforcement', 'labor_dispute', 'general',
    }
    assert tags >= {
        'opposing_role', 'negation', 'role_correction', 'fact_conflict',
        'procedure_progress', 'urgent', 'deadline', 'evidence_exhausted',
        'deadline_negation', 'deadline_correction', 'urgent_negation', 'urgent_correction',
    }
    assert len({case.case_id for case in cases}) == len(cases)


def test_red_team_round_state_persists_seed_and_exact_anonymous_case_list():
    payload = json.loads(Path('evaluation/red_team_state.json').read_text(encoding='utf-8'))
    active_round = payload['rounds'][-1]
    generators = {
        'generate_automatic_variants': generate_automatic_variants,
        'generate_round_two_variants': generate_round_two_variants,
        'generate_round_three_variants': generate_round_three_variants,
        'generate_round_four_variants': generate_round_four_variants,
        'generate_round_five_variants': generate_round_five_variants,
        'generate_round_six_variants': generate_round_six_variants,
        'generate_round_seven_variants': generate_round_seven_variants,
    }
    generated = generators[active_round['generator']](active_round['seed'])

    assert payload['round_size'] == len(generated) == 5
    assert set(payload['case_pool_sources']) == {
        'human_failures', 'fixed_cases', 'automatic_variants'
    }
    assert active_round['selected_case_ids'] == [case.case_id for case in generated]
    assert active_round['anonymous_cases'] == [
        {'case_id': case.case_id, 'messages': list(case.messages)} for case in generated
    ]
    assert all(case.origin == 'auto_variant' for case in generated)
    serialized = json.dumps(active_round['anonymous_cases'], ensure_ascii=False)
    assert not __import__('re').search(r'1[3-9]\d{9}|\d{17}[0-9Xx]', serialized)


@pytest.mark.parametrize('case', generate_red_team_cases(), ids=lambda case: case.case_id)
def test_generated_red_team_case_passes_real_multiturn_engine(case):
    engine = LexPilotEngine()
    state = None
    replies = []
    prior_facts = {}
    for message in case.messages:
        result = engine.process(message, state)
        state = result['case_state']
        replies.append(result['reply'])
        if not {'fact_conflict', 'fact_correction'} & set(case.tags):
            assert all(state.facts.get(key) == value for key, value in prior_facts.items())
        prior_facts = dict(state.facts)

    assert audit_red_team_result(case, state, replies) == []
    if 'fact_conflict' in case.tags:
        assert state.consultation.conflicts
    if 'fact_correction' in case.tags:
        assert state.consultation.corrections
        assert not state.consultation.conflicts
        assert state.final_report['fact_corrections'] == state.consultation.corrections
        assert '本轮明确更正' in report_markdown(state)
    if 'evidence_exhausted' in case.tags:
        assert state.evidence_collection_exhausted is True
    if 'urgent' in case.tags:
        assert state.consultation.urgent_actions
    if 'outside_mainland' in case.tags:
        assert state.consultation.jurisdiction_status == 'OUTSIDE_MAINLAND'
        assert state.final_report['research_sources'] == []


def test_anonymous_multiformat_files_use_real_api_and_remain_unverified(tmp_path, monkeypatch):
    thread_id = 'red_team_multiformat_upload'
    uploads = generate_anonymous_uploads()
    client = TestClient(api_module.api_app)
    monkeypatch.setattr(api_module, '_upload_root', lambda: tmp_path)
    try:
        first = client.post('/chat', json={
            'thread_id': thread_id,
            'query': '朋友向我借款4万元，有转账和微信，没有借条，请给我方案。',
        })
        response = client.post(
            f'/cases/{thread_id}/evidence',
            data={'query': '这些都是匿名合成测试材料，请更新方案。'},
            files=[('files', (item.name, item.data, item.media_type)) for item in uploads],
        )
        markdown = client.get(f'/cases/{thread_id}/report.md')
        docx = client.get(f'/cases/{thread_id}/report.docx')
        pdf = client.get(f'/cases/{thread_id}/report.pdf')
    finally:
        api_module._sessions.pop(thread_id, None)

    assert first.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    records = payload['case_state']['uploaded_files']
    assert {record['extension'] for record in records} == {'.txt', '.pdf', '.docx', '.png'}
    assert 'stored_path' not in str(payload)
    tasks = {item['name']: item for item in payload['final_report']['evidence_checklist']}
    assert tasks['转账记录']['status'].startswith('已上传')
    assert tasks['催款记录']['status'].startswith('已上传')
    assert all(item['status'] != 'PROVEN' for item in tasks.values())
    assert markdown.status_code == docx.status_code == pdf.status_code == 200
    assert '证据清单' in markdown.content.decode('utf-8')
    assert docx.content.startswith(b'PK')
    assert pdf.content.startswith(b'%PDF')


def test_explicit_fact_correction_is_visible_in_streamlit_without_conflict_warning():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value('我是借款人，争议本金是5万元。').run(timeout=20)
    at.chat_input[0].set_value(
        '说错了，我不是借款人，是出借人；实际尚欠4万元，请给我方案。'
    ).run(timeout=20)

    state = at.session_state['case_state']
    assert state.consultation.corrections
    assert not state.consultation.conflicts
    assert any('本轮明确更正' in item.value for item in at.markdown)
    assert not at.exception


def test_no_other_questions_is_not_misread_as_no_more_evidence():
    engine = LexPilotEngine()
    first = engine.process('朋友向我借款4万元，有转账记录。')
    before = {item.name: item.status for item in first['case_state'].consultation.evidence_tasks}

    second = engine.process('没有其他问题，请给我方案。', first['case_state'])
    state = second['case_state']
    after = {item.name: item.status for item in state.consultation.evidence_tasks}

    assert state.evidence_collection_exhausted is False
    assert after['借条'] == before['借条'] == '尚未提供'
    assert after['转账记录'] == '用户称有，尚未上传'


def test_conflicting_uploaded_amount_does_not_silently_replace_user_fact(tmp_path, monkeypatch):
    thread_id = 'red_team_upload_fact_conflict'
    client = TestClient(api_module.api_app)
    monkeypatch.setattr(api_module, '_upload_root', lambda: tmp_path)
    try:
        first = client.post('/chat', json={
            'thread_id': thread_id,
            'query': '朋友向我借款4万元，有转账记录，请给我方案。',
        })
        second = client.post(
            f'/cases/{thread_id}/evidence',
            data={'query': '这是匿名合成材料，请更新方案。'},
            files=[('files', (
                '匿名借条.txt',
                '匿名合成借条，记载借款金额50000元，不含真实姓名。'.encode('utf-8'),
                'text/plain',
            ))],
        )
    finally:
        api_module._sessions.pop(thread_id, None)

    assert first.status_code == second.status_code == 200
    state = api_module.CaseState.from_value(second.json()['case_state'])
    assert '4万元' in state.facts['amount']
    conflict = next(item for item in state.consultation.conflicts if item['fact'] == '金额陈述')
    assert '50000元' in conflict['current']
    assert '未自动覆盖' in conflict['status']
    source = next(
        item for item in state.fact_provenance
        if item.fact_id == 'amount' and item.source_type == 'uploaded_file'
    )
    assert source.accepted is False
    extracted = state.uploaded_files[0].extracted_facts
    assert any('金额陈述' in item and '未自动覆盖' in item for item in extracted)
    assert '从正文识别' in second.json()['reply']
    assert '未自动覆盖' in second.json()['reply']
    assert '4万元' in second.json()['final_report']['case_summary']


def test_labor_evidence_distinguishes_self_report_upload_and_human_verification(tmp_path, monkeypatch):
    thread_id = 'red_team_labor_evidence_levels'
    client = TestClient(api_module.api_app)
    monkeypatch.setattr(api_module, '_upload_root', lambda: tmp_path)
    docx_fixture = next(item for item in generate_anonymous_uploads() if item.name.endswith('.docx'))
    try:
        first = client.post('/chat', json={
            'thread_id': thread_id,
            'query': '我是员工，签了劳动合同，合同期限三年，试用期六个月，我有劳动合同，公司说试用期不合格，请给我方案。',
        })
        second = client.post(
            f'/cases/{thread_id}/evidence',
            data={'query': '这是匿名合成劳动合同，请更新方案。'},
            files=[('files', ('匿名劳动合同.docx', docx_fixture.data, docx_fixture.media_type))],
        )
    finally:
        api_module._sessions.pop(thread_id, None)

    assert first.status_code == second.status_code == 200
    first_state = api_module.CaseState.from_value(first.json()['case_state'])
    self_reported = next(item for item in first_state.evidence if item.name == '劳动合同')
    assert self_reported.verification_status == 'SELF_REPORTED'
    assert next(
        item for item in first_state.evidence_gaps if item.element_id == 'valid_probation_term'
    ).status != EvidenceStatus.PROVEN

    state = api_module.CaseState.from_value(second.json()['case_state'])
    uploaded = next(item for item in state.evidence if item.name == '劳动合同')
    assert uploaded.verification_status == 'UPLOADED_UNVERIFIED'
    gap = next(item for item in state.evidence_gaps if item.element_id == 'valid_probation_term')
    assert gap.status == EvidenceStatus.PARTIAL

    state.verify_evidence('劳动合同', reviewer_ref='synthetic-human-review')
    assert state.final_report == {}
    detect_evidence_gaps(state)
    verified = next(item for item in state.evidence if item.name == '劳动合同')
    assert verified.verification_status == 'VERIFIED'
    assert next(
        item for item in state.evidence_gaps if item.element_id == 'valid_probation_term'
    ).status == EvidenceStatus.PROVEN
