"""Regression tests for the five defects in the 2026-09-13 user report.

The user replayed a real labour consultation and flagged:
1. the arrears total "共18000元" was treated as corrected by the later monthly
   wage answer "2万" even though the two do not conflict;
2. "一次说两条" still got only one question;
3. "我现在第一步应该干什么" was answered with the whole plan, not one step;
4. after handing back a plan the system never asked for the still-missing facts;
5. when the report was already usable the user was never told.
"""

from backend.workflow import LexPilotEngine

CONVERSATION = (
    '公司拖欠我3个月工资，共18000元。我没有劳动合同，但有工资流水、工作群聊天和考勤截图。公司已经明确拒绝支付，请先给我方案。',
    '你还需要我补充什么信息？一次说两条',
    '2026.8.11',
    '等一下，我应该是2025.8.11入职，然后中间大概有5个月',
    '2万',
    '暂时这些都没有',
    '那你根据我前面的信息，判断一下我现在第一步应该干什么',
)


def _replay(messages):
    engine = LexPilotEngine()
    state = None
    replies = []
    for message in messages:
        result = engine.process(message, state)
        state = result['case_state']
        replies.append(result['reply'])
    return replies, state


def test_monthly_wage_answer_does_not_conflict_with_arrears_total():
    replies, state = _replay(CONVERSATION[:5])

    # The arrears total is not overwritten by the monthly-wage answer.
    amount = str(state.facts.get('amount', ''))
    assert '18000' in amount, state.facts.get('amount')
    assert '2万' not in amount, state.facts.get('amount')
    assert state.facts.get('monthly_salary') == 20000.0
    # And no spurious conflict / correction was recorded against the amount.
    assert all(item.get('fact') != '金额陈述' for item in state.consultation.conflicts)
    assert all(item.get('fact') != '金额陈述' for item in state.consultation.corrections)


def test_user_can_request_two_questions_at_once():
    replies, state = _replay(CONVERSATION[:2])
    assert len(state.pending_questions) >= 2
    assert replies[1].count('？') >= 2


def test_plan_is_followed_by_a_proactive_question():
    replies, state = _replay(CONVERSATION[:1])
    # The plan must not end silently; it asks for the top missing fact.
    assert '？' in replies[0]
    assert '入职' in replies[0]


def test_first_step_request_returns_a_single_step():
    replies, state = _replay(CONVERSATION)
    assert '现在最先做这一步' in replies[-1]
    # It must not fall back to the five-step plan listing.
    assert '5. **' not in replies[-1]


def test_complete_report_is_announced_to_the_user():
    replies, state = _replay(CONVERSATION[:6])
    assert '现有信息已经比较完整' in replies[-1]
