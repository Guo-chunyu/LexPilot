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


class ResearchSource(BaseModel):
    source_id: str
    title: str
    url: str
    status: str = '待核验线索'
    summary: str = ''
    retrieved_at: str = ''


class ConsultationDossier(BaseModel):
    domain_ids: list[str] = Field(default_factory=list)
    jurisdiction_status: str = 'UNCONFIRMED'
    turns: int = 0
    declined_slots: list[str] = Field(default_factory=list)
    question_history: list[str] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    conflicts: list[dict[str, str]] = Field(default_factory=list)
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
