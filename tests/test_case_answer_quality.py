"""Regression tests for natural, case-specific consultation answers."""

import pytest

from backend.workflow import LexPilotEngine


@pytest.mark.parametrize(
    ('message', 'expected'),
    [
        ('朋友借了我五万元，到期不还，只有转账记录没有借条，想知道怎么追回。', '不是补造一张借条'),
        ('退房后房东一直扣着押金，说房间有损坏，我想拿回押金。', '具体损坏位置'),
        ('健身房关门了，我的会员卡还有余额，想知道怎样退款。', '经营主体'),
        ('我想离婚，孩子一直跟我生活，房子登记在对方名下，我想先弄清应该准备什么。', '房屋何时取得'),
        ('家人被刑事拘留，今天收到了通知书，我们现在该准备什么、找谁处理？', '不是先猜结果'),
    ],
)
def test_homepage_cases_receive_a_direct_case_specific_opening(message, expected):
    result = LexPilotEngine().process(message)
    assert expected in result['reply']
    assert result['case_state'].consultation.analysis in result['reply']


def test_only_transfer_without_iou_keeps_positive_and_negative_evidence_separate():
    state = LexPilotEngine().process(
        '我在深圳，朋友借钱不还，只有转账和聊天记录，没有借条，请给我方案'
    )['case_state']
    tasks = {task.name: task for task in state.consultation.evidence_tasks}
    assert tasks['借条'].status == '暂无法提供'
    assert tasks['转账记录'].status == '用户称有，尚未上传'
    assert tasks['催款记录'].status == '用户称有，尚未上传'
    assert '借条' not in {evidence.name for evidence in state.evidence}
    assert not any('保存借条原件' in line for line in state.final_report['action_plan'][1]['instructions'])


def test_rental_deposit_case_is_answered_from_the_tenant_perspective():
    state = LexPilotEngine().process(
        '退房后房东一直扣着押金，说房间有损坏，我想拿回押金，请给我方案。'
    )['case_state']
    assert state.final_report['strategy_comparison']['client_role']['id'] == 'tenant'
    assert '向出租人书面索取' in str(state.final_report['action_plan'])


def test_debt_plan_uses_case_materials_and_readable_fallbacks():
    state = LexPilotEngine().process(
        '我在深圳，朋友借了我五万元，只有转账和聊天记录，没有借条，请给我方案。'
    )['case_state']
    report = state.final_report
    assert '本人收到的通知或决定及送达凭证' not in report['action_plan'][0]['materials']
    assert report['analysis'].startswith('没有借条不等于')
    fallback = report['action_plan'][1]['fallback']
    assert fallback.startswith('材料暂时拿不到时：')
    assert '；；' not in fallback
