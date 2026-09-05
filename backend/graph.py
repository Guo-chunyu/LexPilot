"""Rule-routed LangGraph for the LexPilot labor-dispute workflow."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, TypedDict

from backend.legal_domain.labor.evidence_gap import detect_evidence_gaps
from backend.legal_domain.labor.facts import extract_labor_facts
from backend.legal_rl.actions import ACTION_TO_NODE
from backend.legal_rl.policy import PolicyDecision, RuleBasedPolicy
from backend.legal_rl.state import CaseState
from backend.workflow import LexPilotEngine, execute_action

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, StateGraph
except ImportError:  # Minimal/offline test installs use the equivalent fallback below.
    InMemorySaver = None
    StateGraph = None
    END = "__end__"


class LexPilotGraphState(TypedDict, total=False):
    case_state: CaseState | dict[str, Any]
    user_message: str
    decision: dict[str, Any]
    reply: str
    requires_user: bool
    auto_steps: int


def _fact_extraction(graph_state: LexPilotGraphState) -> dict:
    case = CaseState.from_value(graph_state.get("case_state"))
    message = graph_state.get("user_message", "")
    case = extract_labor_facts(message, case)
    detect_evidence_gaps(case)
    return {"case_state": case, "reply": "", "requires_user": False, "auto_steps": 0}


def _policy_router(graph_state: LexPilotGraphState) -> dict:
    case = CaseState.from_value(graph_state.get("case_state"))
    decision = RuleBasedPolicy().decide(case)
    return {"decision": decision.model_dump(mode="json"), "case_state": case}


def _route_action(graph_state: LexPilotGraphState) -> str:
    decision = PolicyDecision.model_validate(graph_state["decision"])
    return ACTION_TO_NODE[decision.action]


def _action_node(graph_state: LexPilotGraphState) -> dict:
    case = CaseState.from_value(graph_state.get("case_state"))
    decision = PolicyDecision.model_validate(graph_state["decision"])
    execution = execute_action(case, decision, graph_state.get("user_message", ""))
    return {
        "case_state": case,
        "reply": execution.reply or graph_state.get("reply", ""),
        "requires_user": execution.requires_user,
        "auto_steps": int(graph_state.get("auto_steps", 0)) + 1,
    }


def _continue_or_end(graph_state: LexPilotGraphState) -> str:
    case = CaseState.from_value(graph_state.get("case_state"))
    if graph_state.get("requires_user") or case.done or int(graph_state.get("auto_steps", 0)) >= 12:
        return "end"
    return "continue"


def build_graph():
    """Build the dynamic graph using the audited rule decision order."""

    if StateGraph is None:
        return None
    workflow = StateGraph(LexPilotGraphState)
    def domain_router(graph_state):
        from backend.legal_domain.consultation.profiles import route_case
        case = CaseState.from_value(graph_state.get("case_state"))
        route_case(graph_state.get("user_message", ""), case)
        return {"case_state": case, "reply": "", "requires_user": False, "auto_steps": 0}

    def domain_route(graph_state):
        from backend.legal_domain.consultation.intake import wants_plan
        if CaseState.from_value(graph_state["case_state"]).case_type != "labor_dispute":
            return "general_consultation"
        return "labor_stage_plan" if wants_plan(graph_state.get("user_message", "")) else "fact_extraction"

    def general_consultation(graph_state):
        from backend.legal_domain.consultation.service import process_consultation
        return process_consultation(graph_state.get("user_message", ""), CaseState.from_value(graph_state["case_state"]))

    workflow.add_node("domain_router", domain_router)
    workflow.add_node("general_consultation", general_consultation)
    def labor_plan_node(graph_state):
        from backend.workflow import labor_stage_plan
        case = extract_labor_facts(graph_state.get("user_message", ""), CaseState.from_value(graph_state["case_state"]))
        detect_evidence_gaps(case)
        return labor_stage_plan(case)
    workflow.add_node("labor_stage_plan", labor_plan_node)
    workflow.add_node("fact_extraction", _fact_extraction)
    workflow.add_node("policy_router", _policy_router)
    for node_name in ACTION_TO_NODE.values():
        workflow.add_node(node_name, _action_node)
    workflow.set_entry_point("domain_router")
    workflow.add_conditional_edges("domain_router", domain_route, {"fact_extraction": "fact_extraction", "general_consultation": "general_consultation", "labor_stage_plan": "labor_stage_plan"})
    workflow.add_edge("general_consultation", END)
    workflow.add_edge("labor_stage_plan", END)
    workflow.add_edge("fact_extraction", "policy_router")
    workflow.add_conditional_edges(
        "policy_router",
        _route_action,
        {name: name for name in ACTION_TO_NODE.values()},
    )
    for node_name in ACTION_TO_NODE.values():
        workflow.add_conditional_edges(
            node_name,
            _continue_or_end,
            {"continue": "policy_router", "end": END},
        )
    return workflow


class FallbackGraph:
    """Same state/action semantics when LangGraph is not installed."""

    def __init__(self) -> None:
        self.engine = LexPilotEngine()
        self.sessions: dict[str, dict] = {}

    def invoke(self, inputs: dict, config: dict | None = None) -> dict:
        thread_id = (config or {}).get("configurable", {}).get("thread_id", "default")
        prior = inputs.get("case_state") or self.sessions.get(thread_id, {}).get("case_state")
        result = self.engine.process(inputs.get("user_message", ""), prior)
        payload = {
            "case_state": result["case_state"],
            "reply": result["reply"],
            "requires_user": result["requires_user"],
        }
        self.sessions[thread_id] = payload
        return payload

    def get_state(self, config: dict) -> SimpleNamespace:
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        return SimpleNamespace(values=self.sessions.get(thread_id, {}))


def compile_app():
    graph = build_graph()
    if graph is None:
        return FallbackGraph()
    return graph.compile(checkpointer=InMemorySaver())


app = compile_app()


def invoke_lexpilot(
    message: str,
    thread_id: str,
    case_state: CaseState | dict | None = None,
) -> dict:
    payload: dict[str, Any] = {"user_message": message}
    if case_state is not None:
        payload["case_state"] = case_state
    result = app.invoke(payload, config={"configurable": {"thread_id": thread_id}})
    case = CaseState.from_value(result.get("case_state"))
    return {
        "case_state": case,
        "reply": result.get("reply", ""),
        "requires_user": result.get("requires_user", False),
    }
