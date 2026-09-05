"""Small sourced starter set, deliberately separate from the full-law search leads.

These are paraphrases checked against the linked official texts on 2026-09-05.
They are not a complete corpus, a promise of continuing validity, or a finding
that a legal rule applies. Historical cases and conflicts need separate review.
"""

import re
from datetime import date

from backend.legal_rl.state import LawReference


CIVIL = 'https://www.court.gov.cn/zixun/xiangqing/233181.html'
INHERITANCE = 'https://www.cac.gov.cn/2020-06/01/c_15925617772683195.htm'
CONSUMER = 'https://www.samr.gov.cn/zfjcj/tzgg/art/2023/art_615af9ed6bcd4974bf853dd2e02bc663.html'
ADMIN = 'https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_70518816df484be18f6b38fa295750bb.html'
CHECKED_ON = date(2026, 9, 5)

# domain, article, summary, official URL, law name, version start, relevant terms
RULES = [
    ('debt', '第六百七十五条', '先查还款约定；期限仍无法确定时，可考虑催告并给予合理还款时间。', CIVIL, '中华人民共和国民法典', date(2021, 1, 1), ()),
    ('debt', '第六百七十九条', '自然人借款需核对实际交付款项，约定与交付证据应互相对应。', CIVIL, '中华人民共和国民法典', date(2021, 1, 1), ()),
    ('housing', '第七百三十三条', '租期结束需返还房屋；返还状态应结合约定及正常使用后的状态判断。', CIVIL, '中华人民共和国民法典', date(2021, 1, 1), ('租', '房东', '押金')),
    ('inheritance', '第一千一百二十三条', '遗产处理要区分法定继承、遗嘱或遗赠以及遗赠扶养协议。', INHERITANCE, '中华人民共和国民法典', date(2021, 1, 1), ()),
    ('consumer', '第五十三条', '预收款服务未按约提供时，可核对继续履行或退还预付款等请求。', CONSUMER, '中华人民共和国消费者权益保护法', date(2014, 3, 15), ('预付', '健身', '会员', '充值', '培训', '关门')),
    ('consumer', '第二十六条', '单方写明“不退”并不能结束判断，还要核对条款内容及提示说明情况。', CONSUMER, '中华人民共和国消费者权益保护法', date(2014, 3, 15), ('不退', '条款', '合同')),
    ('administrative', '第二十二条', '行政复议申请可依规定通过书面、指定网络等途径提出，口头申请有相应记录程序。', ADMIN, '中华人民共和国行政复议法', date(2024, 1, 1), ()),
    ('administrative', '第二十三条', '部分行政争议需要先复议；应根据具体行政行为核对是否适用前置程序。', ADMIN, '中华人民共和国行政复议法', date(2024, 1, 1), ()),
]


def relevant_rules(state) -> list[dict]:
    if state.consultation.jurisdiction_status == 'OUTSIDE_MAINLAND':
        return []
    event = str(state.facts.get('event_time', ''))
    year = re.search(r'(?<!\d)(19\d{2}|20\d{2})(?:年|-)', event)
    text = state.user_narrative + ' ' + ' '.join(str(v) for v in state.facts.values())
    result = []
    for domain, article, summary, url, law, start, terms in RULES:
        if domain != state.case_type or terms and not any(t in text for t in terms):
            continue
        if year and int(year.group(1)) < start.year:
            continue
        # A year alone cannot prove a version was effective on a particular day.
        applicable = '需核对本案事实、发生日、法律过渡规则及相关司法解释；不是最终适用结论。'
        if not year:
            applicable = '发生时间未明确，版本适用待核对。' + applicable
        if date.today() > CHECKED_ON:
            applicable += '应再次核对来源是否有后续修订。'
        result.append({
            'source_id': f'{domain}_{RULES.index((domain, article, summary, url, law, start, terms))}',
            'law_name': law, 'article': article, 'summary': summary, 'source_url': url,
            'effective_from': start.isoformat(), 'checked_on': CHECKED_ON.isoformat(),
            'temporal_validated': False, 'applicability': applicable,
        })
    return result


def update_rule_references(state) -> list[dict]:
    rules = relevant_rules(state)
    state.retrieved_laws = [LawReference(**{k: v for k, v in rule.items() if k not in ('checked_on', 'applicability')}) for rule in rules]
    return rules
