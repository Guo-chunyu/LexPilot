"""Explain how a regenerated plan differs from its prior structured snapshot."""

from __future__ import annotations

from hashlib import sha256
import json


FACT_LABELS = {
    'amount': '金额与履行情况',
    'constraints': '办理偏好与限制',
    'details': '关键事实与材料说明',
    'event_time': '事件时间',
    'evidence_inventory': '材料清单',
    'goal': '办理目标',
    'location': '地区与管辖线索',
    'parties': '当事人身份',
    'procedure': '程序与交涉进展',
}
ROUTE_LABELS = {
    'negotiation': '协商',
    'mediation': '调解',
    'formal': '正式程序',
}


def _snapshot(state, report: dict) -> dict:
    return {
        'facts': {key: str(value) for key, value in sorted(state.facts.items())},
        'evidence': {
            item.name: item.status
            for item in sorted(state.consultation.evidence_tasks, key=lambda item: item.name)
        },
        'recommended_route': report.get('strategy_comparison', {}).get('recommended_route', ''),
        'support_mode': report.get('support_bridge', {}).get('mode', ''),
        'action_titles': [item.get('title', '') for item in report.get('action_plan', [])],
    }


def _change(change_type, label, before, after, reason, impact) -> dict:
    return {
        'change_type': change_type,
        'label': label,
        'before': str(before) if before not in (None, '') else '未记录',
        'after': str(after) if after not in (None, '') else '未记录',
        'reason': reason,
        'impact': impact,
    }


def build_decision_delta(state, report: dict) -> dict:
    dossier = state.consultation
    current = _snapshot(state, report)
    previous = dossier.decision_snapshot
    snapshot_id = sha256(json.dumps(current, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    if not previous:
        result = {
            'model': 'deterministic_decision_delta_v1',
            'status': 'baseline',
            'summary': '这是本案首份结构化方案，已建立后续比较基线。',
            'changes': [],
            'unchanged': ['事实、材料状态、建议路线和接力强度将在后续报告中逐项比较。'],
            'snapshot_id': snapshot_id,
            'outcome_probability': None,
        }
        dossier.decision_snapshot = current
        return result

    changes = []
    old_facts, new_facts = previous.get('facts', {}), current['facts']
    for key in sorted(set(old_facts) | set(new_facts)):
        if old_facts.get(key) == new_facts.get(key):
            continue
        kind = 'fact_added' if key not in old_facts else 'fact_changed'
        reason = '本轮新增了结构化事实。' if kind == 'fact_added' else '本轮陈述更新了此前记录；是否属于明确更正或冲突以事实记录为准。'
        changes.append(_change(kind, FACT_LABELS.get(key, key), old_facts.get(key), new_facts.get(key), reason,
            '已重新生成事实摘要、路线比较和行动步骤；该事实仍须材料核对。'))

    old_evidence, new_evidence = previous.get('evidence', {}), current['evidence']
    for name in sorted(set(old_evidence) | set(new_evidence)):
        if old_evidence.get(name) != new_evidence.get(name):
            changes.append(_change('evidence_status_changed', name, old_evidence.get(name), new_evidence.get(name),
                '材料自述、上传或可得性状态发生变化。',
                '行动清单已按新状态更新；上传仅表示已接收，内容真实性和证明力仍需核对。'))

    if previous.get('recommended_route') != current['recommended_route']:
        changes.append(_change('route_changed', '建议路线', previous.get('recommended_route'), current['recommended_route'],
            '事实进展、程序状态或约束条件改变了路线排序。',
            '后续步骤改按新路线排列；法定期限和受理条件仍需向正式渠道核对。'))
    if previous.get('support_mode') != current['support_mode']:
        changes.append(_change('support_mode_changed', '接力强度', previous.get('support_mode'), current['support_mode'],
            '紧急程度、程序阶段、事实冲突或协助需要发生变化。',
            '人工支持建议已更新，但不会把接力建议当作案件结果判断。'))
    if previous.get('action_titles') != current['action_titles']:
        changes.append(_change('action_plan_changed', '行动步骤', ' → '.join(previous.get('action_titles', [])),
            ' → '.join(current['action_titles']), '路线或案件状态变化后重新排序了行动。',
            '请以本轮步骤为当前工作清单，旧报告仅作历史记录。'))

    if changes:
        status = 'changed'
        summary = f'本轮识别到 {len(changes)} 项结构化变化；每项均列出原因和对方案的影响。'
        unchanged = ['没有变化的事实与材料状态沿用此前记录，仍保持“待核实”属性。']
    else:
        status = 'no_material_change'
        summary = '本轮未发现会改变结构化事实、材料状态、建议路线或接力强度的内容。'
        unchanged = ['当前事实、材料状态、建议路线、接力强度和行动步骤均保持不变。']
    dossier.decision_snapshot = current
    return {
        'model': 'deterministic_decision_delta_v1', 'status': status,
        'summary': summary, 'changes': changes, 'unchanged': unchanged,
        'snapshot_id': snapshot_id, 'outcome_probability': None,
    }


def decision_delta_reply_lines(delta: dict) -> list[str]:
    """Render the material cross-turn changes in the chat, not only in the report."""
    if delta.get('status') != 'changed':
        return []
    visible = [
        item for item in delta.get('changes', [])
        if item.get('change_type') not in {'support_mode_changed', 'action_plan_changed'}
    ]
    lines = [f'**本轮方案变化**：{delta["summary"]}']
    for item in visible:
        before, after = item['before'], item['after']
        if item.get('change_type') == 'route_changed':
            before = ROUTE_LABELS.get(before, before)
            after = ROUTE_LABELS.get(after, after)
        lines.append(
            f'- {item["label"]}：{before} → {after}。'
            f'{item["reason"]}{item["impact"]}'
        )
    lines.append('')
    return lines
