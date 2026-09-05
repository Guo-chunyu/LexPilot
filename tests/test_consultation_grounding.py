import json

import httpx

from backend.ai.provider import AIProviderError
from backend.legal_domain.consultation.research import is_official_url, research_case
from backend.legal_domain.consultation.semantic import enrich_consultation
from backend.workflow import LexPilotEngine


class DraftProvider:
    def __init__(self, value):
        self.value = value
        self.prompt = ''

    def generate_json(self, prompt, schema, **kwargs):
        self.prompt = prompt
        return self.value


def test_rejects_unanchored_model_facts_and_fabricated_statutes():
    state = LexPilotEngine().process('朋友借钱不还')['case_state']
    provider = DraftProvider({'facts': [{'name': 'amount', 'value': '100000元', 'quote': '朋友欠我100000元'}], 'analysis': '根据第九千九百条，你保证胜诉。'})
    enrich_consultation('只有转账记录', state, provider=provider)
    assert 'amount' not in state.facts
    assert not state.consultation.analysis


def test_model_fact_must_be_contained_in_its_own_quote():
    state = LexPilotEngine().process('朋友欠钱')['case_state']
    provider = DraftProvider({'facts': [{'name': 'amount', 'value': '30000元', 'quote': '对方说我在北京'}]})
    enrich_consultation('对方说我在北京，争议是30000元', state, provider=provider)
    assert 'amount' not in state.facts


def test_remote_failure_keeps_deterministic_plan_available():
    class BrokenProvider:
        def generate_json(self, *args, **kwargs):
            raise AIProviderError('unavailable')
    state = LexPilotEngine().process('房东扣押金')['case_state']
    enrich_consultation('先给我方案', state, provider=BrokenProvider())
    assert '暂不可用' in state.consultation.semantic_status
    result = LexPilotEngine().process('先给我方案', state)
    assert result['case_state'].final_report['action_plan']


def test_law_search_filters_spoofed_hosts_and_never_sends_private_narrative(monkeypatch):
    state = LexPilotEngine().process('朋友欠我100000元，我在深圳')['case_state']
    state.consultation.research_key = ''
    monkeypatch.setenv('SERPER_API_KEY', 'synthetic-test-key')
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'organic': [
            {'title': '官方', 'link': 'https://www.court.gov.cn/zixun/xiangqing/233181.html', 'snippet': '检索摘要'},
            {'title': '伪造', 'link': 'https://court.gov.cn.attacker.example/x'},
            {'title': '账号伪装', 'link': 'https://court.gov.cn@evil.example/x'},
        ]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        research_case(state, client=client)
    assert len(payloads) == 1
    assert '100000' not in payloads[0]['q'] and '深圳' not in payloads[0]['q']
    sources = [s for s in state.consultation.research_sources if s.source_id.startswith('official_')]
    assert len(sources) == 1
    assert '待核验' in sources[0].status
    assert not is_official_url('https://court.gov.cn.attacker.example/')
    assert not is_official_url('http://127.0.0.1/')


def test_debt_plan_explains_a_relevant_primary_rule_with_version_caveat():
    state = LexPilotEngine().process('我在深圳，朋友2025年5月借了我50000元，到期不还，给我方案')['case_state']
    rules = state.final_report.get('legal_basis', [])
    assert any(r['article'] == '第六百七十五条' for r in rules)
    assert all(r.get('source_url', '').startswith('https://') for r in rules)
    assert all(r.get('applicability') for r in rules)
    assert state.final_report['generation_status'] == 'PROVISIONAL'


def test_does_not_apply_post_2021_civil_code_to_2018_event():
    state = LexPilotEngine().process('我在深圳，朋友2018年5月借了我50000元，到期不还，给我方案')['case_state']
    assert not any(r.get('law_name') == '中华人民共和国民法典' for r in state.final_report.get('legal_basis', []))


def test_explicit_labor_plan_is_available_with_incomplete_materials():
    engine = LexPilotEngine()
    state = engine.process('公司拖欠工资')['case_state']
    result = engine.process('先给我具体方案', state)
    assert result['case_state'].final_report['action_plan']
    assert not result['case_state'].done


def test_remote_context_excludes_document_text_even_after_fact_extraction():
    state = LexPilotEngine().process('朋友欠钱')['case_state']
    state.apply_facts({'amount': 'PRIVATE_DOCUMENT_SENTINEL_73629'})
    state.add_fact_provenance('amount', source_type='uploaded_file', source_ref='借条.txt', quote='PRIVATE_DOCUMENT_SENTINEL_73629')
    provider = DraftProvider({})
    enrich_consultation('请继续整理', state, provider=provider)
    assert 'PRIVATE_DOCUMENT_SENTINEL_73629' not in provider.prompt


def test_model_rephrasing_same_turn_is_not_a_fact_conflict():
    message = '我在深圳，朋友借了我50000元'
    state = LexPilotEngine().process(message)['case_state']
    provider = DraftProvider({'facts': [
        {'name': 'location', 'value': '我在深圳', 'quote': '我在深圳'},
        {'name': 'amount', 'value': '50000元', 'quote': '朋友借了我50000元'},
    ]})
    enrich_consultation(message, state, provider=provider)
    assert state.facts['location'] == '深圳'
    assert not state.consultation.conflicts
