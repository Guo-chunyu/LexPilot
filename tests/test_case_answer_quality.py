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
        ('市场监管局给我行政处罚，我想申请行政复议。', '救济告知'),
        ('我是公司股东，想查账但一直被拒绝。', '查阅目的'),
        ('有人盗用我的摄影作品并在网上售卖。', '创作源文件'),
        ('父亲去世留下遗嘱，家人对分配有争议。', '被继承人'),
        ('我被汽车撞伤，对方保险公司不赔。', '一次性结清'),
        ('医院手术后出现严重后遗症，怀疑医疗过错。', '不良结果本身不能直接证明'),
        ('有人在网上公开我的隐私并造谣。', '不要为了反击再次扩散'),
        ('已经胜诉但对方不履行判决，想申请强制执行。', '胜诉不等于款项会自动到账'),
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


def test_rejected_debt_request_keeps_available_evidence_and_skips_repeat_negotiation():
    result = LexPilotEngine().process(
        '朋友借钱到期不还，我有转账记录，没有借条，已经催款三次，对方拒绝还钱，请给我具体方案。'
    )
    state = result['case_state']
    tasks = {task.name: task for task in state.consultation.evidence_tasks}

    assert state.case_type == 'debt'
    assert tasks['借条'].status == '暂无法提供'
    assert tasks['转账记录'].status == '用户称有，尚未上传'
    assert tasks['催款记录'].status == '用户称有，尚未上传'
    assert state.final_report['strategy_comparison']['recommended_route'] != 'negotiation'
    assert '协商已经受阻' in result['reply']
    assert state.pending_questions and state.pending_questions[0] in result['reply']


def test_evidence_denial_after_material_name_is_not_treated_as_possession():
    state = LexPilotEngine().process(
        '朋友借钱不还，借条我没有，只有转账记录，请给我方案。'
    )['case_state']
    tasks = {task.name: task for task in state.consultation.evidence_tasks}
    assert tasks['借条'].status == '暂无法提供'
    assert tasks['转账记录'].status == '用户称有，尚未上传'


def test_material_followed_by_no_problem_is_still_treated_as_possession():
    state = LexPilotEngine().process(
        '朋友借钱不还，借条没问题，我有原件，请给我方案。'
    )['case_state']
    tasks = {task.name: task for task in state.consultation.evidence_tasks}
    assert tasks['借条'].status == '用户称有，尚未上传'


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


def test_missing_iou_answer_uses_debtor_perspective_when_user_is_borrower():
    result = LexPilotEngine().process(
        '我是借款人，向朋友借了五万元，没有借条，对方现在要求我还八万元。'
    )
    assert result['case_state'].case_type == 'debt'
    assert '对方主张的金额都正确' in result['reply']
    assert '催还情况' not in result['case_state'].consultation.analysis


def test_deposit_answer_uses_landlord_perspective_when_user_is_landlord():
    result = LexPilotEngine().process(
        '我是房东，租客退房后房间确有损坏，我需要从押金扣款。'
    )
    assert result['case_state'].case_type == 'housing'
    assert '押金不能不经核算就当然全部没收' in result['reply']
    assert '无争议的余额' in result['case_state'].consultation.analysis


def test_explicit_role_correction_uses_creditor_perspective():
    result = LexPilotEngine().process(
        '我不是借款人，是出借人；朋友借了五万元，没有借条，只有转账。'
    )
    assert result['case_state'].case_type == 'debt'
    assert '不是补造一张借条' in result['reply']
    assert result['case_state'].facts['parties'].endswith('是出借人')


def test_explicit_role_correction_uses_landlord_perspective():
    result = LexPilotEngine().process(
        '我不是租客，是房东；租客退房后房间有损坏，需要核算押金扣款。'
    )
    assert result['case_state'].case_type == 'housing'
    assert '押金不能不经核算就当然全部没收' in result['reply']
    assert result['case_state'].facts['parties'].endswith('是房东')
