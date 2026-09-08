"""Behavioral checks for the evidence-grounded consultation upgrade."""
import importlib
import json
from datetime import date

import httpx
import pytest

from backend.legal_rl.state import CaseState


def module(name):
    name = 'backend.legal_domain.consultation.' + name
    assert importlib.util.find_spec(name), f'Missing production capability: {name}'
    return importlib.import_module(name)


def case(domain='debt', **facts):
    state = CaseState(case_type=domain, user_narrative='朋友借钱到期不还')
    state.consultation.domain_ids = [domain]
    state.consultation.jurisdiction_status = 'MAINLAND_LOCATION_REPORTED'
    state.apply_facts(facts)
    return state


@pytest.mark.parametrize('message,role,expected,forbidden', [
    ('我在深圳，我是借款人，借了三万元已经还了一万元，现在被催款，希望合法减轻负担，请给我方案。', 'debtor', '已还', '将书面催款发到对方'),
    ('我在深圳，我是房东，租客拖欠房租两个月，想追回欠租，请给我方案。', 'landlord', '欠租', '向出租人书面索取'),
    ('我在深圳，我是用人单位负责人，员工申请劳动仲裁说公司欠工资，请给我方案。', 'employer', '工资', '向公司书面索取'),
])
def test_consultant_role_controls_both_sides_of_the_plan(message, role, expected, forbidden):
    from backend.workflow import LexPilotEngine
    state = LexPilotEngine().process(message)['case_state']
    report = state.final_report
    assert report['strategy_comparison']['client_role']['id'] == role
    assert expected in json.dumps(report['action_plan'], ensure_ascii=False)
    assert forbidden not in json.dumps(report, ensure_ascii=False)
    assert '对话' in report['strategy_comparison']['client_role']['basis']


def test_role_negation_is_not_treated_as_admission_and_graph_routes_employer():
    perspective = module('perspective')
    state = case('housing', parties='我不是房东，我是租客')
    assert perspective.client_perspective(state)['id'] == 'tenant'
    from backend.graph import build_graph
    graph = build_graph()
    if graph is not None:
        result = graph.compile().invoke({'case_state': CaseState(), 'user_message': '我是用人单位负责人，员工申请劳动仲裁追索工资，请给我方案。'})
        assert result['case_state'].final_report['strategy_comparison']['client_role']['id'] == 'employer'


def passage(id='civil_675', **changes):
    return dict(source_id=id, law_name='中华人民共和国民法典', article='第六百七十五条',
                text='借款人应当按照约定的期限返还借款。', domains=['debt'],
                source_url='https://www.court.gov.cn/zixun/xiangqing/233181.html',
                effective_from='2021-01-01', effective_to='', checked_on='2026-09-08',
                keywords=['借钱', '欠钱', '还款', '借款'], **changes)


def test_sqlite_retrieves_chinese_law_with_trace_and_excludes_future_versions(tmp_path):
    kb = module('knowledge').LegalKnowledgeBase(tmp_path / 'laws.sqlite3')
    kb.upsert([passage()])
    hits = kb.search(['朋友借钱不还', '借款 到期'], ['debt'], event_date='2025-05-01')
    assert hits[0]['source_id'] == 'civil_675'
    assert hits[0]['content_hash'] and hits[0]['retrieval_score'] > 0
    assert hits[0]['temporal_status'] == '版本起始条件满足，仍须核对修订和过渡规则'
    assert kb.search(['借款'], ['debt'], event_date='2018-05-01') == []
    assert kb.search(['借款'], ['criminal']) == []


def test_corpus_rejects_spoofed_sources_and_updates_index_without_duplicate(tmp_path):
    kb = module('knowledge').LegalKnowledgeBase(tmp_path / 'laws.sqlite3')
    bad = passage()
    bad['source_url'] = 'https://court.gov.cn.attacker.example/x'
    with pytest.raises(ValueError):
        kb.upsert([bad])
    kb.upsert([passage()])
    changed = passage()
    changed['text'] = '借款人应当按照约定的期限返还借款。贷款人可以催告还款。'
    kb.upsert([changed])
    hits = kb.search(['借款'], ['debt'])
    assert len(hits) == 1 and hits[0]['text'] == changed['text']


def test_expired_law_and_unknown_date_are_distinguished(tmp_path):
    kb = module('knowledge').LegalKnowledgeBase(tmp_path / 'laws.sqlite3')
    p = passage()
    p['effective_to'] = '2024-01-01'
    kb.upsert([p])
    assert kb.search(['借款'], ['debt'], event_date='2025-01-01') == []
    hit = kb.search(['借款'], ['debt'])[0]
    assert '日期未确认' in hit['temporal_status']


def test_citation_gate_rejects_fabricated_quote_id_and_missing_facts():
    verify = module('grounding').verify_claims
    state = case(location='深圳')
    sources = [passage()]
    good = dict(conclusion='先核对约定还款日。', source_ids=['civil_675'], fact_ids=['location'],
                quotes=[dict(source_id='civil_675', quote='借款人应当按照约定的期限返还借款。')], conditions=['借款关系与交付仍需核对'])
    checked = verify([good], state, sources)
    assert len(checked['accepted']) == 1
    for override in [dict(source_ids=['invented']), dict(fact_ids=['invented']),
                     dict(quotes=[dict(source_id='civil_675', quote='一定赔偿三倍')]), dict(conditions=[])]:
        rejected = verify([{**good, **override}], state, sources)
        assert not rejected['accepted'] and rejected['issues']


def test_citation_gate_does_not_treat_matching_quote_as_semantic_proof():
    verify = module('grounding').verify_claims
    result = verify([dict(conclusion='你肯定胜诉', source_ids=['civil_675'], fact_ids=['location'],
        quotes=[dict(source_id='civil_675', quote='借款人应当按照约定的期限返还借款。')], conditions=['需核对'])], case(location='深圳'), [passage()])
    assert not result['accepted']
    assert result['semantic_entailment_verified'] is False


def test_service_directory_never_invents_address_or_sends_narrative(monkeypatch):
    services = module('services')
    monkeypatch.setenv('AMAP_API_KEY', 'test-map-key')
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={'status': '1', 'pois': [
            {'id': 'P1', 'name': '深圳市南山区人民法院', 'address': '测试路1号', 'cityname': '深圳市', 'adname': '南山区', 'location': '113.9,22.5', 'tel': '0755-12345678'}]})
    state = case(location='广东省深圳市南山区', amount='PRIVATE_AMOUNT_12345')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = services.resolve_services(state, client=client)
    assert result['places'][0]['address'] == '深圳市南山区测试路1号'
    assert result['places'][0]['jurisdiction_confirmed'] is False
    assert 'PRIVATE_AMOUNT' not in ''.join(requests)
    monkeypatch.delenv('AMAP_API_KEY')
    fallback = services.resolve_services(state)
    assert fallback['places'] == [] and fallback['online_channels']
    assert '12368' in fallback['call_script']


def test_outside_mainland_receives_no_mainland_laws_or_places(monkeypatch):
    state = case(location='美国加州')
    state.consultation.jurisdiction_status = 'OUTSIDE_MAINLAND'
    assert module('services').resolve_services(state)['online_channels'] == []
    module('knowledge').retrieve_for_case(state)
    assert state.consultation.knowledge_passages == []


def test_strategy_prioritizes_deadlines_over_cheap_negotiation():
    planner = module('planning')
    state = case(constraints='希望低成本')
    state.consultation.urgent_actions = ['明天是文书载明的期限，先保全程序权利']
    result = planner.compare_routes(state)
    assert result['recommended_route'] == 'formal'
    assert result['success_probability'] is None
    assert result['model'] == 'transparent_preference_rules'
    assert all(r['reason'] and r['stop_condition'] for r in result['routes'])


def test_normal_low_cost_debt_plan_has_action_dates_and_specific_operations():
    from backend.legal_domain.consultation.intake import refresh_evidence
    from backend.legal_domain.consultation.reporting import build_consultation_report
    state = case(location='深圳', constraints='低成本', goal='追回借款')
    refresh_evidence(state)
    report = build_consultation_report(state)
    assert report.get('strategy_comparison', {}).get('recommended_route') == 'negotiation'
    assert report.get('service_guide', {}).get('online_channels')
    assert report['action_plan'][0].get('suggested_date')
    assert '法定期限' in report['action_plan'][0].get('date_note', '')
    assert any('本金' in text for step in report['action_plan'] for text in step['instructions'])
    assert report.get('quality_audit', {}).get('legal_correctness_verified') is False


def test_real_world_progress_stops_repeating_failed_negotiation():
    state = case(procedure='已经协商三次，对方拒绝还钱', constraints='低成本')
    result = module('planning').compare_routes(state)
    assert result['recommended_route'] != 'negotiation'
    from backend.legal_domain.consultation.reporting import action_plan
    steps = action_plan(state)
    assert '调解' in steps[2]['title']
    assert not any('先提出一次' in step['title'] for step in steps)


def test_export_contains_chinese_steps_sources_and_never_serializes_secret_paths(tmp_path):
    from backend.legal_domain.consultation.reporting import build_consultation_report
    from backend.legal_domain.consultation.intake import refresh_evidence
    from docx import Document
    from io import BytesIO
    import pymupdf
    state = case(location='深圳', goal='追回借款')
    refresh_evidence(state)
    build_consultation_report(state)
    exports = module('exports')
    docx = exports.export_report(state, 'docx')
    pdf = exports.export_report(state, 'pdf')
    text = '\n'.join(p.text for p in Document(BytesIO(docx)).paragraphs)
    assert '具体行动步骤' in text and '何时' in text
    with pymupdf.open(stream=pdf, filetype='pdf') as document:
        pdf_text = ''.join(p.get_text() for p in document)
        assert len(document) >= 2 and '办理' in pdf_text and '深圳' in pdf_text
        assert any(page.get_links() for page in document), 'Official source and service links must remain clickable in PDF'
    assert '.local_data' not in text and 'API_KEY' not in text
    with pytest.raises(ValueError):
        exports.export_report(state, 'exe')


def test_export_api_is_downloadable_and_missing_report_is_not_fabricated():
    from fastapi.testclient import TestClient
    from backend.api import api_app, _sessions
    client = TestClient(api_app)
    response = client.get('/cases/nonexistent-intelligence/report.pdf')
    assert response.status_code == 404
    _sessions['empty-intelligence'] = case()
    response = client.get('/cases/empty-intelligence/report.pdf')
    assert response.status_code == 409
    client.post('/chat', json={'thread_id': 'export-intelligence', 'query': '朋友借钱不还，我在深圳，给我方案'})
    response = client.get('/cases/export-intelligence/report.docx')
    assert response.status_code == 200
    assert 'attachment' in response.headers['content-disposition']
    assert response.content.startswith(b'PK')


def test_managed_snapshot_removes_retired_article_from_disk(tmp_path):
    kb = module('knowledge').LegalKnowledgeBase(tmp_path / 'laws.sqlite3')
    kb.upsert([passage()])
    kb.upsert([passage(id='replacement')], replace=True)
    assert [p['source_id'] for p in kb.search(['借款'], ['debt'])] == ['replacement']


def test_corpus_domain_tags_cover_real_profiles_and_ip_article_is_relevant():
    from backend.legal_domain.consultation.profiles import PROFILES
    knowledge = module('knowledge')
    corpus = json.loads(knowledge.CORPUS.read_text(encoding='utf-8'))['passages']
    domains = {domain for p in corpus for domain in p['domains']}
    assert domains <= set(PROFILES)
    assert set(PROFILES) - {'general'} <= domains
    ip = [p for p in corpus if 'intellectual_property' in p['domains'] and '惩罚性' in p['text']]
    assert any('知识产权' in p['text'] for p in ip)
    assert not any('污染环境' in p['text'] for p in ip)


def test_current_procedure_is_not_rejected_only_because_dispute_started_in_2018(tmp_path):
    kb = module('knowledge').LegalKnowledgeBase(tmp_path / 'laws.sqlite3')
    p = passage(id='procedure', temporal_scope='procedure')
    kb.upsert([p])
    assert kb.search(['借款'], ['debt'], event_date='2018-01-01')


def test_citation_rejects_a_fabricated_article_even_with_a_real_quote():
    result = module('grounding').verify_claims([dict(conclusion='依据第九千条可以请求还款。',
        source_ids=['civil_675'], fact_ids=['location'], conditions=['借款已交付'],
        quotes=[dict(source_id='civil_675', quote='借款人应当按照约定的期限返还借款。')])], case(location='深圳'), [passage()])
    assert not result['accepted']


def test_repair_uses_checker_feedback_and_drops_unsupported_conclusions():
    from backend.legal_domain.consultation.semantic import enrich_consultation
    state = case(location='深圳')
    state.consultation.knowledge_passages = [{**passage(), 'temporal_status': '需核对'}]
    class Provider:
        def __init__(self):
            self.count = 0
        def generate_json(self, prompt, schema, **kwargs):
            self.count += 1
            if self.count == 1:
                return {'grounded_claims': [{'conclusion': '应核对还款约定', 'source_ids': ['invented'], 'fact_ids': ['location'],
                    'quotes': [{'source_id': 'invented', 'quote': '这是没有被检索到的原文资料'}], 'conditions': ['需核对借款']}]}
            return {'analysis': '先核对借款用途与还款约定。', 'grounded_claims': []}
    enrich_consultation('给我方案', state, provider=Provider(), include_plan=True)
    assert state.consultation.generation_audit['repair_attempts'] == 1
    assert not state.consultation.grounded_claims
    assert state.consultation.analysis == '先核对借款用途与还款约定。'


def test_anchored_new_fact_is_available_to_citation_checker_in_same_turn():
    from backend.legal_domain.consultation.semantic import enrich_consultation
    state = case(location='深圳')
    state.consultation.knowledge_passages = [{**passage(), 'temporal_status': '需核对'}]
    class Provider:
        def generate_json(self, *args, **kwargs):
            return {'facts': [{'name':'details','value':'约定九月还款','quote':'约定九月还款'}],
                    'analysis':'先核对还款约定与实际交付。',
                    'grounded_claims':[{'conclusion':'需结合还款约定核对到期情况。',
                    'source_ids':['civil_675'],'fact_ids':['details'], 'conditions':['需要核实借款交付'],
                    'quotes':[{'source_id':'civil_675','quote':'借款人应当按照约定的期限返还借款。'}]}]}
    enrich_consultation('我们约定九月还款', state, provider=Provider())
    assert state.facts['details'] == '约定九月还款'
    assert state.consultation.grounded_claims
    assert not state.consultation.generation_audit['issues']


def test_only_transfer_and_chat_does_not_request_nonexistent_iou():
    from backend.workflow import LexPilotEngine
    state = LexPilotEngine().process('我在深圳，朋友借钱不还，只有转账和聊天记录，请给我方案')['case_state']
    assert '借条' in state.unavailable_evidence
    step = state.final_report['action_plan'][1]
    assert not any('保存借条原件' in line for line in step['instructions'])
