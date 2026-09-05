"""LexPilot consultation workspace: facts, evidence, research and action plans."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st
from streamlit.typing import ChatInputValue, UploadedFile

from backend.config import LEXPILOT_UPLOAD_DIR
from backend.graph import invoke_lexpilot
from backend.legal_domain.consultation.profiles import route_case, PROFILES, domain_label
from backend.legal_domain.consultation.reporting import report_markdown
from consultation_workspace import render_dossier, render_plan_sections
from backend.legal_domain.labor.evidence_upload import (
    CURRENT_EVIDENCE_PARSER_VERSION,
    MAX_FILE_BYTES,
    STREAMLIT_FILE_TYPES,
    UploadPayload,
    ingest_evidence_files,
    refresh_stored_evidence,
)
from backend.legal_domain.labor.facts import extract_labor_facts
from backend.legal_rl.actions import LegalAction
from backend.legal_rl.state import CaseState, EvidenceStatus, FileExtractionStatus
from evidence_constellation import render_evidence_constellation
from frontend_experience import (
    experience_shell_key,
    render_brand,
    render_motion_styles,
    sidebar_shell_key,
)


st.set_page_config(
    page_title="LexPilot 律策 · 法律咨询与行动方案",
    page_icon=":material/balance:",
    layout="wide",
    initial_sidebar_state="auto",
)


ACTION_LABELS = {
    LegalAction.ASK_FACT: "补充关键事实",
    LegalAction.REQUEST_EVIDENCE: "完善证据材料",
    LegalAction.SEARCH_LAW: "核对法律依据",
    LegalAction.SEARCH_CASE: "参考同类案件",
    LegalAction.SIMULATE_OPPONENT: "分析对方抗辩",
    LegalAction.VERIFY: "复核案件结论",
    LegalAction.CALCULATE: "测算可能金额",
    LegalAction.GENERATE_DOCUMENT: "整理行动方案",
    LegalAction.STOP: "形成阶段报告",
    LegalAction.ESCALATE_HUMAN: "建议人工复核",
}

EVIDENCE_LABELS = {
    EvidenceStatus.PROVEN: ("已有支持", "green", ":material/check_circle:"),
    EvidenceStatus.PARTIAL: ("部分支持", "orange", ":material/pending:"),
    EvidenceStatus.MISSING: ("尚缺材料", "red", ":material/error:"),
    EvidenceStatus.CONFLICT: ("存在冲突", "violet", ":material/warning:"),
}

EXTRACTION_LABELS = {
    FileExtractionStatus.TEXT_EXTRACTED: ("已提取文本", "green"),
    FileExtractionStatus.METADATA_ONLY: ("已安全留存", "blue"),
    FileExtractionStatus.PARSER_UNAVAILABLE: ("需人工查看", "orange"),
    FileExtractionStatus.FAILED: ("解析失败", "red"),
}

SUGGESTIONS = {
    "试用期被辞退": "我在公司工作8个月，领导说我试用期表现不合格，明天不用来了，也没有给赔偿。",
    "借钱不还怎么办": "朋友借了我五万元，到期不还，只有转账记录没有借条，想知道怎么追回。",
    "离婚与孩子安排": "我想离婚，孩子一直跟我生活，房子登记在对方名下，我想先弄清应该准备什么。",
    "房东不退押金": "退房后房东一直扣着押金，说房间有损坏，我想拿回押金。",
    "商家关门不退款": "健身房关门了，我的会员卡还有余额，想知道怎样退款。",
    "收到刑事拘留通知": "家人被刑事拘留，今天收到了通知书，我们现在该准备什么、找谁处理？",
}

CASE_PHASES = ("事实梳理", "证据核对", "法源分析", "行动方案")

ACTION_PHASES = {
    LegalAction.ASK_FACT: "事实梳理",
    LegalAction.REQUEST_EVIDENCE: "证据核对",
    LegalAction.SEARCH_LAW: "法源分析",
    LegalAction.SEARCH_CASE: "法源分析",
    LegalAction.VERIFY: "法源分析",
    LegalAction.SIMULATE_OPPONENT: "行动方案",
    LegalAction.CALCULATE: "行动方案",
    LegalAction.GENERATE_DOCUMENT: "行动方案",
    LegalAction.STOP: "行动方案",
    LegalAction.ESCALATE_HUMAN: "行动方案",
}


def _initialize() -> None:
    defaults = {
        "thread_id": f"case_{uuid4().hex}",
        "case_state": None,
        "messages": [],
        "last_error": None,
        "ui_intro_seen": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    if st.session_state.case_state is not None:
        state = CaseState.from_value(st.session_state.case_state)
        legacy_state = state.evidence_parser_version < CURRENT_EVIDENCE_PARSER_VERSION
        refresh_stored_evidence(state, _upload_root())
        if legacy_state and state.pending_evidence_requests and state.case_type == "labor_dispute":
            latest_user_text = next(
                (
                    str(item.get("content", ""))
                    for item in reversed(st.session_state.messages)
                    if item.get("role") == "user"
                ),
                "",
            )
            if latest_user_text:
                extract_labor_facts(latest_user_text, state, enable_semantic=False)
                if state.evidence_collection_exhausted:
                    state.pending_evidence_requests = []
        st.session_state.case_state = state


def _reset() -> None:
    st.session_state.thread_id = f"case_{uuid4().hex}"
    st.session_state.case_state = None
    st.session_state.messages = []
    st.session_state.last_error = None


def _upload_root() -> Path:
    configured = Path(LEXPILOT_UPLOAD_DIR)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parent / configured


def _action_label(action: LegalAction | None) -> str:
    if action is None:
        return "等待案件描述"
    return ACTION_LABELS.get(action, action.name)


def _case_phase(state: CaseState | None) -> str:
    if state is None or state.current_action is None:
        return CASE_PHASES[0]
    return ACTION_PHASES.get(state.current_action, CASE_PHASES[0])


def _render_case_path(state: CaseState | None) -> None:
    active_phase = _case_phase(state)
    with st.container(key="case_path"):
        st.caption("事实梳理 → 证据核对 → 法源分析 → 行动方案")
        with st.container(horizontal=True, gap="small"):
            for phase in CASE_PHASES:
                st.badge(
                    phase,
                    icon=":material/check_circle:" if phase == active_phase else None,
                    color="primary" if phase == active_phase else "gray",
                )


def _run_message(message: str, files: list[UploadedFile] | None = None) -> None:
    uploads = list(files or [])
    display_content = message.strip() or f"上传了 {len(uploads)} 份案件材料。"
    user_message_added = False
    try:
        prior = CaseState.from_value(st.session_state.case_state)
        if message.strip():
            route_case(message.strip(), prior)
        ingestion = ingest_evidence_files(
            prior,
            [
                UploadPayload(
                    name=uploaded.name,
                    data=uploaded.getvalue(),
                    media_type=getattr(uploaded, "type", "") or "application/octet-stream",
                )
                for uploaded in uploads
            ],
            _upload_root(),
        )
        attachments = [
            {**record.model_dump(mode="json"), "stored_path": record.stored_path}
            for record in ingestion.files
        ]
        st.session_state.messages.append(
            {"role": "user", "content": display_content, "attachments": attachments}
        )
        user_message_added = True
        st.session_state.case_state = prior

        engine_message = message.strip() or "我已上传系统刚才要求的案件证据材料。"
        result = invoke_lexpilot(engine_message, st.session_state.thread_id, prior)
        state: CaseState = result["case_state"]
        st.session_state.case_state = state
        reply = result["reply"]
        if uploads:
            reply = f"{ingestion.summary_markdown()}\n\n{reply}"
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.session_state.last_error = None
    except Exception as exc:
        if not user_message_added:
            st.session_state.messages.append(
                {
                    "role": "user",
                    "content": display_content,
                    "attachments": [
                        {"original_name": item.name, "size_bytes": item.size, "rejected": True}
                        for item in uploads
                    ],
                }
            )
        error = f"{type(exc).__name__}: {exc}"
        st.session_state.last_error = error
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "这一轮没有处理成功，之前的案件信息仍然保留。请稍后重试。",
            }
        )


def _render_attachment(attachment: dict, message_index: int) -> None:
    name = attachment.get("original_name", "未命名文件")
    size_bytes = int(attachment.get("size_bytes", 0))
    size_text = (
        f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024 * 1024
        else f"{size_bytes / 1024 / 1024:.1f} MB"
    )
    if attachment.get("rejected"):
        st.caption(f":material/error: {name} · {size_text} · 未接收")
        return

    labels = "、".join(attachment.get("evidence_names", [])) or "待人工分类"
    raw_status = attachment.get("extraction_status", FileExtractionStatus.FAILED.value)
    try:
        status = FileExtractionStatus(raw_status)
    except ValueError:
        status = FileExtractionStatus.FAILED
    status_label = EXTRACTION_LABELS[status][0]
    fact_count = len(attachment.get("extracted_facts", []))
    fact_suffix = f" · 已识别 {fact_count} 项关键事实" if fact_count else ""
    st.caption(f":material/attach_file: {name} · {size_text} · {labels} · {status_label}{fact_suffix}")
    stored_path = Path(attachment.get("stored_path", ""))
    if not stored_path.is_file():
        return
    if attachment.get("extension") in {".png", ".jpg", ".jpeg", ".webp"}:
        st.image(str(stored_path), caption=name, width="stretch")
    st.download_button(
        "下载原始材料",
        data=stored_path.read_bytes(),
        file_name=name,
        mime=attachment.get("media_type", "application/octet-stream"),
        key=f"download_{message_index}_{attachment.get('file_id', name)}",
        icon=":material/download:",
        type="tertiary",
        on_click="ignore",
    )


def _render_chat() -> str | None:
    st.subheader("案件对话", icon=":material/forum:")
    st.caption("先说最困扰你的事，再一起整理事实与证据；随时可以说“先给我方案”或“不清楚”。")

    selected_prompt: str | None = None
    if not st.session_state.messages:
        with st.container(border=True, gap="small"):
            st.markdown("#### 从一段事实开始")
            st.write("不用整理成法律语言，按事情发生的顺序描述即可。")
            selected = st.pills(
                "常见情形",
                list(SUGGESTIONS),
                key="starter_suggestion",
                label_visibility="collapsed",
                wrap=True,
            )
            if selected:
                selected_prompt = SUGGESTIONS[selected]
            st.caption(":material/lock: 上传的案件材料默认仅保存在本机。")

    for message_index, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            for attachment in message.get("attachments", []):
                _render_attachment(attachment, message_index)

    st.caption(":material/attach_file: 可附加合同、转账、聊天、通知书、病历等材料；原件请自行保留。")
    user_input: ChatInputValue | str | None = st.chat_input(
        "描述情况、回答追问，或附加案件材料……",
        key="case_chat_input",
        accept_file="multiple",
        file_type=STREAMLIT_FILE_TYPES,
        max_upload_size=MAX_FILE_BYTES // 1024 // 1024,
        submit_mode="disable",
    )
    if selected_prompt:
        return selected_prompt
    if user_input is None:
        return None
    if isinstance(user_input, str):
        with st.status(":shimmer[正在理解你的情况……]", type="compact") as status:
            _run_message(user_input)
            status.update(label="已整理这轮信息", state="complete")
    else:
        with st.status(":shimmer[正在理解你的情况……]", type="compact") as status:
            _run_message(user_input.text, list(user_input.files))
            status.update(label="已整理这轮信息", state="complete")
    st.rerun()
    return None


def _render_progress(state: CaseState) -> None:
    columns = st.columns(3, gap="small")
    if state.case_type != "labor_dispute":
        for column, label, value in zip(columns, ("已记事实", "上传材料", "规则线索"), (len(state.facts), len(state.uploaded_files), len(state.retrieved_laws)), strict=True):
            column.metric(label, str(value), border=True)
        st.caption("数量用于查看整理进展，不代表证据已获认可或案件胜算。")
        return
    metrics = (
        ("事实", state.fact_completeness),
        ("证据", state.evidence_completeness),
        ("法源", state.legal_confidence),
    )
    for column, (label, value) in zip(columns, metrics, strict=True):
        column.metric(label, f"{value:.0%}", border=True)


def _render_evidence_gap(gap) -> None:
    label, color, icon = EVIDENCE_LABELS[gap.status]
    with st.container(border=True, gap=None):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{gap.name}**")
            st.badge(label, color=color, icon=icon)
        if "暂无法提供" in gap.reason:
            st.caption("暂无法提供；报告中已列出替代取证办法。")
        elif gap.status != EvidenceStatus.PROVEN and gap.missing_evidence:
            st.caption("可补充：" + "、".join(gap.missing_evidence[:3]))
        elif gap.reason:
            st.caption(gap.reason)


def _render_reasoning_graph(state: CaseState) -> None:
    paths = state.reasoning_graph.paths
    if not paths:
        st.caption("完成事实梳理后，这里会形成事实—证据—法条推理链。")
        return
    with st.expander("查看可验证推理链", icon=":material/account_tree:"):
        for path in sorted(paths, key=lambda item: item.support_score, reverse=True):
            label, color, icon = EVIDENCE_LABELS[path.status]
            with st.container(border=True, gap="small"):
                with st.container(horizontal=True, vertical_alignment="center"):
                    st.markdown(f"**{path.element_name}**")
                    st.badge(label, color=color, icon=icon)
                    st.caption(f"支持度 {path.support_score:.0%}")
                st.caption(path.explanation)
                if path.evidence_names:
                    st.caption("关联证据：" + "、".join(path.evidence_names))
                if path.law_ids:
                    st.caption("关联法源：" + "、".join(path.law_ids))


def _render_uploaded_file(item) -> None:
    label, color = EXTRACTION_LABELS[item.extraction_status]
    with st.container(border=True, gap="small"):
        st.markdown(f"**:material/description: {item.original_name}**")
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(label, color=color)
            if item.evidence_names:
                st.caption("归类为：" + "、".join(item.evidence_names))
        if item.extracted_facts:
            st.caption("从正文识别：" + "、".join(item.extracted_facts))
        if item.notes:
            st.caption(item.notes)
        if item.text_preview:
            with st.expander("查看文字摘要", icon=":material/subject:"):
                st.write(item.text_preview)
        stored_path = Path(item.stored_path)
        if stored_path.is_file():
            st.download_button(
                "下载原文件",
                data=stored_path.read_bytes(),
                file_name=item.original_name,
                mime=item.media_type,
                key=f"evidence_download_{item.file_id}",
                icon=":material/download:",
                type="tertiary",
                on_click="ignore",
            )


def _report_markdown(state: CaseState) -> str:
    return report_markdown(state)


def _render_report(state: CaseState) -> None:
    report = state.final_report
    if not report:
        st.caption("可以随时点击“生成当前方案”；材料不全时先形成阶段步骤，补充后继续更新。")
        return

    st.markdown("#### 案情摘要")
    st.write(report.get("case_summary", ""))

    verification = report.get("verification", {})
    if report.get("generation_status") == "VERIFIED":
        st.success("事实、证据、法源和引用已通过生成前核验。", icon=":material/verified:")
    else:
        st.warning(
            verification.get("refusal_reason", "当前材料不足，系统未生成确定性结论。"),
            icon=":material/gpp_maybe:",
        )

    issues = report.get("legal_issues", [])
    if issues:
        st.markdown("#### 主要法律问题")
        for issue in issues:
            st.markdown(f"- {issue}")

    findings = report.get("grounded_findings", [])
    if findings:
        st.markdown("#### 可验证分析")
        for finding in findings:
            status = "已有支持" if finding.get("support_status") == "SUPPORTED" else "部分支持"
            with st.container(border=True, gap="small"):
                st.write(finding.get("text", ""))
                st.caption(
                    f"{status} · 要件 {len(finding.get('element_ids', []))} 项 · "
                    f"法源 {len(finding.get('law_ids', []))} 项"
                )

    estimate = report.get("compensation_estimate", {})
    if estimate.get("amount") is not None:
        st.metric("当前金额测算", f"¥{float(estimate['amount']):,.2f}", border=True)
        if estimate.get("formula"):
            st.caption("计算方式：" + estimate["formula"])
        st.caption(estimate.get("message", "仅为当前信息下的估算。"))

    recommendations = report.get("recommended_actions", [])
    if recommendations and not report.get("action_plan"):
        st.markdown("#### 建议行动")
        for index, item in enumerate(recommendations, start=1):
            st.markdown(f"{index}. {item}")

    laws = report.get("legal_basis", [])
    if laws:
        with st.expander("查看法律规则与适用条件", icon=":material/gavel:"):
            for law in laws:
                title = f"{law.get('law_name', '')}{law.get('article', '')}"
                source = law.get("source_url", "")
                st.markdown(f"**[{title}]({source})**" if source else f"**{title}**")
                st.caption(law.get("summary", ""))
                if law.get("applicability"):
                    st.caption(law["applicability"])

    render_plan_sections(state)
    st.download_button(
        "下载阶段报告",
        data=_report_markdown(state),
        file_name=f"LexPilot_{state.case_id}_阶段报告.md",
        mime="text/markdown",
        key="download_case_report",
        icon=":material/download:",
        type="primary",
        width="stretch",
        on_click="ignore",
    )
    st.caption(report.get("disclaimer", ""))


def _render_case_workspace(state: CaseState | None) -> None:
    st.subheader("案件档案", icon=":material/folder_open:")
    if state is None:
        with st.container(border=True):
            st.markdown("#### 系统会怎样协助你")
            st.markdown("1. **梳理事实** · 每次只追问最关键的信息")
            st.markdown("2. **核对证据** · 可直接上传合同、流水和截图")
            st.markdown("3. **分析选择** · 核对依据，比较处理路径和成本")
            st.markdown("4. **落实步骤** · 说明找谁办、带什么、如何推进")
        st.info(
            "支持劳动、婚姻、借贷、房产、消费、合同、公司、知识产权、继承、交通、医疗、侵权、刑事、行政及执行咨询。先确认地区，再核对适用法律。",
            icon=":material/info:",
        )
        return

    action = _action_label(state.current_action)
    with st.container(border=True, gap="small"):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge("案件进行中" if not state.done else "阶段完成", color="primary")
            st.caption(f"已完成 {state.step_count} 个处理步骤")
        st.caption(f"当前阶段 · {_case_phase(state)}")
        st.markdown(f"### {action}")
        st.caption(state.current_reason or "系统正在根据现有信息安排下一步。")

    if st.button("生成当前方案", key="generate_current_plan", icon=":material/checklist:", width="stretch"):
        with st.status("正在整理现有事实和实施步骤……", type="compact"):
            _run_message("请按现有事实和材料给我一份详细的实施方案，写清具体步骤、证据、办理渠道和不顺利时怎么办。")
        st.rerun()

    overview_tab, evidence_tab, report_tab = st.tabs(
        [":material/monitoring: 概览", ":material/inventory_2: 材料", ":material/article: 报告"]
    )
    with overview_tab:
        render_dossier(state)
        _render_progress(state)
        st.markdown("#### 证据要点")
        gaps = sorted(
            state.evidence_gaps,
            key=lambda gap: {
                EvidenceStatus.CONFLICT: 0,
                EvidenceStatus.MISSING: 1,
                EvidenceStatus.PARTIAL: 2,
                EvidenceStatus.PROVEN: 3,
            }[gap.status],
        )
        if not gaps:
            st.caption("描述案件后，这里会显示证据缺口。")
        for gap in gaps[:5]:
            _render_evidence_gap(gap)
        if state.case_type == "labor_dispute":
            _render_reasoning_graph(state)
        if state.inquiry_candidates and state.pending_fact_ids:
            selected = next(
                (item for item in state.inquiry_candidates if item.fact_id == state.pending_fact_ids[0]),
                None,
            )
            if selected:
                with st.expander("为什么先问这个问题", icon=":material/psychology:"):
                    st.write(selected.reason)
                    st.progress(selected.score, text=f"问题价值评分 · {selected.score:.0%}")
        if state.action_history:
            with st.expander("查看处理记录", icon=":material/history:"):
                for record in reversed(state.action_history):
                    st.markdown(f"**{record.step}. {_action_label(record.action)}**")
                    st.caption(record.result)

    with evidence_tab:
        if state.pending_evidence_requests:
            st.markdown("#### 当前建议补充")
            for request in state.pending_evidence_requests:
                st.markdown(f"- {request}")
        if state.unavailable_evidence:
            st.markdown("#### 已确认暂时无法提供")
            for name in state.unavailable_evidence:
                st.markdown(f"- {name}")
        if not state.uploaded_files:
            st.caption("尚未上传材料。点击对话输入框旁的附件按钮即可添加。")
        else:
            st.caption(f"已登记 {len(state.uploaded_files)} 份案件材料")
            for item in state.uploaded_files:
                _render_uploaded_file(item)

    with report_tab:
        _render_report(state)


def _render_sidebar(*, intro_seen: bool) -> None:
    with st.sidebar:
        with st.container(key=sidebar_shell_key(intro_seen=intro_seen)):
            with st.container(key="sidebar_brand_block"):
                render_brand()

            with st.container(key="sidebar_case_controls"):
                if st.button(
                    "新建案件",
                    key="new_case",
                    icon=":material/add:",
                    type="primary",
                    width="stretch",
                ):
                    _reset()
                    st.rerun()

                short_id = st.session_state.thread_id.removeprefix("labor_").removeprefix("case_")[:10]
                st.caption(f"当前案件 · `{short_id}`")
                st.space("small")

            with st.container(key="sidebar_reference_blocks"):
                with st.expander("可以咨询哪些问题", icon=":material/checklist:"):
                    st.markdown(
                        "- 劳动用工、婚姻家庭与继承\n"
                        "- 借贷欠款、合同交易与消费退款\n"
                        "- 房产租赁、侵权、交通与医疗\n"
                        "- 公司股权与知识产权\n"
                        "- 刑事、行政争议与诉讼执行\n"
                        "- 其他问题可直接描述，由综合接谈进一步分类"
                    )
                    st.caption("不将问题强行归入某一领域；涉及多个法律关系时分别核对。")

                with st.expander("材料与隐私", icon=":material/shield_lock:"):
                    st.write("支持 PDF、Word、图片、表格及纯文本，单个文件不超过 15 MB。")
                    st.caption("原始附件默认只保存在本机，不会自动发送到外部服务；聊天文本会先脱敏再进行结构化分析。")

            with st.container(key="sidebar_trust_block"):
                st.caption(":material/account_tree: 处理过程可追溯，结论需经证据与法源核验。")
                st.caption(":material/gavel: AI 法律咨询与行动辅助工具；重要结论须结合证据、有效法源和当地实践核实。")


def main() -> None:
    _initialize()
    render_motion_styles()
    _render_sidebar(intro_seen=st.session_state.ui_intro_seen)

    shell_key = experience_shell_key(intro_seen=st.session_state.ui_intro_seen)
    with st.container(key=shell_key):
        with st.container(key="hero_stage"):
            hero_copy, hero_visual = st.columns(
                [1.3, 1],
                gap="large",
                vertical_alignment="center",
            )
            with hero_copy:
                with st.container(key="hero_copy"):
                    st.title("把法律难题，变成能落实的下一步", icon=":material/balance:")
                    st.caption("从你的真实处境出发，理清事实、整理证据、分析选择，把每一步怎么做说清楚。")
            with hero_visual:
                with st.container(key="hero_visual"):
                    render_evidence_constellation(
                        _case_phase(st.session_state.case_state),
                        intro=not st.session_state.ui_intro_seen,
                    )
        _render_case_path(st.session_state.case_state)
        st.space("small")

        if st.session_state.last_error:
            st.error(
                "本轮处理未完成。请原样重新发送上一条消息。",
                icon=":material/error:",
            )
            with st.expander("查看技术详情", icon=":material/code:"):
                st.code(st.session_state.last_error)
                st.caption("先前已保存的对话和案件状态没有被覆盖。")

        conversation, workspace = st.columns([1.55, 1], gap="large")
        with conversation:
            selected_prompt = _render_chat()
        with workspace:
            _render_case_workspace(st.session_state.case_state)

        if selected_prompt:
            with st.status(":shimmer[正在建立案件档案……]", type="compact") as status:
                _run_message(selected_prompt)
                status.update(label="案件档案已建立", state="complete")
            st.rerun()

    st.session_state.ui_intro_seen = True


if __name__ == "__main__":
    main()
