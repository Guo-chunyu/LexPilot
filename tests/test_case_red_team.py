"""End-to-end red-team cases that exercise the public consultation paths."""

from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

import backend.api as api_module
from backend.workflow import LexPilotEngine
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
