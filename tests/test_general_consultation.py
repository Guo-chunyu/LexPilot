"""Acceptance cases: ordinary legal problems must not become labor disputes."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.api import api_app
from backend.graph import invoke_lexpilot
from backend.legal_domain.labor.evidence_upload import UploadPayload, ingest_evidence_files
from backend.workflow import LexPilotEngine


@pytest.mark.parametrize(("message", "domain"), [
    ("朋友借了我五万元到期不还，只有转账没有借条，怎么办？", "debt"),
    ("我要离婚，孩子一直跟我生活，房子登记在丈夫名下", "family"),
    ("房东不退押金，还说我把房间弄坏了", "housing"),
    ("健身房关门了，我的会员卡还有余额，想退款", "consumer"),
    ("对方一直没有交货，我们签了采购合同", "contract"),
    ("家人被刑事拘留，今天收到拘留通知书", "criminal"),
    ("市场监管局给我行政处罚，我想申请行政复议", "administrative"),
    ("我是公司股东，想查账但老板不让", "corporate"),
    ("有人盗用我的摄影作品，还拿去卖", "intellectual_property"),
    ("父亲去世留下遗嘱，兄弟不同意这样分遗产", "inheritance"),
    ("我被汽车撞伤了，对方保险公司不赔", "traffic"),
    ("医院手术后出现严重后遗症，怀疑医疗过错", "medical"),
    ("网上有人公开我的隐私并造谣辱骂", "tort"),
    ("已经胜诉但对方不履行判决，想申请强制执行", "enforcement"),
])
def test_routes_legal_topics_without_labor_questions(message, domain):
    result = LexPilotEngine().process(message)
    state = result["case_state"]
    assert state.case_type == domain
    assert "劳动合同" not in result["reply"]
    assert "平均月工资" not in result["reply"]
    assert state.pending_questions
    assert len(state.pending_questions) <= 2
    assert result["requires_user"]


def test_debt_intake_remembers_short_answers_and_unknowns():
    engine = LexPilotEngine()
    state = engine.process("朋友借钱不还，想要回钱")['case_state']
    assert state.pending_fact_ids == ["location"]
    state = engine.process("广东省深圳市南山区", state)['case_state']
    assert state.facts['location'] == "广东省深圳市南山区"
    assert state.pending_fact_ids != ["location"]
    previous = state.pending_fact_ids[0]
    result = engine.process("不清楚", state)
    assert previous not in result['case_state'].pending_fact_ids
    assert previous in result['case_state'].consultation.declined_slots
    assert result['case_state'].fact_provenance


def test_plan_is_available_before_all_evidence_is_collected():
    engine = LexPilotEngine()
    state = engine.process("深圳朋友欠我50000元，2025年5月转账，我想追回借款")['case_state']
    result = engine.process("先给我具体方案，证据暂时没有更多了", state)
    report = result['case_state'].final_report
    assert report.get('action_plan'), "A lack of evidence should not block practical steps"
    assert report['generation_status'] == 'PROVISIONAL'
    assert len(report['action_plan']) >= 4
    for step in report['action_plan']:
        assert all(step.get(key) for key in ('title', 'when', 'channel', 'materials', 'instructions', 'completion', 'fallback'))
    assert report['evidence_checklist']
    assert all(item.get('proves') and item.get('alternative') for item in report['evidence_checklist'])
    assert report['opponent_arguments']
    assert report['costs']
    assert report['deadlines']
    assert report['documents']
    assert '50000' in report['case_summary']
    assert '劳动人事争议仲裁委员会' not in str(report)
    assert not result['case_state'].pending_evidence_requests
    assert not result['case_state'].done, "A stage report must allow continuing the consultation"


def test_urgent_criminal_situation_prioritizes_local_help():
    result = LexPilotEngine().process("家人今天被刑事拘留，通知上写了看守所，不知道怎么办")
    assert result['case_state'].consultation.urgent_actions
    assert "刑事律师" in result['reply']
    assert result['case_state'].consultation.urgent_actions[0] in result['reply']


def test_nonmainland_case_does_not_apply_mainland_procedure():
    result = LexPilotEngine().process("我在美国加州租房，房东扣押金")
    assert result['case_state'].consultation.jurisdiction_status == 'OUTSIDE_MAINLAND'
    assert '劳动仲裁' not in result['reply']
    result = LexPilotEngine().process("给我方案", result['case_state'])
    assert '人民法院在线服务' not in str(result['case_state'].final_report.get('action_plan', []))


def test_upload_is_classified_in_its_actual_domain_and_not_treated_as_proven(tmp_path):
    engine = LexPilotEngine()
    state = engine.process("朋友借钱不还，我在深圳，想要回5万元")['case_state']
    ingest_evidence_files(state, [UploadPayload('借条.txt', '借条\n2025年5月1日向张某借款50000元，尚未偿还。'.encode())], tmp_path)
    result = engine.process("这是借条，先给我方案", state)
    state = result['case_state']
    assert state.case_type == 'debt'
    assert '借条' in state.uploaded_files[0].evidence_names
    assert 'has_written_contract' not in state.facts
    assert not state.uploaded_files[0].stored_path in str(state.public_dict())
    assert state.final_report['evidence_checklist'][0]['status'] != 'PROVEN'
    assert state.consultation.timeline


def test_langgraph_keeps_general_case_between_invocations():
    thread_id = 'general_' + uuid4().hex
    first = invoke_lexpilot("健身房关门了，会员卡的钱还能退吗", thread_id)
    second = invoke_lexpilot("上海市浦东新区", thread_id)
    assert first['case_state'].case_id == second['case_state'].case_id
    assert second['case_state'].case_type == 'consumer'
    assert second['case_state'].facts['location'] == '上海市浦东新区'


def test_api_returns_general_dossier_and_plan():
    client = TestClient(api_app)
    thread = 'consult_' + uuid4().hex
    first = client.post('/chat', json={'thread_id': thread, 'query': '房东扣押金，我要追回租房押金'})
    assert first.status_code == 200
    assert first.json()['case_state']['case_type'] == 'housing'
    response = client.post('/chat', json={'thread_id': thread, 'query': '先给我详细方案'})
    assert response.status_code == 200
    assert response.json()['final_report']['action_plan']
    assert response.json()['case_state']['consultation']['domain_ids'] == ['housing']


def test_stage_report_refreshes_after_user_correction():
    engine = LexPilotEngine()
    state = engine.process('朋友借钱不还，我在深圳，借了50000元')['case_state']
    state = engine.process('给我方案', state)['case_state']
    state = engine.process('更正一下，金额是30000元，已经还了20000元', state)['case_state']
    assert '30000' in str(state.facts['amount'])
    assert state.final_report['action_plan']
    assert state.final_report['fact_conflicts'], 'Keep the changed amount visible for reconciliation'


def test_missing_iou_uses_alternative_and_does_not_reask_stated_goal():
    state = LexPilotEngine().process('我在深圳，朋友2025年5月借了我50000元，没有借条，想低成本追回，请给我具体方案')['case_state']
    assert '追回' in state.facts['goal']
    assert '低成本' in state.facts['constraints']
    assert '借条' in state.unavailable_evidence
    evidence_step = state.final_report['action_plan'][1]
    assert not any('保存借条原件' in text for text in evidence_step['instructions'])
    assert 'goal' not in state.pending_fact_ids


def test_background_salary_does_not_turn_a_rental_dispute_into_labor():
    result = LexPilotEngine().process('房东不退租房押金，我每月工资只有3000元，希望低成本处理')
    assert result['case_state'].case_type == 'housing'


def test_administrative_detention_is_not_assumed_to_be_criminal():
    result = LexPilotEngine().process('收到行政拘留处罚决定，想提出异议')
    assert result['case_state'].case_type == 'administrative'
    assert '刑事律师' not in result['reply']


def test_upload_after_report_refreshes_the_same_plan(tmp_path):
    engine = LexPilotEngine()
    state = engine.process('朋友借钱不还，先给我方案')['case_state']
    ingest_evidence_files(state, [UploadPayload('借条.txt', '借条：2025年5月1日借款50000元。'.encode())], tmp_path)
    state = engine.process('刚刚上传了材料', state)['case_state']
    assert state.final_report['action_plan']
    assert state.final_report['evidence_checklist'][0]['source_refs'] == ['借条.txt']
