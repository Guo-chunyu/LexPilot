"""Shared API schemas; CaseState is the workflow's only authoritative state."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.legal_rl.state import CaseState


class AnalyzerOutput(BaseModel):
    intent: Literal["LEGAL", "CHAT", "OUT_OF_SCOPE"] = Field(description="用户意图分类")
    rewritten_query: str = ""
    sub_tasks: list[str] = Field(default_factory=list)


class FinalResponse(BaseModel):
    reply_text: str
    needs_doc: bool = False
    doc_title: str = ""
    doc_content: str = ""


class JudgeVerdict(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    suggestion: str = ""


__all__ = ["AnalyzerOutput", "CaseState", "FinalResponse", "JudgeVerdict"]

