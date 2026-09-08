"""Deterministic citation/fact integrity checks; not a semantic entailment oracle."""
import re


UNSAFE = re.compile(r'保证.{0,5}(?:胜诉|取保|赔偿)|肯定胜诉|胜诉率|一定能赢|必胜|伪造证据|删除.{0,5}证据|购买.{0,5}个人信息|我是.{0,8}律师')


def normalized(text):
    return re.sub(r'\s+', '', str(text))


def verify_claims(claims: list[dict], state, passages: list[dict]) -> dict:
    sources = {p['source_id']: p for p in passages}
    accepted, issues = [], []
    for index, claim in enumerate(claims):
        errors = []
        ids, facts, quotes = claim.get('source_ids', []), claim.get('fact_ids', []), claim.get('quotes', [])
        if not ids or any(sid not in sources for sid in ids):
            errors.append('引用ID不存在或未提供')
        if not facts or any(fid not in state.facts for fid in facts):
            errors.append('事实ID不存在或未提供')
        if not claim.get('conditions') or not all(str(c).strip() for c in claim.get('conditions', [])):
            errors.append('缺少适用条件')
        supported = set()
        for quote in quotes:
            sid = quote.get('source_id')
            excerpt = normalized(quote.get('quote', ''))
            if sid not in sources or len(excerpt) < 8 or excerpt not in normalized(sources[sid]['text']):
                errors.append('引文不是所引正文的连续原文')
            else:
                supported.add(sid)
        if set(ids) != supported:
            errors.append('每个引用均须提供对应原文，不能附加无关引文')
        conclusion = str(claim.get('conclusion', ''))
        if not conclusion.strip() or UNSAFE.search(conclusion):
            errors.append('结论为空或包含不允许的结果保证或违法取证')
        if re.search(r'https?://', conclusion):
            errors.append('引用链接由系统附加，不接受生成链接')
        articles = re.findall(r'第[零一二三四五六七八九十百千0-9]+条', conclusion)
        if any(a not in [sources[sid]['article'] for sid in ids if sid in sources] for a in articles):
            errors.append('结论使用了所引法源不存在的条号')
        if errors:
            issues.append({'claim_index': index, 'reasons': list(dict.fromkeys(errors))})
        else:
            accepted.append({**claim, 'integrity_status': '事实ID与引文完整性通过',
                'legal_status': '有条件分析，语义蕴含与适用仍需复核'})
    return {'accepted': accepted, 'issues': issues, 'semantic_entailment_verified': False,
            'legal_correctness_verified': False}


def audit_report(report: dict, dossier) -> dict:
    steps = report.get('action_plan', [])
    required = ('when', 'channel', 'materials', 'instructions', 'completion', 'fallback')
    complete = sum(all(s.get(k) for k in required) for s in steps)
    return {'step_count': len(steps), 'complete_step_count': complete,
        'action_completeness': round(complete / max(len(steps), 1), 3),
        'retrieved_passages': len(dossier.knowledge_passages),
        'accepted_citations': len(dossier.grounded_claims),
        'citation_issues': dossier.generation_audit.get('issues', []),
        'repair_attempts': dossier.generation_audit.get('repair_attempts', 0),
        'legal_correctness_verified': False,
        'explanation': '检查步骤字段、事实引用和引文真实性；不代表法律结论正确率或胜诉概率。'}
