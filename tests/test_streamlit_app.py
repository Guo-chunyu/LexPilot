from pathlib import Path
import tomllib

from streamlit.testing.v1 import AppTest

from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"
THEME_PATH = APP_PATH.parent / ".streamlit" / "config.toml"


def _contrast_ratio(first: str, second: str) -> float:
    def relative_luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_theme_primary_actions_meet_wcag_aa_contrast():
    theme = tomllib.loads(THEME_PATH.read_text(encoding="utf-8"))["theme"]

    assert _contrast_ratio(theme["primaryColor"], "#FFFFFF") >= 4.5
    assert _contrast_ratio(theme["sidebar"]["primaryColor"], "#FFFFFF") >= 4.5


def test_empty_workspace_exposes_the_case_review_sequence():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()

    captions = [item.value for item in at.caption]
    assert "事实梳理 → 证据核对 → 法源分析 → 行动方案" in captions
    assert not at.exception


def test_workspace_marks_the_phase_for_the_current_action():
    state = CaseState(
        current_action=LegalAction.REQUEST_EVIDENCE,
        current_reason="需要补充能证明关键事实的材料。",
    )
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.session_state["case_state"] = state.model_dump(mode="json")
    at.run()

    assert "当前阶段 · 证据核对" in [item.value for item in at.caption]
    assert not at.exception


def test_processing_error_leads_with_a_recovery_action():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20)
    at.session_state["last_error"] = "RuntimeError: upstream unavailable"
    at.run()

    assert at.error[0].value == "本轮处理未完成。请原样重新发送上一条消息。"
    assert not at.exception


def test_streamlit_supports_rule_only_two_turn_chat_and_evidence_upload():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    assert not at.exception
    assert "use_dqn" not in at.session_state
    assert "policy_type" not in at.session_state
    assert at.button(key="new_case")
    assert at.pills(key="starter_suggestion")
    assert at.chat_input[0].proto.accept_file != 0
    assert ".pdf" in at.chat_input[0].proto.file_type
    assert ".docx" in at.chat_input[0].proto.file_type
    assert ".png" in at.chat_input[0].proto.file_type
    assert at.chat_input[0].proto.max_upload_size_mb == 15

    at.chat_input[0].set_value(
        "我在公司工作8个月，昨天领导微信说我明天不用来了，说我试用期表现不合格，也没有给赔偿。"
    ).run(timeout=20)
    at.chat_input[0].set_value("签了").run(timeout=20)

    state = at.session_state["case_state"]
    assert state.facts["has_written_contract"] is True
    assert "多长期限" in at.session_state["messages"][-1]["content"]
    assert len(at.session_state["messages"]) == 4
    assert not at.exception

    at.chat_input[0].set_value("三年").run(timeout=20)
    at.chat_input[0].set_value("六个月").run(timeout=20)
    assert "录用条件" in at.session_state["messages"][-1]["content"]

    at.chat_input[0].set_value("告知并留存了").run(timeout=20)
    state = at.session_state["case_state"]
    assert state.facts["recruitment_conditions_disclosed"] is True
    assert "录用条件" not in at.session_state["messages"][-1]["content"]
    assert "考核" in at.session_state["messages"][-1]["content"]
    assert len(at.session_state["messages"]) == 10
    assert not at.exception

    at.chat_input[0].set_value("没有，公司没给我看过考核材料").run(timeout=20)
    at.chat_input[0].set_value("只有微信通知，没有书面通知").run(timeout=20)
    assert "平均月工资" in at.session_state["messages"][-1]["content"]

    at.chat_input[0].set_value("一个月一万").run(timeout=20)
    state = at.session_state["case_state"]
    assert state.facts["monthly_salary"] == 10000
    assert "平均月工资" not in at.session_state["messages"][-1]["content"]
    assert "手头有没有" in at.session_state["messages"][-1]["content"]
    assistant_messages = [
        message["content"]
        for message in at.session_state["messages"]
        if message["role"] == "assistant"
    ]
    assert all("为判断案件，先补充一个关键事实" not in message for message in assistant_messages)
    assert not at.exception

    at.chat_input[0].set_value("剩下的没有了").run(timeout=20)
    state = at.session_state["case_state"]
    assert state.evidence_collection_exhausted is True
    assert state.pending_evidence_requests == []
    assert "不会再重复让你补同样的材料" in at.session_state["messages"][-1]["content"]
    assert "手头有没有" not in at.session_state["messages"][-1]["content"]
    assert not at.exception


def test_streamlit_starter_suggestion_creates_a_case():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.pills(key="starter_suggestion").set_value("试用期被辞退").run(timeout=20)

    assert at.session_state["case_state"] is not None
    assert len(at.session_state["messages"]) == 2
    assert "劳动合同" in at.session_state["messages"][-1]["content"]
    assert not at.exception


def test_sidebar_does_not_offer_a_visual_motion_setting():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()

    assert len(at.toggle) == 0
    assert "motion_enabled" not in at.session_state
    assert not at.exception


def test_general_case_can_generate_plan_then_continue_and_reset():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()
    at.chat_input[0].set_value('朋友借钱不还，我想追回借款').run()
    assert at.session_state['case_state'].case_type == 'debt'
    at.button(key='generate_current_plan').click().run()
    state = at.session_state['case_state']
    assert state.final_report['action_plan']
    assert len(at.expander) >= 4, 'Concrete steps must be exposed for review'
    assert at.get('download_button'), 'Plans and working drafts must be downloadable'
    at.chat_input[0].set_value('广东省深圳市南山区').run()
    assert at.session_state['case_state'].facts['location'] == '广东省深圳市南山区'
    assert at.session_state['case_state'].final_report['action_plan']
    at.button(key='new_case').click().run()
    assert at.session_state['case_state'] is None
    assert not at.exception


def test_particle_balance_is_rendered_in_the_right_hero_region():
    at = AppTest.from_file(str(APP_PATH), default_timeout=20).run()

    shell = next(
        child
        for child in at.main.children.values()
        if getattr(child, "key", "") in {"experience_intro", "experience_steady"}
    )
    hero = shell.children[0]
    columns = hero.children[0]
    copy_column, visual_column = columns.children.values()

    assert hero.key == "hero_stage"
    assert copy_column.children[0].key == "hero_copy"
    assert visual_column.children[0].key == "hero_visual"
    assert visual_column.children[0].children[0].key == "lexpilot_evidence_constellation"
    assert not at.exception
