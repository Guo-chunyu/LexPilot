"""Responsive Canvas atmosphere for the LexPilot case workspace."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


CASE_PHASES = ("事实梳理", "证据核对", "法源分析", "行动方案")
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _asset(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


_COMPONENT_NAME = "lexpilot_evidence_constellation"
_EVIDENCE_CONSTELLATION = st.components.v2.component(
    _COMPONENT_NAME,
    html=_asset("evidence_constellation.html"),
    css=_asset("evidence_constellation.css"),
    js=_asset("evidence_constellation.mjs"),
    isolate_styles=True,
)


def _renderer_for_active_runtime():
    """Re-register only when a test runtime has replaced Streamlit's registry."""

    global _EVIDENCE_CONSTELLATION
    from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

    if get_script_run_ctx(suppress_warning=True) is None:
        return _EVIDENCE_CONSTELLATION

    from streamlit.runtime import Runtime

    registry = Runtime.instance().bidi_component_registry
    if registry.get(_COMPONENT_NAME) is None:
        _EVIDENCE_CONSTELLATION = st.components.v2.component(
            _COMPONENT_NAME,
            html=_asset("evidence_constellation.html"),
            css=_asset("evidence_constellation.css"),
            js=_asset("evidence_constellation.mjs"),
            isolate_styles=True,
        )
    return _EVIDENCE_CONSTELLATION


def particle_payload(
    phase: str,
    *,
    intro: bool,
) -> dict[str, object]:
    """Build a small validated payload for the browser-side renderer."""

    normalized = phase if phase in CASE_PHASES else CASE_PHASES[0]
    return {
        "phase": normalized,
        "phaseIndex": CASE_PHASES.index(normalized),
        "intro": bool(intro),
    }


def render_evidence_constellation(
    phase: str,
    *,
    intro: bool,
) -> None:
    """Mount the decorative, non-interactive evidence constellation."""

    renderer = _renderer_for_active_runtime()
    renderer(
        key="lexpilot_evidence_constellation",
        data=particle_payload(
            phase,
            intro=intro,
        ),
        width="stretch",
        height=300,
    )
