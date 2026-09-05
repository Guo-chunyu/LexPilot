"""Privacy-minimized official-source discovery; search hits are never verified law."""

from datetime import datetime, timezone
import os
from urllib.parse import urlparse

import httpx

from .models import ResearchSource
from .profiles import PROFILES


OFFICIAL_ROOTS = ('gov.cn', 'npc.gov.cn', 'court.gov.cn', 'spp.gov.cn')
SERVICE_LINKS = {
    'law': ('国家法律法规数据库', 'https://flk.npc.gov.cn/'),
    'court': ('人民法院在线服务', 'https://zxfw.court.gov.cn/'),
    'aid': ('中国法律服务网', 'https://www.12348.gov.cn/'),
    'consumer': ('全国12315平台', 'https://www.12315.cn/'),
}


def is_official_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        return parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443) and any(host == root or host.endswith('.' + root) for root in OFFICIAL_ROOTS)
    except ValueError:
        return False


def research_case(state, *, client: httpx.Client | None = None) -> None:
    dossier = state.consultation
    profile = PROFILES.get(state.case_type, PROFILES['general'])
    laws = list(dict.fromkeys(law for domain in dossier.domain_ids for law in PROFILES.get(domain, profile).laws))
    key = '|'.join(dossier.domain_ids) + '|' + str(state.facts.get('event_time', ''))
    if key == dossier.research_key:
        return
    dossier.research_key = key
    dossier.research_sources = [ResearchSource(
        source_id=f'catalog_{i}', title=law, url=SERVICE_LINKS['law'][1], status='检索目录，待核对条文与版本',
        summary='按法律名称检索，核对公布机关、施行和修订日期、案发时间及地方规定。此链接是检索入口，不是具体条文。',
    ) for i, law in enumerate(laws)]
    api_key = os.getenv('SERPER_API_KEY', '').strip()
    if not api_key:
        dossier.research_status = '尚未联网核验；当前提供官方检索入口，不将目录当作法律依据。'
        return
    # Only practice-area/law names go to the search service, never names, narrative,
    # file text, exact sums, addresses, or account identifiers.
    query = f'{profile.name} {" ".join(laws[:2])} 现行 司法解释 (site:npc.gov.cn OR site:gov.cn OR site:court.gov.cn OR site:spp.gov.cn)'
    owned = client is None
    client = client or httpx.Client(timeout=6, follow_redirects=False)
    try:
        response = client.post('https://google.serper.dev/search', headers={'X-API-KEY': api_key}, json={'q': query, 'num': 8})
        response.raise_for_status()
        payload = response.json()
        hits = payload.get('organic', []) if isinstance(payload, dict) else []
        seen = set()
        for hit in hits[:8] if isinstance(hits, list) else []:
            if not isinstance(hit, dict):
                continue
            url = str(hit.get('link', ''))
            if not is_official_url(url) or url in seen:
                continue
            seen.add(url)
            dossier.research_sources.append(ResearchSource(
                source_id=f'official_{len(seen)}', title=str(hit.get('title', '官方来源'))[:180], url=url,
                summary=str(hit.get('snippet', ''))[:600], status='官方检索线索，正文与时效待核验',
                retrieved_at=datetime.now(timezone.utc).isoformat(),
            ))
        dossier.research_status = f'找到 {len(seen)} 条官方网页线索；尚未逐条核对正文、适用范围及生效版本。'
    except (httpx.HTTPError, ValueError, TypeError):
        dossier.research_status = '在线检索暂不可用，已保留官方检索入口；具体条文及版本待核验。'
        dossier.research_key = ''  # A later turn may retry a transient outage.
    finally:
        if owned:
            client.close()
