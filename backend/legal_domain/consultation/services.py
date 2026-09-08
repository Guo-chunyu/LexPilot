"""National official entry points and optional Amap POIs, with no venue inference."""
from datetime import datetime, timezone
import os
import re
from urllib.parse import urlencode

import httpx

from .research import SERVICE_LINKS
from .profiles import domain_label


def safe_city(value: str) -> str:
    """Only send an administrative city name, never a narrative/street address."""
    value = str(value)
    for name in ('北京', '上海', '天津', '重庆', '深圳', '广州', '杭州', '南京', '成都', '武汉', '西安', '苏州', '长沙', '郑州', '东莞', '佛山', '宁波', '合肥', '青岛', '济南', '厦门', '福州', '沈阳', '大连', '昆明', '南宁', '海口', '贵阳', '南昌', '长春', '哈尔滨'):
        if name in value:
            return name + '市'
    # A short standalone province/city string is allowed; full utterances aren't.
    if re.fullmatch(r'(?:[\u4e00-\u9fff]{2,8}省)?[\u4e00-\u9fff]{2,8}市', value):
        return value.split('省')[-1]
    return ''


def resolve_services(state, *, client=None) -> dict:
    dossier = state.consultation
    if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        return {'status': '需先确认当地机构', 'places': [], 'online_channels': [], 'call_script': '请当地法律服务机构核对适用法、管辖与期限。'}
    domain = state.case_type
    keyword = {'labor_dispute': '劳动人事争议仲裁委员会', 'consumer': '市场监督管理局',
        'criminal': '法律援助中心', 'administrative': '司法局', 'general': '公共法律服务中心'}.get(domain, '人民法院')
    keys = ['aid'] if domain in ('criminal', 'administrative', 'labor_dispute', 'general') else ['consumer', 'court', 'aid'] if domain == 'consumer' else ['court', 'aid']
    channels = [{'name': SERVICE_LINKS[k][0], 'url': SERVICE_LINKS[k][1],
        'use': {'court': '选择审判流程或立案服务，按地区与案件类型进入，核对管辖后提交；可拨12368询问当地入口。',
                'aid': '选择所在省市，查询公共法律服务、法律援助或人民调解机构；可拨12348说明事项并核对申请条件。',
                'consumer': '使用投诉入口提出民事消费诉求，举报入口反映违法线索；二者目的不同，分别保留编号。'}[k]} for k in keys]
    hotline = '12348' if domain in ('criminal', 'administrative', 'general') else '12333' if domain == 'labor_dispute' else '12315' if domain == 'consumer' else '12368'
    script = f'拨打{hotline}后这样说：“我需要办理{keyword}相关事项。请帮我核对受理机构全称、管辖条件、办公地址、窗口名称、工作时间、预约方式、材料份数和网上入口。我的案件类型是{domain_label(domain)}，当事人住所和履行地我会分别说明。请问缺少对方身份材料时如何补正？”记下答复日期和工单号。'
    result = {'status': '已提供官方入口；未取得线下地址', 'city': safe_city(state.facts.get('location', '')),
        'institution_type': keyword, 'places': [], 'online_channels': channels, 'call_script': script,
        'jurisdiction_note': '咨询者所在城市不等于有管辖权的所在地。地图结果只用于找路，先核对对方住所、履行地、文书指定机关或专属管辖。'}
    api_key = os.getenv('AMAP_API_KEY', '').strip()
    if not api_key or not result['city']:
        return result
    owned = client is None
    client = client or httpx.Client(timeout=5, follow_redirects=False)
    try:
        response = client.get('https://restapi.amap.com/v3/place/text', params={
            'key': api_key, 'keywords': keyword, 'city': result['city'], 'citylimit': 'true',
            'offset': 3, 'page': 1, 'extensions': 'all'})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('status') != '1':
            raise ValueError('POI service unavailable')
        pois = payload.get('pois', [])
        if not isinstance(pois, list):
            raise ValueError('Invalid POIs')
        for poi in pois[:3]:
            if not isinstance(poi, dict) or not all(isinstance(poi.get(k), str) for k in ('name', 'address', 'cityname', 'adname')):
                continue
            if not poi['address'] or result['city'].replace('市', '') not in poi['cityname']:
                continue
            if not any(t in poi['name'] for t in (keyword, '人民法院' if keyword == '人民法院' else keyword)):
                continue
            coordinates = str(poi.get('location', ''))
            if not re.fullmatch(r'\d{2,3}(?:\.\d+)?,\d{1,2}(?:\.\d+)?', coordinates):
                continue
            tel = poi.get('tel', '')
            result['places'].append({'name': poi['name'][:100],
                'address': poi['cityname'] + poi['adname'] + poi['address'],
                'telephone': tel[:100] if isinstance(tel, str) else '',
                'map_url': 'https://uri.amap.com/marker?' + urlencode({'position': coordinates, 'name': poi['name']}),
                'source': '高德地图POI检索', 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'jurisdiction_confirmed': False, 'office_hours': '未核验，请先电话确认',
                'status': '真实接口返回的候选机构，受理资格与地址仍需电话确认'})
        result['status'] = f'查询到{len(result["places"])}个候选机构；须确认管辖和办公时间'
    except (httpx.HTTPError, ValueError, TypeError):
        result['status'] = '机构地址查询暂不可用；可使用官方在线入口或电话核对'
    finally:
        if owned:
            client.close()
    return result


def service_guide(state):
    """Avoid repeated paid POI calls when a report rerenders in one case."""
    dossier = state.consultation
    key = '|'.join([state.case_type, dossier.jurisdiction_status, safe_city(state.facts.get('location', '')),
                    str(bool(os.getenv('AMAP_API_KEY'))), datetime.now(timezone.utc).date().isoformat()])
    if key != dossier.service_key:
        dossier.service_guide = resolve_services(state)
        dossier.service_key = key if '暂不可用' not in dossier.service_guide['status'] else ''
    return dossier.service_guide
