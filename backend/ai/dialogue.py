"""Validation helpers for AI-written conversational transitions."""

from __future__ import annotations

import re

FORBIDDEN_WORDING = (
    "为判断案件",
    "补充一个关键事实",
    "作为AI",
    "作为人工智能",
    "Gemini",
    "Qwen",
    "通义千问",
    "大语言模型",
    "系统提示",
)


def sanitize_transition(value: str) -> str:
    """Accept only a short bridge with no provider disclosure or question."""

    transition = str(value or "").strip().strip('"“”')
    transition = " ".join(transition.split())
    if not 2 <= len(transition) <= 45:
        return ""
    if any(word.lower() in transition.lower() for word in FORBIDDEN_WORDING):
        return ""
    if any(mark in transition for mark in ("?", "？")):
        return ""
    if not transition.endswith(("。", "！", "，", "：")):
        transition += "。"
    return transition


def redact_sensitive_text(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已脱敏]", value)
    value = re.sub(r"(?<!\d)\d{17}[0-9Xx](?!\d)", "[身份证号已脱敏]", value)
    value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[邮箱已脱敏]", value)
    value = re.sub(r"(?<!\d)\d{16,19}(?!\d)", "[账号已脱敏]", value)
    return value
