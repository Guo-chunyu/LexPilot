"""The single authoritative state model for a LexPilot labor case."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.legal_rl.actions import LegalAction
from backend.legal_domain.consultation.models import ConsultationDossier


class EvidenceStatus(str, Enum):
    PROVEN = "PROVEN"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    CONFLICT = "CONFLICT"


class EvidenceItem(BaseModel):
    name: str
    source: str = "user"
    notes: str = ""


class FactProvenance(BaseModel):
    """Trace one structured fact back to the text or file that supplied it."""

    fact_id: str
    source_type: str = "user_message"
    source_ref: str = ""
    quote: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    extraction_method: str = "rules"
    accepted: bool = True


class FileExtractionStatus(str, Enum):
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    METADATA_ONLY = "METADATA_ONLY"
    PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"
    FAILED = "FAILED"


class UploadedEvidenceFile(BaseModel):
    file_id: str
    original_name: str
    stored_name: str
    media_type: str = "application/octet-stream"
    extension: str
    size_bytes: int = Field(ge=0)
    sha256: str
    evidence_names: list[str] = Field(default_factory=list)
    extracted_facts: list[str] = Field(default_factory=list)
    extraction_status: FileExtractionStatus
    text_preview: str = ""
    page_count: int | None = None
    notes: str = ""
    stored_path: str = Field(default="", exclude=True, repr=False)
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvidenceGap(BaseModel):
    element_id: str
    name: str
    status: EvidenceStatus
    evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    reason: str = ""


class LawReference(BaseModel):
    source_id: str = ""
    law_name: str
    article: str
    summary: str
    source_url: str
    effective_from: date | None = None
    effective_to: date | None = None
    authority_level: int = Field(default=1, ge=1, le=5)
    retrieval_score: float = Field(default=0.0, ge=0.0)
    matched_elements: list[str] = Field(default_factory=list)
    temporal_validated: bool = True


class InquiryCandidate(BaseModel):
    fact_id: str
    question: str
    score: float = Field(ge=0.0, le=1.0)
    legal_importance: float = Field(ge=0.0, le=1.0)
    expected_information_gain: float = Field(ge=0.0, le=1.0)
    element_coverage: float = Field(ge=0.0, le=1.0)
    evidence_leverage: float = Field(ge=0.0, le=1.0)
    conflict_urgency: float = Field(ge=0.0, le=1.0)
    interaction_cost: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class ReasoningNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    status: str = ""
    value: str = ""


class ReasoningEdge(BaseModel):
    source: str
    target: str
    relation: str
    rationale: str = ""


class ReasoningPath(BaseModel):
    element_id: str
    element_name: str
    fact_ids: list[str] = Field(default_factory=list)
    evidence_names: list[str] = Field(default_factory=list)
    law_ids: list[str] = Field(default_factory=list)
    status: EvidenceStatus
    support_score: float = Field(ge=0.0, le=1.0)
    explanation: str = ""


class EvidenceReasoningGraph(BaseModel):
    version: str = "1.0"
    nodes: list[ReasoningNode] = Field(default_factory=list)
    edges: list[ReasoningEdge] = Field(default_factory=list)
    paths: list[ReasoningPath] = Field(default_factory=list)
    focus_element_ids: list[str] = Field(default_factory=list)


class ClaimVerification(BaseModel):
    claim_id: str
    claim: str
    status: str
    fact_ids: list[str] = Field(default_factory=list)
    evidence_names: list[str] = Field(default_factory=list)
    law_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class VerificationResult(BaseModel):
    status: str = "INSUFFICIENT_SUPPORT"
    fact_traceability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    claim_support_score: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_validity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    temporal_validity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    can_generate: bool = False
    refusal_reason: str = ""
    claims: list[ClaimVerification] = Field(default_factory=list)


class RiskItem(BaseModel):
    name: str
    description: str
    level: float = Field(ge=0.0, le=1.0)


class JudgeResult(BaseModel):
    fact_score: float = Field(ge=0.0, le=1.0)
    evidence_score: float = Field(ge=0.0, le=1.0)
    legal_score: float = Field(ge=0.0, le=1.0)
    citation_score: float = Field(ge=0.0, le=1.0)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    can_stop: bool
    reason: str


class ActionRecord(BaseModel):
    step: int
    action: LegalAction
    reason: str
    node: str
    result: str = ""
    reward_breakdown: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @computed_field
    @property
    def action_name(self) -> str:
        return self.action.name


class CaseState(BaseModel):
    """Mutable case state shared by the legal workflow."""

    model_config = ConfigDict(use_enum_values=False, validate_assignment=True)

    case_id: str = Field(default_factory=lambda: f"labor_{uuid4().hex[:12]}")
    case_type: str = "labor_dispute"
    dispute_type: str = "unknown"
    event_date: date | None = None
    user_narrative: str = ""
    consultation: ConsultationDossier = Field(default_factory=ConsultationDossier)

    facts: dict[str, Any] = Field(default_factory=dict)
    fact_provenance: list[FactProvenance] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    uploaded_files: list[UploadedEvidenceFile] = Field(default_factory=list)
    evidence_parser_version: int = Field(default=0, ge=0)
    key_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    unavailable_evidence: list[str] = Field(default_factory=list)
    evidence_collection_exhausted: bool = False
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)

    retrieved_laws: list[LawReference] = Field(default_factory=list)
    retrieved_cases: list[dict[str, Any]] = Field(default_factory=list)
    legal_issues: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    opponent_analysis: dict[str, Any] = Field(default_factory=dict)

    fact_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_completeness: float = Field(default=0.0, ge=0.0, le=1.0)
    legal_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    issue_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    contradiction_score: float = Field(default=0.0, ge=0.0, le=1.0)

    action_history: list[ActionRecord] = Field(default_factory=list)
    current_action: LegalAction | None = None
    current_reason: str = ""
    pending_questions: list[str] = Field(default_factory=list)
    pending_fact_ids: list[str] = Field(default_factory=list)
    inquiry_candidates: list[InquiryCandidate] = Field(default_factory=list)
    pending_evidence_requests: list[str] = Field(default_factory=list)
    reasoning_graph: EvidenceReasoningGraph = Field(default_factory=EvidenceReasoningGraph)
    verification_result: VerificationResult | None = None
    judge_result: JudgeResult | None = None
    compensation_estimate: dict[str, Any] = Field(default_factory=dict)
    final_report: dict[str, Any] = Field(default_factory=dict)

    # Per-invocation runtime metadata. These values never leave the backend.
    ai_calls_this_turn: int = Field(default=0, exclude=True, ge=0)
    reply_transition: str = Field(default="", exclude=True)

    step_count: int = 0
    max_steps: int = 20
    done: bool = False
    escalated: bool = False

    def apply_facts(self, new_facts: dict[str, Any]) -> None:
        """Merge non-empty facts and clear their missing markers."""

        changed = False
        for key, value in new_facts.items():
            if value is None or value == "":
                continue
            changed = changed or self.facts.get(key) != value
            self.facts[key] = value
            if key in self.missing_facts:
                self.missing_facts.remove(key)
        if changed:
            self.judge_result = None
            self.verification_result = None
            self.final_report = {}
            if self.done and self.escalated:
                self.done = False
                self.escalated = False

    def add_fact_provenance(
        self,
        fact_id: str,
        *,
        source_type: str = "user_message",
        source_ref: str = "",
        quote: str = "",
        confidence: float = 1.0,
        extraction_method: str = "rules",
        accepted: bool = True,
    ) -> None:
        """Keep the strongest unique source trace for a fact without leaking provider details."""

        normalized_quote = " ".join(str(quote).split())[:240]
        signature = (fact_id, source_type, source_ref, normalized_quote, extraction_method)
        for item in self.fact_provenance:
            if (
                item.fact_id,
                item.source_type,
                item.source_ref,
                item.quote,
                item.extraction_method,
            ) == signature:
                return
        self.fact_provenance.append(FactProvenance(
            fact_id=fact_id,
            source_type=source_type,
            source_ref=source_ref,
            quote=normalized_quote,
            confidence=max(0.0, min(float(confidence), 1.0)),
            extraction_method=extraction_method,
            accepted=accepted,
        ))

    def add_evidence(self, name: str, source: str = "user", notes: str = "") -> None:
        """Add evidence once, preserving a readable source trail."""

        normalized = name.strip()
        if not normalized:
            return
        existing = {item.name for item in self.evidence}
        if normalized not in existing:
            self.evidence.append(EvidenceItem(name=normalized, source=source, notes=notes))
            self.judge_result = None
            self.verification_result = None
            self.final_report = {}
            if source in {"uploaded_file", "user_message", "contextual_user_answer"}:
                self.evidence_collection_exhausted = False
            if self.done and self.escalated:
                self.done = False
                self.escalated = False
        if normalized in self.missing_evidence:
            self.missing_evidence.remove(normalized)
        if normalized in self.unavailable_evidence:
            self.unavailable_evidence.remove(normalized)

    def mark_evidence_unavailable(self, names: list[str], *, exhausted: bool = False) -> None:
        """Remember a user's negative answer so the same materials are not requested again."""

        present = {item.name for item in self.evidence}
        changed = False
        for name in names:
            normalized = name.strip()
            if not normalized or normalized in present or normalized in self.unavailable_evidence:
                continue
            self.unavailable_evidence.append(normalized)
            changed = True
        if exhausted and not self.evidence_collection_exhausted:
            self.evidence_collection_exhausted = True
            changed = True
        if changed:
            self.judge_result = None
            self.verification_result = None
            self.final_report = {}

    def record_action(
        self,
        action: LegalAction,
        reason: str,
        node: str,
        result: str = "",
        reward_breakdown: dict[str, float] | None = None,
    ) -> ActionRecord:
        self.step_count += 1
        self.current_action = action
        self.current_reason = reason
        record = ActionRecord(
            step=self.step_count,
            action=action,
            reason=reason,
            node=node,
            result=result,
            reward_breakdown=reward_breakdown or {},
        )
        self.action_history.append(record)
        return record

    def public_dict(self) -> dict[str, Any]:
        """JSON-safe representation returned by API and Streamlit."""

        return self.model_dump(mode="json")

    @classmethod
    def from_value(cls, value: "CaseState | dict[str, Any] | None") -> "CaseState":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            return cls.model_validate(value)
        if hasattr(value, "model_dump"):
            payload = value.model_dump(mode="python")
            # Older live Streamlit sessions may hold instances of the previous
            # Pydantic class after a hot reload. Preserve local file paths, which
            # are intentionally excluded from normal API serialization.
            old_files = list(getattr(value, "uploaded_files", []))
            for index, item in enumerate(payload.get("uploaded_files", [])):
                if index < len(old_files):
                    item["stored_path"] = getattr(old_files[index], "stored_path", "")
            return cls.model_validate(payload)
        return cls()
