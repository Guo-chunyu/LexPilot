from __future__ import annotations

import pytest

from backend.ai.provider import AIProviderError
from backend.legal_rl.state import CaseState


class StubProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_json(self, prompt, schema, *, max_output_tokens=2048, thinking_level=None):
        self.calls.append({
            "prompt": prompt,
            "schema": schema,
            "max_output_tokens": max_output_tokens,
            "thinking_level": thinking_level,
        })
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _state() -> CaseState:
    state = CaseState(case_type="debt")
    state.user_narrative = "朋友借了我4万元，只有转账和微信聊天，现在不还。"
    state.facts = {
        "amount": "4万元",
        "goal": "追回借款",
        "location": "深圳",
        "parties": "我是出借人，对方是朋友",
    }
    state.pending_fact_ids = ["event_time"]
    state.pending_questions = ["借款是什么时候发生的？"]
    state.consultation.evidence_tasks = []
    state.consultation.urgent_actions = []
    return state


def test_online_reply_requires_a_configured_provider():
    from backend.ai.online_reply import OnlineModelUnavailableError, compose_online_reply

    with pytest.raises(OnlineModelUnavailableError):
        compose_online_reply("请继续", _state(), "模板化离线回复", provider=None)


def test_online_reply_uses_case_context_and_rejects_template_transitions():
    from backend.ai.online_reply import compose_online_reply

    provider = StubProvider([{
        "reply": "你提到的4万元借款目前缺少发生时间，这会影响到期和后续处理的判断。请告诉我大概是什么时候转出的？",
        "asked_fact_ids": ["event_time"],
    }])

    reply = compose_online_reply("请继续", _state(), "**先处理紧急事项**\n你现在最希望得到什么结果？", provider=provider)

    assert "4万元" in reply
    assert "**先处理紧急事项**" not in reply
    assert "你现在最希望得到什么结果" not in reply
    assert len(provider.calls) == 1
    assert "朋友借了我4万元" in provider.calls[0]["prompt"]
    assert "追回借款" in provider.calls[0]["prompt"]


def test_online_reply_retries_once_with_validation_feedback():
    from backend.ai.online_reply import compose_online_reply

    provider = StubProvider([
        {"reply": "我先和你一起把情况理清。", "asked_fact_ids": ["amount"]},
        {
            "reply": "你已经说明金额是4万元。现在还缺借款发生时间，请告诉我大概是哪一天或哪一月。",
            "asked_fact_ids": ["event_time"],
        },
    ])

    reply = compose_online_reply("请继续", _state(), "原始回复", provider=provider)

    assert "4万元" in reply
    assert len(provider.calls) == 2
    assert "校验反馈" in provider.calls[1]["prompt"]


def test_online_reply_rejects_law_articles_not_present_in_context():
    from backend.ai.online_reply import compose_online_reply

    provider = StubProvider([
        {
            "reply": "4万元借款适用《某法》第九百九十九条，请告诉我发生时间。",
            "asked_fact_ids": ["event_time"],
        },
        {
            "reply": "你已经说明借款金额是4万元。现在只需确认大概发生时间，这会影响到期和处理路径。",
            "asked_fact_ids": ["event_time"],
        },
    ])

    reply = compose_online_reply("请继续", _state(), "原始回复", provider=provider)

    assert "九百九十九" not in reply
    assert len(provider.calls) == 2


def test_online_reply_does_not_fallback_after_upstream_failure():
    from backend.ai.online_reply import OnlineModelUnavailableError, compose_online_reply

    provider = StubProvider([AIProviderError("upstream")])

    with pytest.raises(OnlineModelUnavailableError):
        compose_online_reply("请继续", _state(), "原始离线回复", provider=provider)


def test_online_reply_preserves_upstream_error_classification():
    from backend.ai.online_reply import OnlineModelUnavailableError, compose_online_reply

    provider = StubProvider([
        AIProviderError("bad key", code="authentication_failed"),
    ])

    with pytest.raises(OnlineModelUnavailableError) as caught:
        compose_online_reply("请继续", _state(), "原始离线回复", provider=provider)

    assert caught.value.code == "authentication_failed"


def test_graph_routes_every_user_facing_reply_through_online_composer(monkeypatch):
    import backend.graph as graph

    state = _state()

    class FakeApp:
        def invoke(self, payload, config):
            return {
                "case_state": state,
                "reply": "规则层模板草案",
                "requires_user": True,
            }

    captured = {}

    def fake_compose(message, case, raw_reply):
        captured.update({"message": message, "case": case, "raw_reply": raw_reply})
        return "在线个案回复"

    monkeypatch.setattr(graph, "app", FakeApp())
    monkeypatch.setattr(graph, "compose_online_reply", fake_compose, raising=False)

    result = graph.invoke_lexpilot("请继续", "online-route-test", state)

    assert result["reply"] == "在线个案回复"
    assert captured["raw_reply"] == "规则层模板草案"


def test_graph_does_not_swallow_online_model_failure(monkeypatch):
    import backend.graph as graph
    from backend.ai.online_reply import OnlineModelUnavailableError

    state = _state()

    class FakeApp:
        def invoke(self, payload, config):
            return {"case_state": state, "reply": "离线模板", "requires_user": True}

    def fail_compose(message, case, raw_reply):
        raise OnlineModelUnavailableError("temporarily_unavailable", "upstream")

    monkeypatch.setattr(graph, "app", FakeApp())
    monkeypatch.setattr(graph, "compose_online_reply", fail_compose, raising=False)
    monkeypatch.setattr(graph, "LEXPILOT_ALLOW_OFFLINE_FALLBACK", False)

    with pytest.raises(OnlineModelUnavailableError):
        graph.invoke_lexpilot("请继续", "online-failure-test", state)


def test_api_exposes_online_model_failure_as_service_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.api as api_module
    from backend.ai.online_reply import OnlineModelUnavailableError

    def fail_run(req):
        raise OnlineModelUnavailableError("authentication_failed", "upstream rejected key")

    monkeypatch.setattr(api_module, "_run", fail_run)

    response = TestClient(api_module.api_app).post(
        "/chat",
        json={"query": "朋友借钱不还"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "authentication_failed"


def test_stream_api_exposes_online_model_failure_as_service_unavailable(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.api as api_module
    from backend.ai.online_reply import OnlineModelUnavailableError

    def fail_run(req):
        raise OnlineModelUnavailableError("temporarily_unavailable", "upstream timeout")

    monkeypatch.setattr(api_module, "_run", fail_run)

    response = TestClient(api_module.api_app).post(
        "/chat/stream",
        json={"query": "朋友借钱不还"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "temporarily_unavailable"


def test_health_reports_online_reply_requirement_without_calling_the_model(monkeypatch):
    from fastapi.testclient import TestClient
    import backend.api as api_module

    monkeypatch.setattr(api_module, "get_consultation_provider", lambda: object(), raising=False)

    response = TestClient(api_module.api_app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["online_reply_required"] is True
    assert body["model_configured"] is True
