"""Fetch a bounded, reviewed set of official statutes; build reproducible snapshots.

Run explicitly after reviewing the manifest. This is not a whole-web crawler or
a claim that the included versions are the latest laws. Failed downloads never
replace existing snapshots. stdout contains counts/statuses, not case data.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.legal_domain.consultation.research import is_official_url


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.skip += 1
        if tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'tr'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.skip = max(0, self.skip - 1)
        if tag in ('p', 'div', 'li', 'h1', 'h2', 'tr'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract_text(html):
    parser = TextExtractor()
    parser.feed(html)
    return '\n'.join(re.sub(r'[\t \u3000\xa0]+', ' ', line).strip() for line in ''.join(parser.parts).splitlines() if line.strip())


def chinese_number(n):
    digits = '零一二三四五六七八九'
    if n < 10:
        return digits[n]
    if n < 100:
        return ('' if n < 20 else digits[n // 10]) + '十' + (digits[n % 10] if n % 10 else '')
    if n < 1000:
        rest = n % 100
        return digits[n // 100] + '百' + (('零' + digits[rest]) if 0 < rest < 10 else ('一' if 10 <= rest < 20 else '') + chinese_number(rest) if rest else '')
    rest = n % 1000
    return digits[n // 1000] + '千' + (('零' if 0 < rest < 100 else '') + ('一' if 10 <= rest < 20 else '') + chinese_number(rest) if rest else '')


CIVIL_DOMAINS = ['debt', 'housing', 'consumer', 'contract', 'family', 'inheritance', 'traffic', 'medical', 'tort', 'intellectual_property', 'corporate']
MANIFEST = [
    dict(id='civil', law='中华人民共和国民法典', url='https://fgk.chinatax.gov.cn/zcfgk/c100009/c5212250/content.html', start='2021-01-01',
         articles={188: CIVIL_DOMAINS, 196: CIVIL_DOMAINS, 496: ['contract', 'consumer'], 497: ['contract', 'consumer'],
             509: ['contract', 'housing'], 577: ['contract', 'housing', 'consumer'], 584: ['contract'], 585: ['contract'],
             667: ['debt'], 675: ['debt'], 676: ['debt'], 679: ['debt'], 680: ['debt'],
             709: ['housing'], 710: ['housing'], 733: ['housing'], 1024: ['tort'], 1032: ['tort'],
             1077: ['family'], 1079: ['family'], 1084: ['family'], 1091: ['family'],
             1123: ['inheritance'], 1133: ['inheritance'], 1179: ['traffic', 'tort', 'medical'],
             1182: ['tort'], 1208: ['traffic'], 1213: ['traffic'], 1218: ['medical'],
             1222: ['medical'], 1225: ['medical'], 1185: ['intellectual_property']}),
    dict(id='labor_procedure', law='中华人民共和国劳动争议调解仲裁法', url='https://chinajob.mohrss.gov.cn/h5/c/2022-07-15/356212.shtml', start='2008-05-01',
         articles={n: ['labor_dispute'] for n in [2, 5, 6, 21, 27, 28, 29, 43, 47, 48, 50, 53]}),
    dict(id='consumer', law='中华人民共和国消费者权益保护法', url='https://www.samr.gov.cn/zfjcj/tzgg/art/2023/art_615af9ed6bcd4974bf853dd2e02bc663.html', start='2014-03-15',
         articles={n: ['consumer'] for n in [24, 25, 26, 39, 44, 53, 55]}),
    dict(id='administrative', law='中华人民共和国行政复议法', url='https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_70518816df484be18f6b38fa295750bb.html', start='2024-01-01',
         articles={n: ['administrative'] for n in [20, 22, 23, 24, 27]}),
    dict(id='criminal_procedure', law='中华人民共和国刑事诉讼法', url='https://www.samr.gov.cn/jjz/djfg/gjflfg/art/2023/art_929f3de7d593441bbe63fe0eecd05e10.html', start='2018-10-26',
         articles={n: ['criminal'] for n in [34, 35, 37, 39, 67, 85]}),
    dict(id='civil_procedure', law='中华人民共和国民事诉讼法', url='https://fgk.chinatax.gov.cn/zcfgk/c100009/c5220330/content.html', start='2024-01-01',
         articles={22: CIVIL_DOMAINS, 24: ['debt', 'contract'], 34: ['housing'], 67: CIVIL_DOMAINS,
                   104: CIVIL_DOMAINS, 122: CIVIL_DOMAINS, 126: CIVIL_DOMAINS, 235: ['enforcement'], 250: ['enforcement'] }),
    dict(id='company', law='中华人民共和国公司法', url='https://tianjin.chinatax.gov.cn/11200000000/0300/030004/03000418/20240920114422835.shtml', start='2024-07-01',
         articles={n: ['corporate'] for n in [23, 54, 57, 88]}),
    dict(id='fees', law='诉讼费用交纳办法', url='https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_b7b56c4657c64656894e66c7e1a993dc.html', start='2007-04-01',
         articles={13: CIVIL_DOMAINS, 16: CIVIL_DOMAINS, 29: CIVIL_DOMAINS, 44: CIVIL_DOMAINS}),
]


def fetch(source):
    try:
        with httpx.Client(timeout=18, follow_redirects=False) as client:
            url = source['url']
            for _ in range(3):
                if not is_official_url(url):
                    raise ValueError('Nonofficial redirect')
                response = client.get(url, headers={'User-Agent': 'LexPilot-LegalSnapshot/1.0'})
                if response.is_redirect:
                    url = str(response.url.join(response.headers['location']))
                    continue
                response.raise_for_status()
                break
            else:
                raise ValueError('Redirect limit')
        if len(response.content) > 5_000_000:
            raise ValueError('Page too large')
        charset = re.search(rb'charset\s*=\s*["\']?([\w-]+)', response.content[:5000], re.I)
        encoding = charset.group(1).decode() if charset else 'utf-8'
        body = extract_text(response.content.decode(encoding, errors='replace'))
        matches = list(re.finditer(r'(?:^|\n)\s*(第[零一二三四五六七八九十百千]+条)\s+', body))
        by_article = {m.group(1): body[m.start(): matches[i+1].start() if i+1 < len(matches) else len(body)].strip() for i, m in enumerate(matches)}
        result = []
        for n, domains in source['articles'].items():
            article = '第' + chinese_number(n) + '条'
            text = by_article.get(article, '')
            # Do not ingest chapter headings, web navigation or huge page tails.
            text = re.split(r'\n第[一二三四五六七八九十]+[章节编]', text)[0].strip()
            if len(text) < 16 or len(text) > 5500:
                continue
            result.append(dict(source_id=f'{source["id"]}_{n}', law_name=source['law'], article=article,
                text=text, domains=domains, source_url=url, effective_from=source['start'], effective_to='',
                checked_on=date.today().isoformat(), snapshot_hash=sha256(body.encode()).hexdigest(),
                keywords=[], provenance='official_html_article_extraction', version_status='已核对来源文本；未保证无后续修订'))
            result[-1]['temporal_scope'] = 'procedure' if source['id'] in ('civil_procedure', 'criminal_procedure', 'labor_procedure', 'fees') else 'substantive'
        return source['id'], result, '' if len(result) == len(source['articles']) else f'expected {len(source["articles"])} got {len(result)}'
    except (httpx.HTTPError, ValueError, LookupError, KeyError) as exc:
        return source['id'], [], type(exc).__name__


def main():
    destination = ROOT / 'data' / 'legal_knowledge.json'
    old = json.loads(destination.read_text(encoding='utf-8'))['passages'] if destination.exists() else []
    records = {p['source_id']: p for p in old}
    # The reviewed manifest is authoritative for this managed snapshot. Remove
    # retired article selections; keep old text only for still-selected entries.
    selected = {f'{s["id"]}_{n}' for s in MANIFEST for n in s['articles']}
    records = {sid: p for sid, p in records.items() if sid in selected}
    failures = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for source_id, passages, error in pool.map(fetch, MANIFEST):
            records.update({p['source_id']: p for p in passages})
            print(f'{source_id}: {len(passages)} articles' + (f' ({error})' if error else ''))
            if error:
                failures.append(source_id)
    value = {'schema_version': 1, 'snapshot_date': date.today().isoformat(),
             'notice': '有限的官方正文快照；不保证全量、最新或个案适用。历史版本与地方规则需另行核对。',
             'passages': sorted(records.values(), key=lambda p: p['source_id'])}
    destination.parent.mkdir(exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(destination)
    print(json.dumps({'total': len(records), 'partial_or_failed_sources': failures}))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
