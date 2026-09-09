"""Native Streamlit views for the evolving dossier and concrete action plan."""

import streamlit as st
from hashlib import sha256

from backend.legal_domain.consultation.intake import LABELS
from backend.legal_domain.consultation.profiles import domain_label


def render_report_downloads(state) -> None:
    from backend.legal_domain.consultation.exports import export_report, MIME_TYPES
    from backend.legal_domain.consultation.reporting import report_markdown
    markdown = report_markdown(state)
    fingerprint = sha256((state.case_id + markdown).encode()).hexdigest()
    cache = st.session_state.get('_report_export_cache', {})
    if cache.get('fingerprint') != fingerprint:
        try:
            cache = {'fingerprint': fingerprint, 'docx': export_report(state, 'docx'), 'pdf': export_report(state, 'pdf')}
            st.session_state['_report_export_cache'] = cache
        except (ImportError, ValueError, RuntimeError, OSError):
            st.warning('Word/PDF 暂时无法生成，可以先下载文本报告；请检查文档组件安装。')
            return
    st.caption('下载当前完整方案，补充事实后会生成新版本。')
    with st.container(horizontal=True, gap='small'):
        for extension, label in [('docx', '下载 Word 方案'), ('pdf', '下载 PDF 方案')]:
            st.download_button(label, data=cache[extension], file_name=f'LexPilot_行动方案.{extension}',
                mime=MIME_TYPES[extension], key=f'download_report_{extension}',
                icon=':material/download:', type='primary' if extension == 'docx' else 'secondary', on_click='ignore')


def render_dossier(state) -> None:
    dossier = state.consultation
    st.caption('咨询领域 · ' + '、'.join(domain_label(key) for key in dossier.domain_ids or [state.case_type]))
    if dossier.urgent_actions:
        for action in dossier.urgent_actions:
            st.warning(action, icon=':material/priority_high:')
    if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        st.info('需先核对适用国家或地区的法律和办理渠道。', icon=':material/public:')
    if state.case_type != 'labor_dispute':
        st.caption(dossier.semantic_status)
    facts = [(LABELS[key], str(value)) for key, value in state.facts.items() if key in LABELS]
    if facts:
        with st.expander('已记录的事实与诉求', icon=':material/fact_check:'):
            st.caption('以下为用户陈述或材料记载，仍需核对；事实完整度不代表胜诉概率。')
            for label, value in facts:
                st.markdown(f'**{label}**')
                st.write(value)
    if dossier.conflicts:
        with st.expander('需要核对的不同陈述', expanded=True, icon=':material/compare_arrows:'):
            for conflict in dossier.conflicts:
                st.write(f'{conflict["fact"]}：此前“{conflict["previous"]}”，本轮“{conflict["current"]}”。请核对，金额变化也可能是已还款等原因。')
    if dossier.corrections:
        with st.expander('已确认的事实更正', icon=':material/edit_note:'):
            st.caption('当前方案采用更正后的值；旧值仅保留在变更记录中。')
            for correction in dossier.corrections:
                st.write(f'{correction["fact"]}：此前“{correction["previous"]}”，现更正为“{correction["current"]}”。')
    if dossier.timeline:
        with st.expander('事实时间线', icon=':material/timeline:'):
            st.caption('按记录顺序呈现；相对日期保留原话，尚未推算成确定日期。')
            for entry in dossier.timeline:
                st.markdown(f'**{entry.date_text}** · {entry.description}')
                st.caption(f'{entry.source_ref} · {entry.status}')


def render_plan_sections(state) -> None:
    report = state.final_report
    if report.get('analysis'):
        st.markdown('#### 初步分析')
        st.write(report['analysis'])
    if report.get('fact_corrections'):
        st.markdown('#### 本轮明确更正')
        st.caption('当前方案采用更正后的值，旧值仅作为历史记录。')
        for correction in report['fact_corrections']:
            st.write(f'{correction["fact"]}：此前“{correction["previous"]}”，现更正为“{correction["current"]}”。')
    strategy = report.get('strategy_comparison', {})
    if strategy:
        st.markdown('#### 先走哪条路')
        st.write(strategy['decision_reason'])
        role = strategy.get('client_role', {})
        if role:
            st.caption('咨询立场：' + role['label'] + ' · ' + role['basis'])
        with st.expander('比较成本、收益与转下一步的条件', icon=':material/alt_route:'):
            for route in strategy['routes']:
                if route['eligible']:
                    st.markdown(f'**{route["name"]}**' + (' · 建议优先' if route['recommended'] else ''))
                    st.write(route['reason'])
                    st.caption('投入：' + route['cost'])
                    st.write('何时停止等待：' + route['stop_condition'])
            for line in strategy['benefit_worksheet']:
                st.markdown('- ' + line)
    bridge = report.get('support_bridge', {})
    if bridge:
        st.markdown('#### 自助—人工接力通行证')
        message = bridge['label'] + '。' + bridge['explanation']
        renderer = st.warning if bridge.get('human_review_recommended') else st.info
        renderer(message, icon=':material/support_agent:')
        with st.expander('查看接力原因和可转交摘要', icon=':material/transfer_within_a_station:'):
            for item in bridge.get('reasons', []):
                st.markdown('- ' + item['explanation'])
            st.write('建议联系：' + bridge['contact_target'])
            st.write('联系时可直接说明：' + bridge['contact_script'])
            if bridge.get('fact_snapshot'):
                st.markdown('**已整理的事实快照**')
                for item in bridge['fact_snapshot']:
                    st.write(f'{item["name"]}：{item["value"]}')
                    st.caption(item['status'])
            if bridge.get('open_questions'):
                st.markdown('**转交后优先核对**')
                for item in bridge['open_questions']:
                    st.write(item['question'])
                    st.caption(item['status'])
            ready = '、'.join(bridge['ready_materials']) or '暂未记录'
            missing = '、'.join(bridge['missing_materials']) or '当前清单未显示缺口'
            st.write('已有或自述持有材料：' + ready)
            st.write('仍缺材料：' + missing)
            st.markdown('**安全转交**')
            for item in bridge.get('privacy_checklist', []):
                st.markdown('- ' + item)
            st.caption('完成标志：' + bridge['completion_signal'])
    guide = report.get('service_guide', {})
    if guide and guide.get('online_channels'):
        st.markdown('#### 办理入口与机构位置')
        for channel in guide['online_channels']:
            st.link_button(channel['name'], channel['url'], icon=':material/open_in_new:')
            st.caption(channel['use'])
        with st.expander('出发前确认地址、材料与受理窗口', icon=':material/location_on:'):
            st.write(guide['jurisdiction_note'])
            st.write(guide['call_script'])
            st.caption(guide['status'])
            for place in guide['places']:
                st.markdown('**' + place['name'] + '**')
                st.write(place['address'])
                st.write('电话：' + (place['telephone'] or '接口未提供'))
                st.caption(place['office_hours'] + '；' + place['status'])
                st.link_button('查看地图位置', place['map_url'], icon=':material/map:')
    for title, key in [('具体行动步骤', 'action_plan'), ('结合本案的补充步骤', 'tailored_action_plan')]:
        if report.get(key):
            st.markdown(f'#### {title}')
            if key == 'tailored_action_plan':
                st.caption('AI 个案草案，需核对事实、法律和当地办理要求。')
            for index, step in enumerate(report[key], 1):
                with st.expander(f'{index}. {step["title"]}', expanded=index == 1 and key == 'action_plan'):
                    st.write('何时做：' + step.get('suggested_date', '') + ' ' + step['when'])
                    st.caption(step.get('date_note', '建议日程不替代法定期限。'))
                    st.write('找谁办：' + step['channel'])
                    st.write('准备材料：' + '、'.join(step['materials']))
                    for instruction in step['instructions']:
                        st.markdown('- ' + instruction)
                    st.write('做到什么程度：' + step['completion'])
                    st.write('不顺利时：' + step['fallback'])
    if report.get('evidence_checklist'):
        with st.expander('证据怎么准备，没有时怎么办', icon=':material/inventory_2:'):
            for item in report['evidence_checklist']:
                st.markdown(f'**{item["name"]} · {item["status"]}**')
                st.write('要证明：' + item['proves'])
                st.write(item['how'])
                st.caption('替代办法：' + item['alternative'])
    sandbox = report.get('evidence_counterfactuals', {})
    if sandbox.get('cards'):
        st.markdown('#### 证据反事实沙盘')
        st.caption(sandbox['explanation'])
        for index, card in enumerate(sandbox['cards']):
            with st.expander(
                f'{card["name"]} · {card["priority"]}',
                expanded=index == 0,
                icon=':material/account_tree:',
            ):
                st.caption(f'当前状态：{card["current_status"]} · 要核对：{card["proves"]}')
                st.markdown('**如果材料支持**')
                st.write(card['if_supports'])
                st.markdown('**如果材料冲突**')
                st.write(card['if_conflicts'])
                st.markdown('**如果最终拿不到**')
                st.write(card['if_unavailable'])
                st.write('现在做：' + card['next_action'])
                st.caption('完成标志：' + card['completion_signal'])
    if report.get('opponent_arguments'):
        with st.expander('对方可能怎么说，如何准备', icon=':material/forum:'):
            for item in report['opponent_arguments']:
                st.write(item)
    if report.get('deadlines') or report.get('costs'):
        with st.expander('时间节点与费用', icon=':material/event:'):
            for item in report.get('deadlines', []):
                st.markdown(f'**{item["name"]}**')
                st.write(item['status'] + '；' + item['trigger'])
                st.caption(item['action'])
            for item in report.get('costs', []):
                st.write(item)
    if report.get('documents'):
        st.markdown('#### 可直接整理的材料草稿')
        for index, document in enumerate(report['documents']):
            with st.expander(document['title'], icon=':material/edit_document:'):
                st.caption(document['status'])
                st.text(document['content'])
                st.download_button('下载这份草稿', data=document['content'], file_name=f'{document["title"]}.txt', mime='text/plain', key=f'draft_{state.case_id}_{index}', on_click='ignore')
    if report.get('research_sources'):
        with st.expander('查看法源检索线索与核验状态', icon=':material/travel_explore:'):
            st.caption(report.get('research_status', ''))
            for source in report['research_sources']:
                st.markdown(f'[{source["title"]}]({source["url"]})')
                st.caption(source['status'])
    if report.get('grounded_claims'):
        st.markdown('#### 哪些事实支持当前分析')
        for claim in report['grounded_claims']:
            with st.expander(claim['conclusion'], icon=':material/account_tree:'):
                st.write('需满足：' + '；'.join(claim['conditions']))
                st.write('对应事实：' + '、'.join(LABELS.get(k, k) for k in claim['fact_ids']))
                for quote in claim['quotes']:
                    st.write(quote['quote'])
                    st.caption('引用编号：' + quote['source_id'])
    if report.get('knowledge_passages'):
        with st.expander('查看法条原文与版本', icon=':material/library_books:'):
            for passage in report['knowledge_passages']:
                st.markdown(f'**[{passage["law_name"]}{passage["article"]}]({passage["source_url"]})**')
                st.write(passage['text'])
                st.caption(f'快照核对日 {passage["checked_on"]} · 版本施行日 {passage["effective_from"]} · {passage["temporal_status"]}')
    audit = report.get('quality_audit', {})
    if audit:
        with st.expander('查看方案检查记录', icon=':material/fact_check:'):
            st.write(f'完整步骤 {audit["complete_step_count"]}/{audit["step_count"]}；检索正文 {audit["retrieved_passages"]} 条；引文完整性通过 {audit["accepted_citations"]} 项。')
            st.caption(audit['explanation'])
            st.caption(report.get('retrieval_audit', {}).get('status', ''))
