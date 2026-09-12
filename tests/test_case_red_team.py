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
    generate_round_eight_variants,
    generate_round_nine_variants,
    generate_round_ten_variants,
    generate_round_eleven_variants,
    generate_round_twelve_variants,
    generate_round_thirteen_variants,
    generate_round_fourteen_variants,
    generate_round_fifteen_variants,
    generate_round_sixteen_variants,
    generate_round_seventeen_variants,
    generate_round_eighteen_variants,
    generate_round_nineteen_variants,
    generate_round_twenty_variants,
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
LABOR_INDIRECT_ARBITRATION_FILING = '我是员工，公司拖欠工资；我已经向劳动人事争议仲裁委员会提交申请并收到受理通知，请给我下一步方案。'
IP_PLATFORM_COMPLAINT_REFUSED = '摄影作品被网店盗用，我已经向平台投诉两次，平台明确拒绝处理，请给我后续方案。'
DEBT_GIFT_DEFENSE_START = '朋友欠我4万元，没有借条，有转账和完整微信，已经催款三次且对方拒绝，请给我方案。'
DEBT_GIFT_DEFENSE_FOLLOWUP = '补充一下，对方刚刚回复说这笔钱是赠与，不承认借款，我应该重点准备什么？'
DEBT_FIRST_TURN_OPENING = '没有借条不等于可以直接下结论。先把每笔转账的时间、金额、收款人'
CONSUMER_TRANSFER_START = '健身房停业，会员卡余额3000元，商家不退款，请先给我方案。'
CONSUMER_TRANSFER_FOLLOWUP = '商家刚回复说只能把会员卡转给别人使用，不能退款，我应该怎么办？'
REALISTIC_CONSUMER_START = '我在健身房办了 3000 元的会员卡，上周健身房突然停业了，商家不退钱。'
REALISTIC_CONSUMER_LOCATION = '上海市'
REALISTIC_CONSUMER_DATE = '2026.8.11'
CONSUMER_FIRST_TURN_OPENING = '先确认是门店停业、迁址，还是经营主体已经异常'
CONSUMER_IDENTITY_START = (
    '我在上海市的健身房办了3000元会员卡，2026.8.11停业，'
    '商家拒绝退款，我想拿回剩余费用，请给我方案。'
)
CONSUMER_IDENTITY_QUESTION = (
    '我是学生，暂时还不知道它具体是啥身份，没有可以确定对方主体的材料，'
    '他应该姓张。我应该怎么查询真正的经营主体？'
)
CONSUMER_MULTI_FACT_QUESTION = (
    '事情发生在上海市，停业日期是2026.8.11，我想拿回剩余的3000元。'
    '我是学生，对方经营主体暂时不清楚。我应该先投诉还是先起诉？'
)
EXPECTED_CONSUMER_PARTIES = (
    '本人：学生；对方经营主体：暂不清楚（暂无确认主体的材料）；'
    '对方联系人：可能姓张'
)
DEBT_DETAILED_PLAN_START = (
    '朋友欠我4万元，没有借条，但我有银行转账记录和完整微信聊天。'
    '约定今年6月30日前还款，我已经催过三次，对方明确拒绝还款。'
    '不要再建议我继续联系或调解，我只接受书面方式处理。请先给我方案。'
)
DEBT_DETAILED_PLAN_DEFENSE = (
    '对方刚刚回复说这4万元是赠与，不承认是借款。'
    '我现在最先准备什么？请只回答当前最重要的一步，不要重复前面的完整方案。'
)
DEBT_DETAILED_PLAN_EVIDENCE = (
    '我找到了他之前说“月底先还你一万元，剩下的下个月还”的聊天，'
    '但没有写“借款”两个字。这份聊天有什么用？只回答这个新问题。'
)
DEBT_DETAILED_PLAN_REQUEST = (
    '请按现有事实和材料给我一份详细的实施方案，写清具体步骤、证据、'
    '办理渠道和不顺利时怎么办。'
)
LABOR_DATE_INTAKE_START = (
    '公司拖欠我3个月工资，共18000元。我没有劳动合同，但有工资流水、'
    '工作群聊天和考勤截图。公司已经明确拒绝支付，请先给我方案。'
)
LABOR_DATE_INTAKE_CONTINUE = '接下来还需要我补充什么？'
LABOR_DATE_CORRECTION_AND_DURATION = (
    '对不起我前面说错了，是2025年8月11日。然后中间大概有5个月。'
)
CUSTOMER_SERVICE_START = '我购买的网课无法继续使用，剩余费用2800元，要求退款，请先给我方案。'
CUSTOMER_SERVICE_FOLLOWUP = '客服刚回复说只能补发代金券，不能退还剩余费用，我该怎么回应？'
UNMARKED_MERCHANT_START = '我预付了摄影套餐，但门店一直无法安排服务，要求退款，请先给我方案。'
UNMARKED_MERCHANT_FOLLOWUP = '商家表示只能延期半年使用，不接受退款，我应该怎么办？'
PRONOUN_MERCHANT_START = '商家取消了我预订的服务，但没有退款，请先给我方案。'
PRONOUN_MERCHANT_FOLLOWUP = '他们回复说只能换成店内余额，不能原路退款，我该怎么回应？'
ACTORLESS_CORPORATE_START = '我是公司股东，已经要求查阅账簿但被拒绝，请先给我方案。'
ACTORLESS_CORPORATE_FOLLOWUP = '收到回复说只能看年度报表，不能查会计账簿，我应该怎么办？'
NEXT_STEP_ONLY_START = '健身房停止营业，预付余额没有退，请先给我方案。'
NEXT_STEP_ONLY_FOLLOWUP = '那我现在最先做哪一步？请只说当前一步。'
MEDICAL_EVIDENCE_START = '手术后出现持续不适，我正在整理诊疗材料，请先给我方案。'
MEDICAL_EVIDENCE_FOLLOWUP = '我补充找到了手术同意书和护理记录，请更新材料清单。'
REMOTE_CONSTRAINT_START = '我是租客，退租后押金没有退，请先给我方案。'
REMOTE_CONSTRAINT_FOLLOWUP = '我还要补充：我人在外地，不能去现场办理，请据此更新方案。'
CRIMINAL_INVESTIGATOR_START = '家人被刑事拘留，我收到了拘留通知书，请给我方案。'
CRIMINAL_INVESTIGATOR_FOLLOWUP = '办案人员刚刚回复说不能告知案件情况，也不提供文书，我应该怎么办？'
TRAFFIC_UNOBTAINABLE_START = '发生交通事故，我受伤还在治疗，请先给我方案。'
TRAFFIC_UNOBTAINABLE_FOLLOWUP = '交警说事故认定书要等调查结束，我这边拿不到，请更新方案。'
DEBT_PRINCIPAL_DENIAL_START = '朋友向我借款4万元，有转账记录和微信聊天，还没还，请先给我方案。'
DEBT_PRINCIPAL_DENIAL_FOLLOWUP = '对方回复说只借了2万元，剩下的是利息，我应该怎么办？'
LABOR_COUNTERPARTY_START = '我是员工，公司拖欠工资6万元，没有劳动合同，只有工资流水和工作微信，请给我方案。'
LABOR_COUNTERPARTY_FOLLOWUP = '公司回复说只欠2万元，其余已经结清，我应该怎么办？'
IP_COMPLAINT_START = '我的摄影作品被网店盗用，我已经向平台投诉，请给我方案。'
IP_COMPLAINT_DISMISSED_FOLLOWUP = '平台表示投诉不成立，已经驳回了，我应该怎么办？'


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


def _assert_indirect_arbitration_filing_persists(state) -> None:
    assert state.case_type == 'labor_dispute'
    assert '提交申请' in state.facts.get('procedure', '')


def test_indirect_arbitration_filing_persists_in_engine():
    result = LexPilotEngine().process(LABOR_INDIRECT_ARBITRATION_FILING)
    _assert_indirect_arbitration_filing_persists(result['case_state'])


def test_indirect_arbitration_filing_persists_in_api():
    thread_id = 'red_team_indirect_arbitration_filing'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': LABOR_INDIRECT_ARBITRATION_FILING,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_indirect_arbitration_filing_persists(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_indirect_arbitration_filing_persists_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(LABOR_INDIRECT_ARBITRATION_FILING).run(timeout=20)
    _assert_indirect_arbitration_filing_persists(at.session_state['case_state'])


def _assert_accepted_arbitration_uses_formal_route(state) -> None:
    _assert_indirect_arbitration_filing_persists(state)
    assert state.final_report['strategy_comparison']['recommended_route'] == 'formal'
    assert any(
        '正式程序' in step['title']
        for step in state.final_report['action_plan']
    )


def test_accepted_arbitration_uses_formal_route_in_engine():
    result = LexPilotEngine().process(LABOR_INDIRECT_ARBITRATION_FILING)
    _assert_accepted_arbitration_uses_formal_route(result['case_state'])


def test_accepted_arbitration_uses_formal_route_in_api():
    thread_id = 'red_team_accepted_arbitration_route'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': LABOR_INDIRECT_ARBITRATION_FILING,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_accepted_arbitration_uses_formal_route(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_accepted_arbitration_uses_formal_route_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(LABOR_INDIRECT_ARBITRATION_FILING).run(timeout=20)
    _assert_accepted_arbitration_uses_formal_route(at.session_state['case_state'])


def _assert_platform_complaint_refusal_advances(state) -> None:
    assert state.case_type == 'intellectual_property'
    assert '投诉两次' in state.facts.get('procedure', '')
    assert '拒绝处理' in state.facts['procedure']
    assert state.final_report['strategy_comparison']['recommended_route'] == 'mediation'


def test_platform_complaint_refusal_advances_engine():
    result = LexPilotEngine().process(IP_PLATFORM_COMPLAINT_REFUSED)
    _assert_platform_complaint_refusal_advances(result['case_state'])


def test_platform_complaint_refusal_advances_api():
    thread_id = 'red_team_ip_platform_refusal'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': IP_PLATFORM_COMPLAINT_REFUSED,
        })
    finally:
        api_module._sessions.pop(thread_id, None)
    _assert_platform_complaint_refusal_advances(
        api_module.CaseState.from_value(response.json()['case_state'])
    )


def test_platform_complaint_refusal_advances_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(IP_PLATFORM_COMPLAINT_REFUSED).run(timeout=20)
    _assert_platform_complaint_refusal_advances(at.session_state['case_state'])


def _assert_debt_followup_answers_current_question(state, reply: str, exported: str = '') -> None:
    assert '对方刚刚回复说这笔钱是赠与' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '赠与抗辩' in reply
    assert '借款合意' in reply
    assert DEBT_FIRST_TURN_OPENING not in reply
    assert state.consultation.reply_granularity == 'single_step'
    assert state.final_report['decision_delta']['status'] == 'changed'
    if exported:
        assert '对方刚刚回复说这笔钱是赠与' in exported


def test_debt_followup_answers_current_question_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_GIFT_DEFENSE_START)
    second = engine.process(DEBT_GIFT_DEFENSE_FOLLOWUP, first['case_state'])
    _assert_debt_followup_answers_current_question(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_debt_followup_answers_current_question_in_api_and_export():
    thread_id = 'red_team_debt_gift_defense_followup'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': DEBT_GIFT_DEFENSE_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': DEBT_GIFT_DEFENSE_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_debt_followup_answers_current_question(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_debt_followup_answers_current_question_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_GIFT_DEFENSE_START).run(timeout=20)
    at.chat_input[0].set_value(DEBT_GIFT_DEFENSE_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_debt_followup_answers_current_question(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_counterparty_update_is_grounded(state, reply: str, exported: str = '') -> None:
    assert state.case_type == 'consumer'
    assert '只能把会员卡转给别人使用' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '转给别人使用' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只能把会员卡转给别人使用' in exported


def test_counterparty_update_is_grounded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(CONSUMER_TRANSFER_START)
    second = engine.process(CONSUMER_TRANSFER_FOLLOWUP, first['case_state'])
    _assert_counterparty_update_is_grounded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_counterparty_update_is_grounded_in_api_and_export():
    thread_id = 'red_team_consumer_counterparty_update'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': CONSUMER_TRANSFER_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': CONSUMER_TRANSFER_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_counterparty_update_is_grounded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_counterparty_update_is_grounded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(CONSUMER_TRANSFER_START).run(timeout=20)
    at.chat_input[0].set_value(CONSUMER_TRANSFER_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_counterparty_update_is_grounded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_realistic_consumer_conversation(
    state,
    counterparty_reply: str,
    date_reply: str,
) -> None:
    assert state.case_type == 'consumer'
    assert '只能把会员卡转给别人使用' in state.facts.get('details', '')
    assert state.facts.get('location') == REALISTIC_CONSUMER_LOCATION
    assert state.consultation.reply_mode_history[1] == 'follow_up'
    assert '转给别人使用' in counterparty_reply
    assert CONSUMER_FIRST_TURN_OPENING not in counterparty_reply
    assert state.facts.get('event_time') == REALISTIC_CONSUMER_DATE
    assert state.pending_fact_ids != ['event_time']
    assert state.consultation.reply_mode == 'acknowledgement'
    assert REALISTIC_CONSUMER_DATE in date_reply
    assert state.consultation.reply_granularity == 'acknowledge_only'
    assert '关键事情是什么时候发生的' not in date_reply


def test_realistic_consumer_conversation_without_prior_plan_in_engine():
    engine = LexPilotEngine()
    first = engine.process(REALISTIC_CONSUMER_START)
    second = engine.process(CONSUMER_TRANSFER_FOLLOWUP, first['case_state'])
    third = engine.process(REALISTIC_CONSUMER_LOCATION, second['case_state'])
    fourth = engine.process(REALISTIC_CONSUMER_DATE, third['case_state'])
    _assert_realistic_consumer_conversation(
        fourth['case_state'], second['reply'], fourth['reply']
    )


def test_realistic_consumer_conversation_without_prior_plan_in_api():
    thread_id = 'red_team_realistic_consumer_without_prior_plan'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': REALISTIC_CONSUMER_START})
        second = client.post('/chat', json={'thread_id': thread_id, 'query': CONSUMER_TRANSFER_FOLLOWUP})
        client.post('/chat', json={'thread_id': thread_id, 'query': REALISTIC_CONSUMER_LOCATION})
        fourth = client.post('/chat', json={'thread_id': thread_id, 'query': REALISTIC_CONSUMER_DATE})
    finally:
        api_module._sessions.pop(thread_id, None)
    assert second.status_code == fourth.status_code == 200
    _assert_realistic_consumer_conversation(
        api_module.CaseState.from_value(fourth.json()['case_state']),
        second.json()['reply'],
        fourth.json()['reply'],
    )


def test_realistic_consumer_conversation_without_prior_plan_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(REALISTIC_CONSUMER_START).run(timeout=20)
    at.chat_input[0].set_value(CONSUMER_TRANSFER_FOLLOWUP).run(timeout=20)
    counterparty_reply = at.session_state['messages'][-1]['content']
    at.chat_input[0].set_value(REALISTIC_CONSUMER_LOCATION).run(timeout=20)
    at.chat_input[0].set_value(REALISTIC_CONSUMER_DATE).run(timeout=20)
    _assert_realistic_consumer_conversation(
        at.session_state['case_state'],
        counterparty_reply,
        at.session_state['messages'][-1]['content'],
    )
    assert not at.exception


def _assert_identity_question_is_answered(state, reply: str, exported: str = '') -> None:
    assert state.facts.get('parties') == EXPECTED_CONSUMER_PARTIES
    assert '怎么查询' not in state.facts['parties']
    assert state.consultation.reply_mode == 'follow_up'
    assert '国家企业信用信息公示系统' in reply
    assert '支付记录' in reply
    if exported:
        assert EXPECTED_CONSUMER_PARTIES in exported
        assert '我应该怎么查询真正的经营主体' not in exported


def test_compound_party_answer_and_identity_question_in_engine():
    engine = LexPilotEngine()
    first = engine.process(CONSUMER_IDENTITY_START)
    second = engine.process(CONSUMER_IDENTITY_QUESTION, first['case_state'])
    _assert_identity_question_is_answered(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_compound_party_answer_and_identity_question_in_api_and_export():
    thread_id = 'red_team_compound_party_identity_question'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': CONSUMER_IDENTITY_START})
        second = client.post('/chat', json={'thread_id': thread_id, 'query': CONSUMER_IDENTITY_QUESTION})
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert second.status_code == exported.status_code == 200
    _assert_identity_question_is_answered(
        api_module.CaseState.from_value(second.json()['case_state']),
        second.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_compound_party_answer_and_identity_question_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(CONSUMER_IDENTITY_START).run(timeout=20)
    at.chat_input[0].set_value(CONSUMER_IDENTITY_QUESTION).run(timeout=20)
    _assert_identity_question_is_answered(
        at.session_state['case_state'],
        at.session_state['messages'][-1]['content'],
        report_markdown(at.session_state['case_state']),
    )
    assert not at.exception


def test_one_message_updates_multiple_slots_and_answers_new_question():
    engine = LexPilotEngine()
    first = engine.process(REALISTIC_CONSUMER_START)
    second = engine.process(CONSUMER_MULTI_FACT_QUESTION, first['case_state'])
    state = second['case_state']
    assert state.facts.get('location') == '上海市'
    assert state.facts.get('event_time') == '2026.8.11'
    assert '拿回剩余的3000元' in state.facts.get('goal', '')
    assert state.facts.get('parties') == '本人：学生；对方经营主体：暂不清楚'
    assert state.consultation.reply_mode == 'follow_up'
    assert '先投诉' in second['reply']
    assert '起诉' in second['reply']


def _assert_explicit_detailed_plan_is_rendered(state, reply: str) -> None:
    assert '朋友欠我4万元' in state.facts.get('amount', '')
    assert '月底先还你一万元' in state.facts.get('details', '')
    assert '**按现有事实，详细实施方案**' in reply
    assert '**办理渠道**' in reply
    assert '**证据与材料**' in reply
    assert '**具体操作**' in reply
    assert '**不顺利时**' in reply
    assert '人民法院在线服务' in reply
    assert state.consultation.reply_granularity == 'detailed_plan'


def _run_debt_detailed_plan_conversation(engine: LexPilotEngine):
    result = engine.process(DEBT_DETAILED_PLAN_START)
    for message in (DEBT_DETAILED_PLAN_DEFENSE, DEBT_DETAILED_PLAN_EVIDENCE):
        result = engine.process(message, result['case_state'])
    return engine.process(DEBT_DETAILED_PLAN_REQUEST, result['case_state'])


def test_explicit_detailed_plan_after_followups_in_engine():
    result = _run_debt_detailed_plan_conversation(LexPilotEngine())
    _assert_explicit_detailed_plan_is_rendered(result['case_state'], result['reply'])


def test_explicit_detailed_plan_after_followups_in_api():
    thread_id = 'red_team_explicit_detailed_plan_after_followups'
    client = TestClient(api_module.api_app)
    try:
        for message in (
            DEBT_DETAILED_PLAN_START,
            DEBT_DETAILED_PLAN_DEFENSE,
            DEBT_DETAILED_PLAN_EVIDENCE,
        ):
            client.post('/chat', json={'thread_id': thread_id, 'query': message})
        response = client.post(
            '/chat', json={'thread_id': thread_id, 'query': DEBT_DETAILED_PLAN_REQUEST}
        )
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == 200
    _assert_explicit_detailed_plan_is_rendered(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
    )


def test_explicit_detailed_plan_after_followups_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    for message in (
        DEBT_DETAILED_PLAN_START,
        DEBT_DETAILED_PLAN_DEFENSE,
        DEBT_DETAILED_PLAN_EVIDENCE,
        DEBT_DETAILED_PLAN_REQUEST,
    ):
        at.chat_input[0].set_value(message).run(timeout=20)
    _assert_explicit_detailed_plan_is_rendered(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )
    assert not at.exception


def _assert_labor_start_date_was_consumed(state, reply: str, expected: str) -> None:
    assert state.facts.get('employment_start_date') == expected
    assert 'employment_start_date' not in state.pending_fact_ids
    assert '你实际是哪一天入职的' not in reply


@pytest.mark.parametrize('answer', ['2026.8.11', '2026/8/11', '2026年8月11日'])
def test_labor_pending_start_date_accepts_common_formats(answer: str):
    engine = LexPilotEngine()
    first = engine.process(LABOR_DATE_INTAKE_START)
    question = engine.process(LABOR_DATE_INTAKE_CONTINUE, first['case_state'])
    assert question['case_state'].pending_fact_ids == ['employment_start_date']
    result = engine.process(answer, question['case_state'])
    _assert_labor_start_date_was_consumed(result['case_state'], result['reply'], '2026-08-11')


def test_labor_pending_start_date_accepts_common_format_in_api():
    thread_id = 'red_team_labor_pending_start_date'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={'thread_id': thread_id, 'query': LABOR_DATE_INTAKE_START})
        client.post('/chat', json={'thread_id': thread_id, 'query': LABOR_DATE_INTAKE_CONTINUE})
        response = client.post('/chat', json={'thread_id': thread_id, 'query': '2026.8.11'})
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == 200
    _assert_labor_start_date_was_consumed(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        '2026-08-11',
    )


def test_labor_pending_start_date_unknown_moves_to_next_question_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    for message in (LABOR_DATE_INTAKE_START, LABOR_DATE_INTAKE_CONTINUE, '不知道'):
        at.chat_input[0].set_value(message).run(timeout=20)
    state = at.session_state['case_state']
    reply = at.session_state['messages'][-1]['content']
    assert 'employment_start_date' in state.consultation.declined_slots
    assert 'employment_start_date' not in state.pending_fact_ids
    assert '你实际是哪一天入职的' not in reply
    assert not at.exception


def _assert_labor_compound_correction_was_consumed(state, reply: str) -> None:
    assert state.facts.get('employment_start_date') == '2025-08-11'
    assert state.facts.get('unsigned_months') == 5.0
    assert 'employment_start_date' not in state.pending_fact_ids
    assert 'unsigned_months' not in state.pending_fact_ids
    assert '你实际是哪一天入职的' not in reply
    assert '中间大约有几个月' not in reply


def _run_labor_compound_correction(engine: LexPilotEngine):
    result = engine.process(LABOR_DATE_INTAKE_START)
    result = engine.process(LABOR_DATE_INTAKE_CONTINUE, result['case_state'])
    result = engine.process('2026.8.11', result['case_state'])
    assert result['case_state'].pending_fact_ids == ['unsigned_months']
    return engine.process(LABOR_DATE_CORRECTION_AND_DURATION, result['case_state'])


def test_labor_compound_date_correction_and_duration_in_engine():
    result = _run_labor_compound_correction(LexPilotEngine())
    _assert_labor_compound_correction_was_consumed(result['case_state'], result['reply'])


def test_labor_compound_date_correction_and_duration_in_api():
    thread_id = 'red_team_labor_compound_date_correction'
    client = TestClient(api_module.api_app)
    try:
        for message in (
            LABOR_DATE_INTAKE_START,
            LABOR_DATE_INTAKE_CONTINUE,
            '2026.8.11',
            LABOR_DATE_CORRECTION_AND_DURATION,
        ):
            response = client.post('/chat', json={'thread_id': thread_id, 'query': message})
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == 200
    _assert_labor_compound_correction_was_consumed(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
    )


def test_labor_compound_date_correction_and_duration_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    for message in (
        LABOR_DATE_INTAKE_START,
        LABOR_DATE_INTAKE_CONTINUE,
        '2026.8.11',
        LABOR_DATE_CORRECTION_AND_DURATION,
    ):
        at = at.chat_input[0].set_value(message).run(timeout=20)
    _assert_labor_compound_correction_was_consumed(
        at.session_state['case_state'], at.session_state['messages'][-1]['content']
    )
    assert not at.exception


def _assert_counterparty_alias_update_is_grounded(state, reply: str, exported: str = '') -> None:
    assert state.case_type == 'consumer'
    assert '2800元' in state.facts.get('amount', '')
    assert '只能补发代金券' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '只能补发代金券' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只能补发代金券' in exported


def test_counterparty_alias_update_is_grounded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(CUSTOMER_SERVICE_START)
    second = engine.process(CUSTOMER_SERVICE_FOLLOWUP, first['case_state'])
    _assert_counterparty_alias_update_is_grounded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_counterparty_alias_update_is_grounded_in_api_and_export():
    thread_id = 'red_team_consumer_counterparty_alias'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': CUSTOMER_SERVICE_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': CUSTOMER_SERVICE_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_counterparty_alias_update_is_grounded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_counterparty_alias_update_is_grounded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(CUSTOMER_SERVICE_START).run(timeout=20)
    at.chat_input[0].set_value(CUSTOMER_SERVICE_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_counterparty_alias_update_is_grounded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_unmarked_counterparty_update_is_grounded(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'consumer'
    assert '只能延期半年使用' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '只能延期半年使用' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只能延期半年使用' in exported


def test_unmarked_counterparty_update_is_grounded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(UNMARKED_MERCHANT_START)
    second = engine.process(UNMARKED_MERCHANT_FOLLOWUP, first['case_state'])
    _assert_unmarked_counterparty_update_is_grounded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_unmarked_counterparty_update_is_grounded_in_api_and_export():
    thread_id = 'red_team_unmarked_counterparty_update'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': UNMARKED_MERCHANT_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': UNMARKED_MERCHANT_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_unmarked_counterparty_update_is_grounded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_unmarked_counterparty_update_is_grounded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(UNMARKED_MERCHANT_START).run(timeout=20)
    at.chat_input[0].set_value(UNMARKED_MERCHANT_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_unmarked_counterparty_update_is_grounded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_pronoun_counterparty_update_is_grounded(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'consumer'
    assert '只能换成店内余额' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '只能换成店内余额' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只能换成店内余额' in exported


def test_pronoun_counterparty_update_is_grounded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(PRONOUN_MERCHANT_START)
    second = engine.process(PRONOUN_MERCHANT_FOLLOWUP, first['case_state'])
    _assert_pronoun_counterparty_update_is_grounded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_pronoun_counterparty_update_is_grounded_in_api_and_export():
    thread_id = 'red_team_pronoun_counterparty_update'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': PRONOUN_MERCHANT_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': PRONOUN_MERCHANT_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_pronoun_counterparty_update_is_grounded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_pronoun_counterparty_update_is_grounded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(PRONOUN_MERCHANT_START).run(timeout=20)
    at.chat_input[0].set_value(PRONOUN_MERCHANT_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_pronoun_counterparty_update_is_grounded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_actorless_reply_update_is_grounded(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'corporate'
    assert '只能看年度报表' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '只能看年度报表' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只能看年度报表' in exported


def test_actorless_reply_update_is_grounded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(ACTORLESS_CORPORATE_START)
    second = engine.process(ACTORLESS_CORPORATE_FOLLOWUP, first['case_state'])
    _assert_actorless_reply_update_is_grounded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_actorless_reply_update_is_grounded_in_api_and_export():
    thread_id = 'red_team_actorless_reply_update'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': ACTORLESS_CORPORATE_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': ACTORLESS_CORPORATE_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_actorless_reply_update_is_grounded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_actorless_reply_update_is_grounded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(ACTORLESS_CORPORATE_START).run(timeout=20)
    at.chat_input[0].set_value(ACTORLESS_CORPORATE_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_actorless_reply_update_is_grounded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_next_step_only_reply_is_scoped(state, reply: str) -> None:
    assert state.consultation.reply_mode == 'follow_up'
    assert state.consultation.reply_granularity == 'single_step'


def test_next_step_only_followup_is_scoped_in_api_and_export():
    thread_id = 'red_team_next_step_only'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': NEXT_STEP_ONLY_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': NEXT_STEP_ONLY_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_next_step_only_reply_is_scoped(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
    )
    assert '## 具体行动步骤' in exported.content.decode('utf-8')


def test_next_step_only_followup_is_scoped_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(NEXT_STEP_ONLY_START).run(timeout=20)
    at.chat_input[0].set_value(NEXT_STEP_ONLY_FOLLOWUP).run(timeout=20)
    _assert_next_step_only_reply_is_scoped(
        at.session_state['case_state'],
        at.session_state['messages'][-1]['content'],
    )
    assert at.get('download_button')
    assert not at.exception


def _assert_new_medical_evidence_is_mapped(
    state, reply: str, exported: str = ''
) -> None:
    evidence = {item.name: item for item in state.evidence}
    assert '完整病历' in evidence
    task = next(
        item for item in state.consultation.evidence_tasks
        if item.name == '完整病历'
    )
    assert task.status == '用户称有，尚未上传'
    assert state.consultation.reply_mode == 'follow_up'
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '完整病历' in exported
        assert '用户称有，尚未上传' in exported


def test_new_medical_evidence_is_mapped_in_engine():
    engine = LexPilotEngine()
    first = engine.process(MEDICAL_EVIDENCE_START)
    second = engine.process(MEDICAL_EVIDENCE_FOLLOWUP, first['case_state'])
    _assert_new_medical_evidence_is_mapped(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_new_medical_evidence_is_mapped_in_api_and_export():
    thread_id = 'red_team_new_medical_evidence'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': MEDICAL_EVIDENCE_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': MEDICAL_EVIDENCE_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_new_medical_evidence_is_mapped(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_new_medical_evidence_is_mapped_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(MEDICAL_EVIDENCE_START).run(timeout=20)
    at.chat_input[0].set_value(MEDICAL_EVIDENCE_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_new_medical_evidence_is_mapped(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_remote_constraint_is_persisted(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'housing'
    assert '不能去现场办理' in state.facts.get('constraints', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '不能去现场办理' in exported


def test_remote_constraint_is_persisted_in_engine():
    engine = LexPilotEngine()
    first = engine.process(REMOTE_CONSTRAINT_START)
    second = engine.process(REMOTE_CONSTRAINT_FOLLOWUP, first['case_state'])
    _assert_remote_constraint_is_persisted(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_remote_constraint_is_persisted_in_api_and_export():
    thread_id = 'red_team_remote_constraint'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': REMOTE_CONSTRAINT_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': REMOTE_CONSTRAINT_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_remote_constraint_is_persisted(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_remote_constraint_is_persisted_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(REMOTE_CONSTRAINT_START).run(timeout=20)
    at.chat_input[0].set_value(REMOTE_CONSTRAINT_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_remote_constraint_is_persisted(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_authority_alias_update_is_grounded(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'criminal'
    assert '不能告知案件情况' in state.facts.get('details', '')
    assert '**先处理紧急事项**' in reply
    assert state.consultation.reply_mode == 'follow_up'
    assert '不能告知案件情况' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '不能告知案件情况' in exported


def test_authority_alias_update_is_grounded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(CRIMINAL_INVESTIGATOR_START)
    second = engine.process(CRIMINAL_INVESTIGATOR_FOLLOWUP, first['case_state'])
    _assert_authority_alias_update_is_grounded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_authority_alias_update_is_grounded_in_api_and_export():
    thread_id = 'red_team_authority_alias_update'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': CRIMINAL_INVESTIGATOR_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': CRIMINAL_INVESTIGATOR_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_authority_alias_update_is_grounded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_authority_alias_update_is_grounded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(CRIMINAL_INVESTIGATOR_START).run(timeout=20)
    at.chat_input[0].set_value(CRIMINAL_INVESTIGATOR_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_authority_alias_update_is_grounded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_unobtainable_material_is_not_an_upload_action(
    state, reply: str, exported: str = ''
) -> None:
    material = '事故认定及现场记录'
    assert state.case_type == 'traffic'
    assert material in state.unavailable_evidence
    assert material not in {item.name for item in state.evidence}
    task = next(item for item in state.consultation.evidence_tasks if item.name == material)
    assert task.status == '暂无法提供'
    assert all(material not in step['materials'] for step in state.final_report['action_plan'])
    assert state.consultation.reply_mode == 'follow_up'
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert material in exported
        assert '暂无法提供' in exported


def test_unobtainable_material_is_not_an_upload_action_in_engine():
    engine = LexPilotEngine()
    first = engine.process(TRAFFIC_UNOBTAINABLE_START)
    second = engine.process(TRAFFIC_UNOBTAINABLE_FOLLOWUP, first['case_state'])
    _assert_unobtainable_material_is_not_an_upload_action(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_unobtainable_material_is_not_an_upload_action_in_api_and_export():
    thread_id = 'red_team_unobtainable_material'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': TRAFFIC_UNOBTAINABLE_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': TRAFFIC_UNOBTAINABLE_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_unobtainable_material_is_not_an_upload_action(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_unobtainable_material_is_not_an_upload_action_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(TRAFFIC_UNOBTAINABLE_START).run(timeout=20)
    at.chat_input[0].set_value(TRAFFIC_UNOBTAINABLE_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_unobtainable_material_is_not_an_upload_action(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_counterparty_denial_does_not_replace_principal(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'debt'
    assert '4万元' in state.facts.get('amount', '')
    assert '只借了2万元' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '只借了2万元' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只借了2万元' in exported
        assert '4万元' in exported


def test_counterparty_denial_does_not_replace_principal_in_engine():
    engine = LexPilotEngine()
    first = engine.process(DEBT_PRINCIPAL_DENIAL_START)
    second = engine.process(DEBT_PRINCIPAL_DENIAL_FOLLOWUP, first['case_state'])
    _assert_counterparty_denial_does_not_replace_principal(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_counterparty_denial_does_not_replace_principal_in_api_and_export():
    thread_id = 'red_team_debt_principal_denial'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': DEBT_PRINCIPAL_DENIAL_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': DEBT_PRINCIPAL_DENIAL_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_counterparty_denial_does_not_replace_principal(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_counterparty_denial_does_not_replace_principal_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(DEBT_PRINCIPAL_DENIAL_START).run(timeout=20)
    at.chat_input[0].set_value(DEBT_PRINCIPAL_DENIAL_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_counterparty_denial_does_not_replace_principal(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_labor_later_update_answers_current_turn(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'labor_dispute'
    assert '只欠2万元' in state.facts.get('details', '')
    assert state.consultation.reply_mode == 'follow_up'
    assert '只欠2万元' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '只欠2万元' in exported


def test_labor_later_update_answers_current_turn_in_engine():
    engine = LexPilotEngine()
    first = engine.process(LABOR_COUNTERPARTY_START)
    second = engine.process(LABOR_COUNTERPARTY_FOLLOWUP, first['case_state'])
    _assert_labor_later_update_answers_current_turn(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_labor_later_update_answers_current_turn_in_api_and_export():
    thread_id = 'red_team_labor_later_update'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': LABOR_COUNTERPARTY_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': LABOR_COUNTERPARTY_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_labor_later_update_answers_current_turn(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_labor_later_update_answers_current_turn_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(LABOR_COUNTERPARTY_START).run(timeout=20)
    at.chat_input[0].set_value(LABOR_COUNTERPARTY_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_labor_later_update_answers_current_turn(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


def _assert_procedure_outcome_is_recorded(
    state, reply: str, exported: str = ''
) -> None:
    assert state.case_type == 'intellectual_property'
    assert '不成立' in state.facts.get('procedure', '')
    assert state.final_report['strategy_comparison']['recommended_route'] == 'mediation'
    assert state.consultation.reply_mode == 'follow_up'
    assert '不成立' in reply
    assert state.consultation.reply_granularity == 'single_step'
    if exported:
        assert '不成立' in exported


def test_procedure_outcome_is_recorded_in_engine():
    engine = LexPilotEngine()
    first = engine.process(IP_COMPLAINT_START)
    second = engine.process(IP_COMPLAINT_DISMISSED_FOLLOWUP, first['case_state'])
    _assert_procedure_outcome_is_recorded(
        second['case_state'], second['reply'], report_markdown(second['case_state'])
    )


def test_procedure_outcome_is_recorded_in_api_and_export():
    thread_id = 'red_team_procedure_outcome'
    client = TestClient(api_module.api_app)
    try:
        client.post('/chat', json={
            'thread_id': thread_id, 'query': IP_COMPLAINT_START,
        })
        response = client.post('/chat', json={
            'thread_id': thread_id, 'query': IP_COMPLAINT_DISMISSED_FOLLOWUP,
        })
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    _assert_procedure_outcome_is_recorded(
        api_module.CaseState.from_value(response.json()['case_state']),
        response.json()['reply'],
        exported.content.decode('utf-8'),
    )


def test_procedure_outcome_is_recorded_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(IP_COMPLAINT_START).run(timeout=20)
    at.chat_input[0].set_value(IP_COMPLAINT_DISMISSED_FOLLOWUP).run(timeout=20)
    state = at.session_state['case_state']
    _assert_procedure_outcome_is_recorded(
        state,
        at.session_state['messages'][-1]['content'],
        report_markdown(state),
    )
    assert not at.exception


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
        'generate_round_eight_variants': generate_round_eight_variants,
        'generate_round_nine_variants': generate_round_nine_variants,
        'generate_round_ten_variants': generate_round_ten_variants,
        'generate_round_eleven_variants': generate_round_eleven_variants,
        'generate_round_twelve_variants': generate_round_twelve_variants,
        'generate_round_thirteen_variants': generate_round_thirteen_variants,
        'generate_round_fourteen_variants': generate_round_fourteen_variants,
        'generate_round_fifteen_variants': generate_round_fifteen_variants,
        'generate_round_sixteen_variants': generate_round_sixteen_variants,
        'generate_round_seventeen_variants': generate_round_seventeen_variants,
        'generate_round_eighteen_variants': generate_round_eighteen_variants,
        'generate_round_nineteen_variants': generate_round_nineteen_variants,
        'generate_round_twenty_variants': generate_round_twenty_variants,
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
            # The procedural record accumulates by design: a later procedural
            # outcome advances the case rather than contradicting the earlier
            # statement, and each case asserts its own expected outcome via
            # `expected_facts`. Every other slot must survive the turn unchanged.
            assert all(
                state.facts.get(key) == value
                for key, value in prior_facts.items() if key != 'procedure'
            )
            if 'procedure' in prior_facts and state.facts.get('procedure') != prior_facts['procedure']:
                assert any(
                    fragment in str(state.facts.get('procedure', ''))
                    for _, fragment in case.expected_facts
                ), 'a changing procedural record must be covered by expected_facts'
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


CONSUMER_TRANSFER_REPLY = '商家说可以把会员卡转给别人使用，但不能退款。'
CONSUMER_ROUTE_QUESTION = '我想知道先投诉好还是直接起诉好？'


def _consumer_engine_turns(amount_text: str) -> list[str]:
    engine = LexPilotEngine()
    state = None
    replies = []
    for message in [
        f'我在一家健身房办了卡，一共付了{amount_text}，现在健身房关门了，我想退款。',
        CONSUMER_TRANSFER_REPLY,
        CONSUMER_ROUTE_QUESTION,
    ]:
        result = engine.process(message, state)
        state = result['case_state']
        replies.append(result['reply'])
    return replies


def test_consumer_transfer_reply_uses_the_case_amount_not_a_hardcoded_one():
    replies = _consumer_engine_turns('1800元')
    assert '1800元' in replies[1]
    assert '3000元' not in replies[1]


def test_consumer_route_advice_uses_the_case_amount_not_a_hardcoded_one():
    replies = _consumer_engine_turns('1800元')
    assert '3000元' not in replies[2]


def test_consumer_transfer_reply_omits_amount_when_none_is_recorded():
    """A case without any amount must not silently invent one."""
    engine = LexPilotEngine()
    first = engine.process('我在一家理发店办了预付卡，现在店关门了，我想退款。')
    second = engine.process(CONSUMER_TRANSFER_REPLY, first['case_state'])
    assert '3000元' not in second['reply']
    assert not re.search(r'按目前\d+元', second['reply'])


def test_consumer_subject_lookup_uses_the_surname_the_user_actually_gave():
    engine = LexPilotEngine()
    first = engine.process('我在一家健身房办了卡，付了1800元，现在店关门了，我想退款。')
    second = engine.process(
        '我只知道联系人可能姓李，怎么查询对方的经营主体？',
        first['case_state'],
    )
    assert '李' in second['reply']
    assert '可能姓张' not in second['reply']
