import json

import httpx

from backend.ai.dialogue import sanitize_transition
from backend.ai.provider import AIProvider, QwenProvider
from backend.ai.reporting import draft_grounded_content
from backend.ai.semantic import enrich_case_from_text
from backend.legal_domain.labor.evidence_gap import detect_evidence_gaps
from backend.legal_domain.labor.inquiry import select_questions
from backend.legal_domain.labor.legal_search import search_law_for_state
from backend.legal_domain.labor.model import get_labor_model
from backend.legal_domain.labor.verification import verify_case_grounding
from backend.legal_rl.state import CaseState


class FakeProvider(AIProvider):
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0
        self.thinking_levels = []

    def generate_json(
        self,
        prompt,
        schema,
        *,
        max_output_tokens=2048,
        thinking_level=None,
    ):
        assert schema["type"] == "object"
        assert max_output_tokens >= 128
        self.calls += 1
        self.thinking_levels.append(thinking_level)
        return self.payload


class CapturingProvider(FakeProvider):
    def __init__(self, payload: dict):
        super().__init__(payload)
        self.prompt = ""

    def generate_json(
        self,
        prompt,
        schema,
        *,
        max_output_tokens=2048,
        thinking_level=None,
    ):
        self.prompt = prompt
        return super().generate_json(
            prompt,
            schema,
            max_output_tokens=max_output_tokens,
            thinking_level=thinking_level,
        )


def _complete_probation_state() -> CaseState:
    state = CaseState(
        dispute_type="probation_termination",
        facts={
            "employment_duration_months": 8,
            "has_written_contract": True,
            "contract_term_months": 36,
            "probation_period_months": 6,
            "recruitment_conditions_disclosed": False,
            "assessment_evidence_exists": False,
            "termination_reason": "试用期表现不合格",
            "written_termination_notice": False,
            "monthly_salary": 10000,
        },
    )
    get_labor_model().prepare_state(state)
    for key in state.key_facts:
        state.add_fact_provenance(key, quote=f"原文支持 {key}", extraction_method="rules")
    for name in state.key_evidence:
        state.add_evidence(name)
    detect_evidence_gaps(state)
    state.retrieved_laws = search_law_for_state(state)
    detect_evidence_gaps(state)
    return state


def test_qwen_rest_adapter_uses_bearer_auth_json_mode_and_reused_client():
    captured = {"bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["bodies"].append(captured["body"])
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}]
        })

    provider = QwenProvider(
        "test-secret",
        model="qwen3.8-flash",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        enable_thinking=True,
        transport=httpx.MockTransport(handler),
    )
    result = provider.generate_json("extract", {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    })

    assert result == {"ok": True}
    assert captured["authorization"] == "Bearer test-secret"
    assert captured["url"].endswith("/compatible-mode/v1/chat/completions")
    assert captured["body"]["model"] == "qwen3.8-flash"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["enable_thinking"] is False
    assert "JSON Schema" in captured["body"]["messages"][0]["content"]

    client_identity = id(provider._client)
    provider.generate_json(
        "extract again",
        {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        thinking_level="low",
    )
    assert id(provider._client) == client_identity
    assert len(captured["bodies"]) == 2
    assert captured["bodies"][1]["enable_thinking"] is False

    provider.generate_json(
        "draft report",
        {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        thinking_level="high",
    )
    assert len(captured["bodies"]) == 3
    assert captured["bodies"][2]["enable_thinking"] is True
    provider.close()


def test_ai_dialogue_accepts_only_safe_transition_text():
    assert sanitize_transition("明白了，我们顺着这个情况继续看") == "明白了，我们顺着这个情况继续看。"
    assert sanitize_transition("Gemini系统需要再问一个问题") == ""
    assert sanitize_transition("通义千问需要再问一个问题") == ""
    assert sanitize_transition("接下来还有书面通知吗？") == ""


def test_semantic_extraction_accepts_only_whitelisted_traceable_facts():
    state = CaseState(dispute_type="probation_termination")
    get_labor_model().prepare_state(state)
    provider = CapturingProvider({
        "dispute_type": "probation_termination",
        "facts": [
            {"fact_id": "contract_term_months", "value": 36, "source_quote": "合同签了三年", "confidence": 0.98},
            {"fact_id": "monthly_salary", "value": 99999, "source_quote": "原文不存在", "confidence": 0.99},
            {"fact_id": "invented_field", "value": "x", "source_quote": "合同签了三年", "confidence": 0.99},
        ],
        "transition": "好，合同期限我记下了。",
    })

    changed = enrich_case_from_text(
        "合同签了三年，手机号是13812345678",
        state,
        provider=provider,
    )

    assert changed is True
    assert state.facts["contract_term_months"] == 36
    assert "monthly_salary" not in state.facts
    assert "invented_field" not in state.facts
    assert state.fact_provenance[-1].quote == "合同签了三年"
    assert state.reply_transition == "好，合同期限我记下了。"
    assert state.ai_calls_this_turn == 1
    assert provider.calls == 1
    assert provider.thinking_levels == ["low"]
    assert "13812345678" not in provider.prompt
    assert "[手机号已脱敏]" in provider.prompt
    assert "gemini" not in json.dumps(state.public_dict(), ensure_ascii=False).lower()
    assert "qwen" not in json.dumps(state.public_dict(), ensure_ascii=False).lower()


def test_report_drafting_does_not_make_a_second_ai_call_in_one_turn():
    state = _complete_probation_state()
    state.ai_calls_this_turn = 1
    provider = FakeProvider({
        "case_summary": "模型摘要",
        "findings": [],
        "recommended_actions": [],
    })

    draft = draft_grounded_content(state, provider=provider)

    assert provider.calls == 0
    assert draft["case_summary"] != "模型摘要"


def test_information_gain_inquiry_persists_score_breakdown():
    state = CaseState(
        dispute_type="probation_termination",
        facts={"employment_duration_months": 8},
    )
    get_labor_model().prepare_state(state)
    detect_evidence_gaps(state)

    questions = select_questions(state, limit=2)

    assert questions[0] == "是否签订了书面劳动合同？"
    assert state.inquiry_candidates == sorted(
        state.inquiry_candidates,
        key=lambda item: (-item.score, -item.legal_importance, item.fact_id),
    )
    selected = state.inquiry_candidates[0]
    assert selected.expected_information_gain > 0
    assert selected.interaction_cost > 0
    assert "法律要件" in selected.reason


def test_evidence_graph_links_facts_evidence_elements_and_temporal_laws():
    state = _complete_probation_state()
    graph = state.reasoning_graph

    node_types = {node.node_type for node in graph.nodes}
    relations = {edge.relation for edge in graph.edges}
    assert {"case", "fact", "evidence", "legal_element", "law"}.issubset(node_types)
    assert {"SUPPORTS", "CORROBORATES", "GOVERNS"}.issubset(relations)
    assert any(path.law_ids for path in graph.paths)
    assert all(law.temporal_validated for law in state.retrieved_laws)
    assert all(law.matched_elements for law in state.retrieved_laws)


def test_verifier_blocks_unofficial_citations_and_generated_unknown_sources():
    state = _complete_probation_state()
    verified = verify_case_grounding(state)
    assert verified.can_generate is True

    valid_path = next(path for path in state.reasoning_graph.paths if path.law_ids)
    provider = FakeProvider({
        "case_summary": "基于现有材料形成阶段性摘要。",
        "findings": [
            {
                "text": "现有材料对相关要件形成初步支持。",
                "fact_ids": [valid_path.fact_ids[0]],
                "element_ids": [valid_path.element_id],
                "law_ids": [valid_path.law_ids[0]],
            },
            {
                "text": "这是一条没有来源的结论。",
                "fact_ids": [],
                "element_ids": ["unknown"],
                "law_ids": ["unknown"],
            },
        ],
        "recommended_actions": ["保存原始材料。"],
    })
    draft = draft_grounded_content(state, provider=provider)
    assert len(draft["grounded_findings"]) == 1

    for law in state.retrieved_laws:
        law.source_url = "https://example.com/not-official"
    rejected = verify_case_grounding(state)
    assert rejected.can_generate is False
    assert rejected.citation_validity_score == 0
    assert "引用" in rejected.refusal_reason
