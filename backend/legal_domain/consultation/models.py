"""Serializable consultation records, independent of the legacy labor models."""

from pydantic import BaseModel, Field


class TimelineEntry(BaseModel):
    date_text: str
    description: str
    source_ref: str
    source_type: str = 'user_message'
    status: str = '待核实陈述'


class EvidenceTask(BaseModel):
    name: str
    proves: str
    how: str
    alternative: str
    status: str = '尚未提供'
    source_refs: list[str] = Field(default_factory=list)


class ActionStep(BaseModel):
    title: str
    when: str
    channel: str
    materials: list[str]
    instructions: list[str]
    completion: str
    fallback: str
    prerequisite: str = '以事实核实和当地受理要求为准'
    suggested_date: str = ''
    date_note: str = '这是建议办事日程，不是法定期限；文书期限更早时优先处理。'


class ResearchSource(BaseModel):
    source_id: str
    title: str
    url: str
    status: str = '待核验线索'
    summary: str = ''
    retrieved_at: str = ''


class SlotAssertion(BaseModel):
    """One stated value for a fact slot, attributable to a specific actor.

    ``key`` is the fact name (``amount`` / ``procedure`` / ``constraints`` …).
    ``assertor`` distinguishes the user's own assertions from those of the
    counterparty or an authority: this lets the engine guarantee that a
    counterparty claim never silently overwrites a user-owned slot, while the
    user's corrections or withdrawals update the lifecycle.
    """

    key: str
    value: str
    assertor: str = 'user'  # user / counterparty / authority / system
    turn: int = 0
    source_ref: str = ''
    quote: str = ''
    lifecycle: str = 'active'  # active / superseded / withdrawn
    superseded_by: str = ''  # the source_ref of the newer active assertion
    extraction_method: str = 'rules'
    asserted_at: str = ''


class CounterpartyClaim(BaseModel):
    """A claim attributed to the counterparty or an authority that was
    deliberately not promoted into a user-owned slot.

    Stored separately so the downstream report can ground its dispute analysis
    in the claim without allowing it to overwrite the user's own assertion.
    """

    slot: str
    value: str
    assertor: str = 'counterparty'
    turn: int = 0
    source_ref: str = ''
    quote: str = ''


class ConsultationDossier(BaseModel):
    domain_ids: list[str] = Field(default_factory=list)
    jurisdiction_status: str = 'UNCONFIRMED'
    turns: int = 0
    declined_slots: list[str] = Field(default_factory=list)
    question_history: list[str] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    conflicts: list[dict[str, str]] = Field(default_factory=list)
    corrections: list[dict[str, str]] = Field(default_factory=list)
    evidence_tasks: list[EvidenceTask] = Field(default_factory=list)
    urgent_actions: list[str] = Field(default_factory=list)
    research_sources: list[ResearchSource] = Field(default_factory=list)
    research_status: str = '尚未检索'
    research_key: str = ''
    stage: str = '接谈'
    semantic_status: str = '基础咨询'
    analysis: str = ''
    follow_up: str = ''
    # Generated recommendations are advice drafts, never verified legal findings.
    tailored_steps: list[ActionStep] = Field(default_factory=list)
    tailored_for: str = ''
    knowledge_passages: list[dict] = Field(default_factory=list)
    retrieval_audit: dict = Field(default_factory=dict)
    grounded_claims: list[dict] = Field(default_factory=list)
    generation_audit: dict = Field(default_factory=dict)
    service_guide: dict = Field(default_factory=dict)
    service_key: str = ''
    decision_snapshot: dict = Field(default_factory=dict)
    # Side-channel for counterparty / authority assertions that must not
    # silently overwrite a user-owned slot.
    counterparty_claims: list[CounterpartyClaim] = Field(default_factory=list)
