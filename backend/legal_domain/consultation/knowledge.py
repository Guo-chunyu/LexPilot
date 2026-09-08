"""Version-aware Chinese lexical retrieval with SQLite FTS5 and multi-query RRF.

No model download or network call occurs on import. The corpus is official text,
not conversation history. Retrieval scores are ranks, never legal confidence.
"""
from contextlib import contextmanager
from datetime import date
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3

from .profiles import PROFILES
from .research import is_official_url

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / 'data' / 'legal_knowledge.json'


def tokens(text: str) -> list[str]:
    """Chinese bigrams plus Latin words; doesn't require an online tokenizer."""
    parts = re.findall(r'[\u4e00-\u9fff]+|[a-z0-9_]+', text.lower())
    return list(dict.fromkeys(token for part in parts for token in
        ([part] if not re.search(r'[\u4e00-\u9fff]', part) or len(part) < 2
         else [part[i:i+2] for i in range(len(part)-1)])))[:240]


def parse_event_date(value: str) -> str:
    match = re.search(r'(20\d{2}|19\d{2})[-年](\d{1,2})[-月](\d{1,2})(?:日)?', str(value))
    if not match:
        return ''
    try:
        return date(*map(int, match.groups())).isoformat()
    except ValueError:
        return ''


class LegalKnowledgeBase:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as con:
            con.execute('CREATE TABLE IF NOT EXISTS passages (source_id TEXT PRIMARY KEY, payload TEXT NOT NULL, content_hash TEXT NOT NULL)')
            con.execute('CREATE VIRTUAL TABLE IF NOT EXISTS passage_search USING fts5(source_id UNINDEXED, body, tokenize="unicode61")')

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=10)
        try:
            with con:
                yield con
        finally:
            con.close()

    def upsert(self, passages: list[dict], *, replace=False) -> None:
        if replace and not passages:
            raise ValueError('Do not replace a managed corpus with an empty snapshot')
        with self.connection() as con:
            for item in passages:
                if not is_official_url(item.get('source_url', '')):
                    raise ValueError('Corpus source must be an official HTTPS URL')
                if not all(item.get(k) for k in ('source_id', 'law_name', 'article', 'text', 'domains', 'effective_from', 'checked_on')):
                    raise ValueError('Incomplete legal passage metadata')
                for key in ('effective_from', 'effective_to', 'checked_on'):
                    if item.get(key):
                        date.fromisoformat(item[key])
                payload = json.dumps(item, ensure_ascii=False, sort_keys=True)
                digest = sha256(payload.encode()).hexdigest()
                old = con.execute('SELECT content_hash FROM passages WHERE source_id=?', (item['source_id'],)).fetchone()
                if old and old[0] == digest:
                    continue
                con.execute('INSERT OR REPLACE INTO passages VALUES(?,?,?)', (item['source_id'], payload, digest))
                con.execute('DELETE FROM passage_search WHERE source_id=?', (item['source_id'],))
                body = ' '.join(tokens(item['law_name'] + item['article'] + item['text'] + ' '.join(item.get('keywords', []))))
                con.execute('INSERT INTO passage_search VALUES(?,?)', (item['source_id'], body))
            if replace:
                ids = [p['source_id'] for p in passages]
                placeholders = ','.join('?' for _ in ids) or 'NULL'
                con.execute(f'DELETE FROM passages WHERE source_id NOT IN ({placeholders})', ids)
                con.execute('DELETE FROM passage_search WHERE source_id NOT IN (SELECT source_id FROM passages)')

    def search(self, queries: list[str], domains: list[str], *, event_date='', limit=8, query_weights=(4.0, 1.0, 0.5, 0.5)) -> list[dict]:
        event = parse_event_date(event_date)
        year = re.search(r'(?:19|20)\d{2}', str(event_date))
        scores, passages, traces = {}, {}, {}
        with self.connection() as con:
            for query_index, query in enumerate(queries[:4]):
                terms = tokens(query)
                if not terms:
                    continue
                expression = ' OR '.join('"' + t.replace('"', '') + '"' for t in terms[:80])
                rows = con.execute('SELECT p.payload, p.content_hash FROM passage_search s JOIN passages p ON p.source_id=s.source_id WHERE passage_search MATCH ? ORDER BY bm25(passage_search) LIMIT 100', (expression,)).fetchall()
                rank = 0
                for payload, digest in rows:
                    item = json.loads(payload)
                    if not set(domains).intersection(item['domains']) and 'all' not in item['domains']:
                        continue
                    procedural = item.get('temporal_scope') == 'procedure'
                    version_date = date.today().isoformat() if procedural else event
                    if version_date and (version_date < item['effective_from'] or item.get('effective_to') and version_date >= item['effective_to']):
                        continue
                    if not procedural and not event and year and int(year.group()) < int(item['effective_from'][:4]):
                        continue
                    rank += 1
                    sid = item['source_id']
                    weight = query_weights[min(query_index, len(query_weights)-1)]
                    scores[sid] = scores.get(sid, 0) + weight / (60 + rank)
                    traces.setdefault(sid, []).append({'query_index': query_index, 'rank': rank})
                    passages[sid] = {**item, 'content_hash': digest}
        result = []
        for sid in sorted(scores, key=lambda s: (-scores[s], s))[:limit]:
            result.append({**passages[sid], 'retrieval_score': round(scores[sid], 6),
                'retrieval_trace': traces[sid], 'temporal_validated': False,
                'temporal_status': '程序法版本按当前日期筛选；实际办理时点及过渡规则待核对' if passages[sid].get('temporal_scope') == 'procedure' else '版本起始条件满足，仍须核对修订和过渡规则' if event else '日期未确认，不能确定版本适用',
                'status': '官方正文快照，当前效力与个案适用待核对'})
        return result


@lru_cache(maxsize=4)
def _database(path: str, corpus_version: int) -> LegalKnowledgeBase:
    kb = LegalKnowledgeBase(path)
    if CORPUS.exists():
        kb.upsert(json.loads(CORPUS.read_text(encoding='utf-8'))['passages'], replace=True)
    return kb


def retrieve_for_case(state) -> list[dict]:
    dossier = state.consultation
    dossier.knowledge_passages = []
    if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        dossier.retrieval_audit = {'status': '需使用当地法源', 'passage_count': 0}
        return []
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    # Local query can use case facts. It is never transmitted to a search API.
    queries = [state.user_narrative + ' ' + str(state.facts.get('details', '')),
        ' '.join(profile.keywords) + ' ' + str(state.facts.get('goal', '')),
        profile.focus + ' ' + profile.route]
    path = os.getenv('LEXPILOT_KNOWLEDGE_DB', str(ROOT / '.local_data' / 'legal_knowledge.sqlite3'))
    try:
        kb = _database(path, CORPUS.stat().st_mtime_ns if CORPUS.exists() else 0)
        hits = kb.search(queries, dossier.domain_ids or [state.case_type], event_date=str(state.facts.get('event_time', '')))
        dossier.knowledge_passages = hits
        dossier.retrieval_audit = {'status': '已检索官方正文快照' if hits else '本地依据不足，需补充官方检索',
            'method': 'Chinese bigram FTS5 BM25 + weighted multi-query RRF (k=60, weights=4/1/0.5)',
            'query_count': len(queries), 'passage_count': len(hits),
            'correction_needed': len(hits) < 2, 'legal_correctness_verified': False}
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
        dossier.retrieval_audit = {'status': '本地知识库暂不可用，继续使用基础法源和官方入口', 'passage_count': 0, 'correction_needed': True}
    return dossier.knowledge_passages
