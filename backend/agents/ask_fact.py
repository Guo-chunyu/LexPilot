"""AskFact Agent backed by the configured active-inquiry priorities."""

from backend.legal_domain.labor.inquiry import select_questions
from backend.legal_rl.state import CaseState


def ask_fact_node(state: CaseState, limit: int = 1) -> list[str]:
    """Ask only the most important one or two missing facts."""

    return select_questions(state, limit=limit)

