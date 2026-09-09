"""Regression tests for cross-turn decision change receipts."""

from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

import backend.api as api_module
from backend.legal_domain.consultation.reporting import report_markdown
from backend.workflow import LexPilotEngine
from evaluation.consultation_red_team import generate_anonymous_uploads
from tests.test_streamlit_app import APP_PATH


def test_multiturn_report_explains_route_change_and_stable_rerun():
    engine = LexPilotEngine()
    first = engine.process(
        '我在深圳，朋友向我借款4万元，有转账记录，我想追回，请给我方案。'
    )
    baseline = first['case_state'].final_report['decision_delta']
    first_route = first['case_state'].final_report['strategy_comparison']['recommended_route']
    assert baseline['status'] == 'baseline'
    assert baseline['changes'] == []

    second = engine.process(
        '我已经催款三次，对方都拒绝还钱，请更新方案。', first['case_state']
    )
    delta = second['case_state'].final_report['decision_delta']
    change_types = {item['change_type'] for item in delta['changes']}
    assert delta['status'] == 'changed'
    assert {'fact_added', 'route_changed'} <= change_types
    assert second['case_state'].final_report['strategy_comparison']['recommended_route'] != first_route
    assert all(item['reason'] and item['impact'] for item in delta['changes'])
    assert delta['outcome_probability'] is None
    assert '本轮方案变更回执' in report_markdown(second['case_state'])

    third = engine.process('请按当前信息重新生成方案。', second['case_state'])
    stable = third['case_state'].final_report['decision_delta']
    assert stable['status'] == 'no_material_change'
    assert stable['changes'] == []
    assert stable['unchanged']


def test_api_upload_receipt_distinguishes_claimed_from_uploaded(tmp_path, monkeypatch):
    thread_id = 'decision_delta_upload'
    client = TestClient(api_module.api_app)
    monkeypatch.setattr(api_module, '_upload_root', lambda: tmp_path)
    upload = generate_anonymous_uploads()[0]
    try:
        first = client.post('/chat', json={
            'thread_id': thread_id,
            'query': '朋友向我借款4万元，我有转账记录，请给我方案。',
        })
        second = client.post(
            f'/cases/{thread_id}/evidence',
            data={'query': '这是匿名合成材料，请更新方案。'},
            files=[('files', (upload.name, upload.data, upload.media_type))],
        )
    finally:
        api_module._sessions.pop(thread_id, None)

    assert first.status_code == second.status_code == 200
    delta = second.json()['final_report']['decision_delta']
    evidence_changes = [
        item for item in delta['changes']
        if item['change_type'] == 'evidence_status_changed'
    ]
    assert any(item['label'] == '转账记录' for item in evidence_changes)
    transfer = next(item for item in evidence_changes if item['label'] == '转账记录')
    assert transfer['before'] == '用户称有，尚未上传'
    assert transfer['after'].startswith('已上传')
    assert '核对' in transfer['impact']


def test_decision_change_receipt_is_visible_in_streamlit():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value(
        '我在深圳，朋友向我借款4万元，有转账记录，我想追回，请给我方案。'
    ).run(timeout=20)
    at.chat_input[0].set_value(
        '我已经催款三次，对方都拒绝还钱，请更新方案。'
    ).run(timeout=20)

    assert at.session_state['case_state'].final_report['decision_delta']['status'] == 'changed'
    assert any('本轮方案变更回执' in item.value for item in at.markdown)
    assert not at.exception
