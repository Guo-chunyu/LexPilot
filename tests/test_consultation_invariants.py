"""Invariant tests: what must hold for every case, not just the chosen examples.

These complement the example-based red-team matrix. Each test states one
invariant and runs it over the whole reusable corpus and the enumerative
coverage probes, so a regression in a dimension nobody thought to enumerate
still fails the suite.
"""

import re

import pytest
from fastapi.testclient import TestClient

import backend.api as api_module
from backend.workflow import LexPilotEngine
from evaluation.consultation_coverage import (
    DOMAIN_OPENERS,
    audit_assertion_probe,
    audit_coverage_probe,
    generate_assertion_probes,
    generate_coverage_probes,
)
from evaluation.consultation_red_team import generate_red_team_cases


# Slots that describe the user's own assertion and must not be replaced by the
# other party's wording. `details`, `procedure` and `constraints` accumulate by
# design and are covered by their own assertions.
USER_OWNED_SLOTS = ('amount', 'parties', 'event_time', 'goal', 'location')
CORRECTION_TAGS = {'fact_correction', 'fact_conflict'}

# An oracle independent of the product code: the position where the other
# party's reported statement starts. Everything from there on is their wording.
REPORT_FRAME = re.compile(
    r'(?:对方|房东|租客|商家|平台|医院|供应商|公司|单位|家人|继承人|中介|客服|人事|'
    r'办案人员|民警|警官|交警|检察官|检察人员|执行法官|法官|书记员|窗口工作人员|窗口|'
    r'医务科|医务处|科室|承办人员|保险理赔员|店铺经营者|物业|开发商|保险人|'
    r'承办机构|经营者|代理人|他们)'
    r'(?:回复|表示|称|说|主张|否认|不承认|拒绝|要求|提出|发来)'
)


def _reported_statement_start(message: str):
    match = REPORT_FRAME.search(message)
    return match.start() if match else None


def _run(messages):
    engine = LexPilotEngine()
    state = None
    replies = []
    states = []
    for message in messages:
        result = engine.process(message, state)
        state = result['case_state']
        replies.append(result['reply'])
        states.append(dict(state.facts))
    return state, replies, states


@pytest.mark.parametrize('case', generate_red_team_cases(), ids=lambda case: case.case_id)
def test_no_user_slot_is_replaced_by_counterparty_wording(case):
    if CORRECTION_TAGS & set(case.tags):
        return
    _, _, states = _run(case.messages)
    for index in range(1, len(case.messages)):
        previous, current = states[index - 1], states[index]
        start = _reported_statement_start(case.messages[index])
        if start is None:
            continue
        for slot in USER_OWNED_SLOTS:
            if previous.get(slot) == current.get(slot):
                continue
            new_value = str(current.get(slot, ''))
            position = case.messages[index].find(new_value)
            assert position < start, (
                f'turn {index + 1} took {slot} from the other party statement: '
                f'{new_value!r}'
            )


def test_no_material_is_both_held_and_unobtainable():
    probes = generate_coverage_probes() + generate_assertion_probes()
    for probe in probes:
        state, _, _ = _run(probe.messages)
        held = {item.name for item in state.evidence}
        overlap = held & set(state.unavailable_evidence)
        assert not overlap, f'{probe.probe_id}: {sorted(overlap)}'


def test_unobtainable_materials_never_appear_as_upload_actions():
    probes = generate_coverage_probes() + generate_assertion_probes()
    for probe in probes:
        state, _, _ = _run(probe.messages)
        unavailable = set(state.unavailable_evidence)
        if not unavailable:
            continue
        for step in (state.final_report or {}).get('action_plan', []):
            listed = [name for name in step.get('materials', []) if name in unavailable]
            assert not listed, f'{probe.probe_id}: {listed} still requested as materials'


@pytest.mark.parametrize('probe', generate_coverage_probes(), ids=lambda probe: probe.probe_id)
def test_material_availability_frames_are_honoured(probe):
    state, _, _ = _run(probe.messages)
    assert audit_coverage_probe(probe, state) == []


@pytest.mark.parametrize('probe', generate_assertion_probes(), ids=lambda probe: probe.probe_id)
def test_user_figures_survive_a_counterparty_claim(probe):
    state, _, _ = _run(probe.messages)
    assert audit_assertion_probe(probe, state) == []


@pytest.mark.parametrize('domain', sorted(DOMAIN_OPENERS))
def test_delivery_paths_publish_the_same_state(domain):
    _, opener = DOMAIN_OPENERS[domain]
    engine_state, _, _ = _run((opener,))
    thread_id = f'invariant_{domain}'
    client = TestClient(api_module.api_app)
    try:
        response = client.post('/chat', json={'thread_id': thread_id, 'query': opener})
        exported = client.get(f'/cases/{thread_id}/report.md')
    finally:
        api_module._sessions.pop(thread_id, None)
    assert response.status_code == exported.status_code == 200
    api_state = api_module.CaseState.from_value(response.json()['case_state'])
    assert api_state.case_type == engine_state.case_type
    for slot in ('amount', 'parties', 'goal', 'location', 'procedure', 'constraints'):
        assert api_state.facts.get(slot) == engine_state.facts.get(slot), slot
    assert api_state.unavailable_evidence == engine_state.unavailable_evidence
    assert ([item.name for item in api_state.evidence]
            == [item.name for item in engine_state.evidence])
    assert (api_state.final_report['action_plan']
            == engine_state.final_report['action_plan'])
    exported_text = exported.content.decode('utf-8')
    for step in engine_state.final_report['action_plan']:
        assert step['title'] in exported_text, step['title']


@pytest.mark.parametrize('probe', generate_coverage_probes(), ids=lambda probe: probe.probe_id)
def test_every_recorded_fact_carries_a_trace(probe):
    state, _, _ = _run(probe.messages)
    traced = {entry.fact_id for entry in state.fact_provenance}
    for slot in state.facts:
        assert slot in traced, f'{slot} was recorded without provenance'
    for entry in state.fact_provenance:
        assert entry.quote or entry.extraction_method, 'provenance without a trace'
