"""Small public regression/ablation set, not a legal accuracy certification."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['LEXPILOT_ENABLE_SEMANTIC_AI'] = 'false'
from backend.legal_domain.consultation.knowledge import CORPUS, LegalKnowledgeBase
from backend.legal_domain.consultation.profiles import PROFILES, identify_domains


def run():
    cases = json.loads((ROOT / 'eval/consultation_benchmark.json').read_text(encoding='utf-8'))
    corpus = json.loads(CORPUS.read_text(encoding='utf-8'))['passages']
    details = []
    routing = []
    with TemporaryDirectory() as directory:
        kb = LegalKnowledgeBase(Path(directory) / 'laws.sqlite3')
        kb.upsert(corpus)
        for case in cases:
            profile = PROFILES[case['domain']]
            routed = identify_domains(case['query'])[0]
            routing.append({'id': case['id'], 'expected_domain': case['domain'],
                'routed_domain': routed, 'correct': routed == case['domain']})
            for mode in ('single_query_bm25', 'multi_query_rrf'):
                queries = [case['query']]
                if mode == 'multi_query_rrf':
                    queries += [' '.join(profile.keywords), profile.focus + ' ' + profile.route]
                started = perf_counter()
                hits = kb.search(queries, [case['domain']], event_date='2026-09-01', limit=5)
                ranked = [p['source_id'] for p in hits]
                relevant_ranks = [ranked.index(sid)+1 for sid in case['expected'] if sid in ranked]
                details.append({'id': case['id'], 'mode': mode, 'domain': case['domain'],
                    'hit_at_5': bool(relevant_ranks), 'recall_at_5': len(relevant_ranks)/len(case['expected']),
                    'reciprocal_rank': 1/min(relevant_ranks) if relevant_ranks else 0,
                    'latency_ms': round((perf_counter()-started)*1000, 2), 'retrieved': ranked, 'expected': case['expected']})
    aggregates = {}
    for mode in ('single_query_bm25', 'multi_query_rrf'):
        rows = [r for r in details if r['mode'] == mode]
        aggregates[mode] = {k: round(sum(float(r[k]) for r in rows)/len(rows), 4) for k in ('hit_at_5','recall_at_5','reciprocal_rank','latency_ms')}
    result = {'case_count': len(cases), 'corpus_size': len(corpus),
        'limitations': '人工编写的公开小型回归集；检索指标使用已知领域标签，路由指标才从原始问题识别。仅测路由和检索命中，不测法律判断正确率，不是盲测，也不证明优于其他系统。',
        'routing': {
            'accuracy': round(sum(item['correct'] for item in routing) / len(routing), 4),
            'errors': [item for item in routing if not item['correct']],
        },
        'metrics': aggregates, 'cases': details}
    destination = ROOT / 'evaluation' / 'consultation_results.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'cases'}, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    run()
