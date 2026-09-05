"""Discrete action space shared by policies, LangGraph and the simulator."""

from enum import IntEnum


class LegalAction(IntEnum):
    """Auditable actions available to the legal workflow router."""

    ASK_FACT = 0
    REQUEST_EVIDENCE = 1
    SEARCH_LAW = 2
    SEARCH_CASE = 3
    SIMULATE_OPPONENT = 4
    VERIFY = 5
    CALCULATE = 6
    GENERATE_DOCUMENT = 7
    STOP = 8
    ESCALATE_HUMAN = 9


ACTION_TO_NODE: dict[LegalAction, str] = {
    LegalAction.ASK_FACT: "ask_fact_agent",
    LegalAction.REQUEST_EVIDENCE: "evidence_agent",
    LegalAction.SEARCH_LAW: "legal_retrieval",
    LegalAction.SEARCH_CASE: "case_retrieval",
    LegalAction.SIMULATE_OPPONENT: "opponent_agent",
    LegalAction.VERIFY: "judge_agent",
    LegalAction.CALCULATE: "compensation_tool",
    LegalAction.GENERATE_DOCUMENT: "report_agent",
    LegalAction.STOP: "final_report",
    LegalAction.ESCALATE_HUMAN: "human_escalation",
}

INTERACTIVE_ACTIONS = {
    LegalAction.ASK_FACT,
    LegalAction.REQUEST_EVIDENCE,
}

TERMINAL_ACTIONS = {
    LegalAction.STOP,
    LegalAction.ESCALATE_HUMAN,
}


def validate_action_mapping() -> None:
    """Fail fast when an action has no executable node."""

    missing = set(LegalAction) - set(ACTION_TO_NODE)
    extra = set(ACTION_TO_NODE) - set(LegalAction)
    if missing or extra:
        raise ValueError(f"Invalid action mapping: missing={missing}, extra={extra}")


validate_action_mapping()
