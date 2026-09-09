"""Deterministic evidence what-if cards without invented outcome probabilities."""

from __future__ import annotations


ROUTE_LABELS = {
    'negotiation': '书面协商',
    'mediation': '平台处理或调解',
    'formal': '正式程序',
}


def _priority(task) -> tuple[int, str, str]:
    if task.status.startswith('已上传'):
        return 0, '立即核对', '文件已在案件中，先核对完整性、形成时间和上下文。'
    if task.status == '用户称有，尚未上传':
        return 1, '优先整理', '用户已表示持有，取得原始版本的现实成本通常较低。'
    if task.status == '暂无法提供':
        return 3, '替代取证', '原材料暂不可得，应尽快启动合法替代路径。'
    return 2, '补充材料', '该材料仍是当前证据缺口，需要确认保管人和取得方式。'


def build_evidence_counterfactuals(state, strategy: dict | None = None, limit: int = 4) -> dict:
    """Explain how each evidence outcome changes preparation, not case odds."""
    tasks = list(state.consultation.evidence_tasks)
    if not tasks:
        return {}
    strategy = strategy or {}
    route_id = strategy.get('recommended_route', 'formal')
    route = ROUTE_LABELS.get(route_id, '下一处理路线')
    ranked = sorted(
        enumerate(tasks),
        key=lambda pair: (_priority(pair[1])[0], pair[0]),
    )
    cards = []
    for original_index, task in ranked[:limit]:
        rank, priority, priority_reason = _priority(task)
        source_text = '、'.join(task.source_refs) if task.source_refs else '尚未记录文件来源'
        cards.append({
            'evidence_id': f'{state.case_type}:{original_index + 1}',
            'name': task.name,
            'current_status': task.status,
            'priority': priority,
            'priority_rank': rank,
            'why_now': priority_reason,
            'proves': task.proves,
            'source_refs': list(task.source_refs),
            'source_status': source_text,
            'if_supports': (
                f'如果核对后的内容、主体、时间和上下文能够支持“{task.proves}”，'
                f'可将这一争点从材料缺口推进为初步支持，并在{route}中按证据编号引用；'
                '仍需与其他材料和适用规则共同判断。'
            ),
            'if_conflicts': (
                '如果内容与当前陈述或其他材料不一致，保留原始版本并登记冲突，'
                '重新核算请求或抗辩范围；不要删除、截断或隐藏不利内容。'
            ),
            'if_unavailable': (
                f'如果最终无法取得：{task.alternative} '
                '替代材料只能补强相应事实，不能自动等同于原材料。'
            ),
            'next_action': (
                f'围绕“{task.proves}”完成一次核对：记录来源、形成时间、完整性和与其他材料的对应关系。'
            ),
            'completion_signal': (
                '形成一条可追溯记录：材料编号、原件位置、证明目的、冲突说明和下一步使用位置。'
            ),
            'outcome_probability': None,
        })
    return {
        'model': 'deterministic_evidence_counterfactuals_v1',
        'title': '证据反事实沙盘',
        'explanation': (
            '分别预演材料支持、相互冲突和最终拿不到时的方案变化。'
            '这是证据准备决策，不预测胜率，也不把上传或自述当成事实已证明。'
        ),
        'recommended_route': route_id,
        'next_best_evidence_id': cards[0]['evidence_id'] if cards else '',
        'cards': cards,
    }
