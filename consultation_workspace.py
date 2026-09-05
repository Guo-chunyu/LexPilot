"""Native Streamlit views for the evolving dossier and concrete action plan."""

import streamlit as st

from backend.legal_domain.consultation.intake import LABELS
from backend.legal_domain.consultation.profiles import domain_label


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
    for title, key in [('具体行动步骤', 'action_plan'), ('结合本案的补充步骤', 'tailored_action_plan')]:
        if report.get(key):
            st.markdown(f'#### {title}')
            if key == 'tailored_action_plan':
                st.caption('AI 个案草案，需核对事实、法律和当地办理要求。')
            for index, step in enumerate(report[key], 1):
                with st.expander(f'{index}. {step["title"]}', expanded=index == 1 and key == 'action_plan'):
                    st.write('何时做：' + step['when'])
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
