import pytest

from backend.graph import build_graph
from backend.legal_rl.actions import ACTION_TO_NODE, LegalAction
from backend.legal_rl.state import CaseState


def test_langgraph_policy_router_reaches_mapped_ask_fact_node():
    graph = build_graph()
    if graph is None:
        pytest.skip("langgraph is optional in the minimal core test runtime")
    compiled = graph.compile()
    result = compiled.invoke({
        "user_message": "我工作8个月，公司说试用期表现不合格，明天不用上班。"
    })
    state = CaseState.from_value(result["case_state"])
    assert state.current_action == LegalAction.ASK_FACT
    assert state.action_history[-1].node == ACTION_TO_NODE[LegalAction.ASK_FACT]
    assert result["requires_user"] is True
