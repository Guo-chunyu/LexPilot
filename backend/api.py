"""FastAPI endpoints for the stateful LexPilot decision workflow."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.config import LEXPILOT_UPLOAD_DIR
from backend.graph import invoke_lexpilot
from backend.legal_domain.consultation.profiles import route_case, PROFILES
from uuid import uuid4
from backend.legal_domain.labor.evidence_upload import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_MESSAGE,
    UploadPayload,
    ingest_evidence_files,
)
from backend.legal_rl.state import CaseState


api_app = FastAPI(title="LexPilot API", version="4.0.0")
_sessions: dict[str, CaseState] = {}


def _upload_root() -> Path:
    configured = Path(LEXPILOT_UPLOAD_DIR)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[1] / configured


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    thread_id: str | None = None
    case_state: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    action: str | None
    action_reason: str
    requires_user: bool
    case_state: dict[str, Any]
    final_report: dict[str, Any]
    decision_mode: str = "rules"


def _run(req: ChatRequest) -> ChatResponse:
    thread_id = req.thread_id or f"case_{uuid4().hex}"
    prior = CaseState.from_value(req.case_state) if req.case_state else _sessions.get(thread_id)
    result = invoke_lexpilot(req.query, thread_id, prior)
    state: CaseState = result["case_state"]
    _sessions[thread_id] = state
    return ChatResponse(
        reply=result["reply"],
        thread_id=thread_id,
        action=state.current_action.name if state.current_action is not None else None,
        action_reason=state.current_reason,
        requires_user=result["requires_user"],
        case_state=state.public_dict(),
        final_report=state.final_report,
        decision_mode="rules",
    )


@api_app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        return _run(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api_app.post("/cases/{thread_id}/evidence", response_model=ChatResponse)
async def upload_evidence(
    thread_id: str,
    files: list[UploadFile] = File(...),
    query: str = Form(default=""),
) -> ChatResponse:
    """Upload one or more evidence files and continue the same case workflow."""

    try:
        if len(files) > MAX_FILES_PER_MESSAGE:
            raise ValueError(f"单次最多上传 {MAX_FILES_PER_MESSAGE} 个文件。")
        payloads: list[UploadPayload] = []
        for uploaded in files:
            data = await uploaded.read(MAX_FILE_BYTES + 1)
            payloads.append(UploadPayload(
                name=uploaded.filename or "upload",
                data=data,
                media_type=uploaded.content_type or "application/octet-stream",
            ))

        prior = _sessions.get(thread_id) or CaseState()
        if query.strip():
            route_case(query.strip(), prior)
        ingestion = ingest_evidence_files(prior, payloads, _upload_root())
        message = query.strip() or "我已上传系统要求的案件证据材料。"
        result = invoke_lexpilot(message, thread_id, prior)
        state: CaseState = result["case_state"]
        _sessions[thread_id] = state
        reply = f"{ingestion.summary_markdown()}\n\n{result['reply']}"
        return ChatResponse(
            reply=reply,
            thread_id=thread_id,
            action=state.current_action.name if state.current_action is not None else None,
            action_reason=state.current_reason,
            requires_user=result["requires_user"],
            case_state=state.public_dict(),
            final_report=state.final_report,
            decision_mode="rules",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def events():
        try:
            response = _run(req)
            for record in response.case_state.get("action_history", []):
                yield "data: " + json.dumps({
                    "node": record["node"],
                    "step": record["step"],
                    "action": record.get("action_name", record["action"]),
                    "reason": record["reason"],
                    "result": record["result"],
                }, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"done": True, **response.model_dump()}, ensure_ascii=False) + "\n\n"
        except Exception as exc:
            yield "data: " + json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")


@api_app.get("/cases/{thread_id}")
async def get_case(thread_id: str):
    state = _sessions.get(thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="case not found")
    return state.public_dict()


@api_app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "4.0.0",
        "domain": "general_legal_consultation",
        "practice_areas": list(PROFILES),
        "decision_mode": "rules",
    }
