"""Auditable self-service boundaries and a portable human-handoff packet."""

from __future__ import annotations

import re

from .intake import LABELS, QUESTIONS
from .profiles import domain_label


HIGH_COMPLEXITY_DOMAINS = {
    'criminal': '刑事措施需要尽快核对程序权利和办理机关。',
    'administrative': '行政程序的受理机关、起算点和救济路径需要结合文书核对。',
    'medical': '医疗争议通常需要专业材料、因果关系和损失项目核对。',
    'intellectual_property': '知识产权事项常同时涉及权属、侵权比对和专业取证。',
    'corporate': '公司事项可能涉及多方主体、内部文件和程序限制。',
    'enforcement': '执行事项需要依据生效文书和当前执行节点核对可用措施。',
}


def _signal(signal_id: str, explanation: str) -> dict:
    return {'signal_id': signal_id, 'explanation': explanation}


def build_support_bridge(state, report: dict, guide: dict | None = None) -> dict:
    """Select a reversible self-help/human-help path without predicting outcomes."""
    dossier = state.consultation
    guide = guide or {}
    reasons: list[dict] = []
    immediate = bool(dossier.urgent_actions)

    if immediate:
        reasons.append(_signal(
            'urgent_action',
            '已触发人身安全、强制措施或紧迫文书期限提示，不能等待完整材料。',
        ))
    if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        reasons.append(_signal(
            'jurisdiction_outside_mainland',
            '存在中国大陆以外或涉外因素，当前大陆法源与入口不能直接套用。',
        ))
    if dossier.conflicts:
        reasons.append(_signal(
            'fact_conflict',
            f'当前记录有 {len(dossier.conflicts)} 项不同陈述，需要由本人或专业人员先核对。',
        ))
    if state.case_type in HIGH_COMPLEXITY_DOMAINS:
        reasons.append(_signal(
            'domain_complexity',
            HIGH_COMPLEXITY_DOMAINS[state.case_type],
        ))
    procedure = str(state.facts.get('procedure', ''))
    if re.search(r'收到.{0,10}(?:传票|通知|决定|裁决|判决)|已经(?:起诉|仲裁|报案|申请执行)', procedure):
        reasons.append(_signal(
            'active_procedure',
            '用户陈述案件已进入正式程序或收到文书，应按原案号和文书节点核对。',
        ))
    constraints = str(state.facts.get('constraints', ''))
    if re.search(r'看不懂|不会操作|不会用|不方便到场|无法到场|听不清|看不清|需要.{0,4}帮', constraints):
        reasons.append(_signal(
            'stated_support_need',
            '用户明确表达了操作、理解或到场方面的支持需要，应提供可选择的人工协助路径。',
        ))
    if state.evidence_collection_exhausted:
        reasons.append(_signal(
            'evidence_limit_reached',
            '用户已说明暂时没有更多材料，继续重复追问不会改善当前准备。',
        ))

    priority = any(
        item['signal_id'] in {
            'jurisdiction_outside_mainland',
            'fact_conflict',
            'domain_complexity',
            'active_procedure',
        }
        for item in reasons
    )
    guided = any(
        item['signal_id'] in {'stated_support_need', 'evidence_limit_reached'}
        for item in reasons
    )
    if immediate:
        mode, label = 'immediate_handoff', '立即接力，数字方案只作准备'
        explanation = '先联系能够处理紧急事项的正式机构或专业人员；不要为补齐应用内信息延误行动。'
    elif priority:
        mode, label = 'priority_review', '优先人工核对，再决定正式提交'
        explanation = '可以继续用本应用整理材料，但在提交、签署或放弃权利前，优先完成一次人工核对。'
    elif guided:
        mode, label = 'guided_self_help', '在人工协助下继续自助'
        explanation = '当前仍可继续准备；把操作困难或材料边界一并交给官方热线、窗口或可信协助者。'
    else:
        mode, label = 'self_help', '可先自助准备，保留随时接力'
        explanation = '当前未识别到必须停止自助准备的信号；情况变化或准备受阻时可直接使用接力摘要。'

    fact_snapshot = [
        {
            'name': LABELS.get(key, key),
            'value': str(value),
            'status': '用户陈述或材料记载，待核实',
        }
        for key, value in state.facts.items()
        if key in LABELS
    ]
    missing_slots = [
        {
            'slot': slot,
            'question': QUESTIONS[slot],
            'status': '用户已表示不清楚或不便提供'
            if slot in dossier.declined_slots
            else '尚未记录',
        }
        for slot in ('location', 'event_time', 'goal', 'parties', 'procedure', 'evidence_inventory')
        if slot not in state.facts
        and not (
            slot == 'evidence_inventory'
            and (state.uploaded_files or state.evidence or state.evidence_collection_exhausted)
        )
    ][:4]
    ready_materials = [
        task.name for task in dossier.evidence_tasks
        if task.status.startswith('已上传') or task.status == '用户称有，尚未上传'
    ]
    missing_materials = [
        task.name for task in dossier.evidence_tasks
        if task.status in {'尚未提供', '暂无法提供'}
    ]
    institution = guide.get('institution_type') or (
        '当地执业律师、法律援助机构或正式受理窗口'
        if dossier.jurisdiction_status == 'OUTSIDE_MAINLAND'
        else '公共法律服务、法律援助或相应正式受理窗口'
    )
    signal_ids = {item['signal_id'] for item in reasons}
    if immediate:
        contact_target = '按紧急提示联系当地警方、急救机构、文书载明机关或能够及时介入的专业人员'
    elif dossier.jurisdiction_status == 'OUTSIDE_MAINLAND':
        contact_target = institution
    elif 'active_procedure' in signal_ids:
        contact_target = '文书载明的受理机关或原案号承办窗口；需要时同时联系当地执业律师或法律援助机构'
    else:
        contact_target = f'12348 公共法律服务；准备正式提交时再向{institution}核对'
    contact_script = (
        f'“我需要就{domain_label(state.case_type)}事项获得一次程序和材料核对。'
        f'目前已整理 {len(fact_snapshot)} 项事实、'
        f'{len(ready_materials)} 项已有或自述持有材料，'
        f'另有 {len(missing_materials)} 项材料缺口。'
        '请先帮我确认受理或答辩路径、最早需要处理的期限、必须提交的材料，'
        '以及哪些结论需要专业人员进一步判断。”'
    )
    first_steps = [
        {
            'title': step.get('title', ''),
            'completion': step.get('completion', ''),
        }
        for step in report.get('action_plan', [])[:2]
    ]
    return {
        'model': 'deterministic_support_bridge_v1',
        'title': '自助—人工接力通行证',
        'mode': mode,
        'label': label,
        'explanation': explanation,
        'human_review_recommended': mode in {'immediate_handoff', 'priority_review'},
        'reasons': reasons or [_signal(
            'no_escalation_signal',
            '尚未识别到紧急、正式程序、涉外、事实冲突或高复杂度领域信号。',
        )],
        'contact_target': contact_target,
        'contact_script': contact_script,
        'fact_snapshot': fact_snapshot,
        'open_questions': missing_slots,
        'ready_materials': ready_materials,
        'missing_materials': missing_materials,
        'first_steps': first_steps,
        'privacy_checklist': [
            '转交前遮盖与办理无关的身份证号、银行卡号、住址和第三人信息。',
            '仅向身份可核实的正式机构或本人选择的专业人员提供原始材料。',
            '先发送材料目录；对方确认必要性和安全渠道后再发送原件或完整副本。',
        ],
        'data_scope': '通行证仅整理当前案件中已经记录的内容，不会把材料上传给外部机构，也不替代对方的独立核对。',
        'completion_signal': '对方已确认接收人、办理事项、最早期限、所需材料和下一次联系节点。',
        'outcome_probability': None,
    }
