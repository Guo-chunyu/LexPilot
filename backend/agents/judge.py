"""Judge Agent for both legacy answer QA and LexPilot state verification."""
import json, re
from typing import Any

try:  # Legacy LLM judge is optional for the offline decision core.
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover - exercised only in minimal installs
    HumanMessage = None
    ChatOpenAI = Any
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, JUDGE_PASS_THRESHOLD
from backend.legal_rl.state import CaseState, EvidenceStatus, JudgeResult
from backend.legal_domain.labor.verification import verify_case_grounding

JUDGE_PROMPT = """# ROLE: Legal AI Quality Inspector
Review the answer against the reference context. Output JSON.

Checks:
1. Statute Accuracy (40%): Does each legal claim match the reference context?
2. No Scope Creep (30%): Does it cite ONLY Company Law?
3. Logical Completeness (30%): Are key conditions or exceptions missed?

Output JSON format:
{{
  "passed": true/false,
  "score": 0-100,
  "issues": ["issue description"],
  "suggestion": "improvement direction if not passed"
}}

[Reference Context]:
{context}

[Answer]:
{answer}"""

# Phrases indicating a legitimate system refusal - judge should pass immediately
REFUSAL_PHRASES = [
    "beyond Company Law", "beyond my professional scope",
    "超出专业范围", "法条库未涵盖", "不涵盖",
    "sorry, my knowledge base",
]


def judge_node(state: dict, llm: ChatOpenAI | None = None) -> dict:
    if state.get("intent", "") != "LEGAL":
        return {"judge_pass": True, "judge_feedback": ""}

    if llm is None:
        llm = ChatOpenAI(model=DEEPSEEK_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, temperature=0)

    messages = state.get("messages", [])
    answer = messages[-1].content if messages else ""
    context = state.get("context", [])

    # Quick pass: legitimate refusal is always correct behavior
    for phrase in REFUSAL_PHRASES:
        if phrase.lower() in answer.lower():
            print("  [Judge] PASS (legitimate refusal)")
            return {"judge_pass": True, "judge_feedback": ""}

    prompt_text = JUDGE_PROMPT.format(
        context="\n".join(context) if context else "No reference context",
        answer=answer[:3000],
    )

    try:
        resp = llm.invoke([HumanMessage(content=prompt_text)])
        json_str = resp.content.strip()
        if json_str.startswith("```"):
            json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
            json_str = re.sub(r"\s*```$", "", json_str)
        verdict_data = json.loads(json_str)
    except (json.JSONDecodeError, Exception) as e:
        print(f"  [!] Judge parse failed: {str(e)[:80]}, default pass")
        return {"judge_pass": True, "judge_feedback": ""}

    passed = verdict_data.get("passed", True)
    score = verdict_data.get("score", 100)
    issues = verdict_data.get("issues", [])
    suggestion = verdict_data.get("suggestion", "")

    if not passed or score < JUDGE_PASS_THRESHOLD:
        print(f"  [Judge] FAIL (score={score}): {issues}")
        return {"judge_pass": False, "judge_feedback": suggestion or "; ".join(issues)}

    print(f"  [Judge] PASS (score={score})")
    return {"judge_pass": True, "judge_feedback": ""}


def evaluate_case_state(state: CaseState) -> JudgeResult:
    """Deterministically decide whether the sequential investigation may stop."""

    verification = verify_case_grounding(state)
    fact_score = state.fact_completeness
    evidence_score = state.evidence_completeness
    legal_score = state.legal_confidence
    citation_score = verification.citation_validity_score
    severe = [
        gap for gap in state.evidence_gaps
        if gap.status in {EvidenceStatus.MISSING, EvidenceStatus.CONFLICT}
    ]
    overall = round(
        0.30 * fact_score
        + 0.30 * evidence_score
        + 0.25 * legal_score
        + 0.15 * citation_score
        - 0.15 * state.contradiction_score,
        4,
    )
    overall = max(0.0, min(overall, 1.0))
    can_stop = (
        fact_score >= 0.70
        and evidence_score >= 0.45
        and legal_score >= 0.80
        and citation_score >= 0.80
        and bool(state.opponent_analysis)
        and verification.can_generate
        and not any(gap.status == EvidenceStatus.CONFLICT for gap in severe)
    )
    if can_stop:
        reason = "关键事实、证据、法源和对方抗辩已达到生成阶段性行动方案的门槛。"
    elif fact_score < 0.70:
        reason = "关键事实仍不充分。"
    elif evidence_score < 0.45:
        reason = "核心证据链仍不充分。"
    elif not state.retrieved_laws:
        reason = "尚未检索并核验可追溯法源。"
    elif not state.opponent_analysis:
        reason = "尚未模拟对方抗辩。"
    elif not verification.can_generate:
        reason = verification.refusal_reason
    else:
        reason = "仍存在严重缺失或冲突，不允许停止调查。"
    result = JudgeResult(
        fact_score=fact_score,
        evidence_score=evidence_score,
        legal_score=legal_score,
        citation_score=citation_score,
        overall_confidence=overall,
        can_stop=can_stop,
        reason=reason,
    )
    state.judge_result = result
    state.overall_confidence = overall
    return result
