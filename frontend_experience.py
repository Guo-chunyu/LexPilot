"""Distinctive, accessible presentation layer for the LexPilot workspace."""

from __future__ import annotations

from pathlib import Path


MOTION_STYLES_PATH = Path(__file__).resolve().parent / "static" / "lexpilot-motion.css"


def brand_markup() -> str:
    """Return the semantic wordmark and its decorative authored seal."""

    return """
<div class="lexpilot-brand" role="img" aria-label="律策 LexPilot">
  <div class="lexpilot-brand__wordmark">
    <div class="lexpilot-brand__name"><span>律</span><span>策</span></div>
    <div class="lexpilot-brand__signature">
      <span aria-hidden="true"></span>
      <b translate="no">LEXPILOT</b>
    </div>
    <p>证据为经 · 法理为纬</p>
  </div>
</div>
""".strip()


def motion_styles() -> str:
    """Return the shipped stylesheet for automated and manual verification."""

    return MOTION_STYLES_PATH.read_text(encoding="utf-8")


def experience_shell_key(*, intro_seen: bool) -> str:
    """Choose an animated shell only for a browser session's first render."""

    return "experience_steady" if intro_seen else "experience_intro"


def sidebar_shell_key(*, intro_seen: bool) -> str:
    """Choose an animated sidebar shell only for the first session render."""

    return "sidebar_steady" if intro_seen else "sidebar_intro"


def render_motion_styles() -> None:
    """Install the trusted local stylesheet without enabling JavaScript."""

    import streamlit as st

    st.html(MOTION_STYLES_PATH)


def render_brand() -> None:
    """Render the LexPilot signature mark in the sidebar."""

    import streamlit as st

    st.html(brand_markup(), width="stretch")
