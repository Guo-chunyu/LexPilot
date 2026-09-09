"""End-to-end red-team cases that exercise the public consultation paths."""

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

import backend.api as api_module
from backend.workflow import LexPilotEngine
from backend.legal_domain.consultation.reporting import report_markdown
from evaluation.consultation_red_team import (
    audit_red_team_result,
    generate_anonymous_uploads,
    generate_red_team_cases,
)
from tests.test_streamlit_app import APP_PATH


DEBT_CORRECTION = (
    '2025-03-12朋友借款5万元，约定一个月后归还，已还1万元剩4万元，'
    '没有借条，有转账和微信，催款三次且对方拒绝，请给我具体方案。'
)
REPEATED_DEBT_QUESTION = '当时约定什么时候还？对方有没有说这笔钱是赠与、货款，或者已经还过一部分？'


def _assert_debt_correction_is_respected(state, reply: str) -> None:
    assert state.case_type == 'debt'
    assert '约定一个月后归还' in state.facts['details']
    assert '已还1万元剩4万元' in state.facts['details']
    assert '催款三次且对方拒绝' in state.facts['procedure']
    assert state.final_report['strategy_comparison']['recommended_route'] != 'negotiation'
    assert REPEATED_DEBT_QUESTION not in reply


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
    }
    assert len({case.case_id for case in cases}) == len(cases)


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
