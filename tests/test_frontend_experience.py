import importlib
import re
from xml.etree import ElementTree


def _load_experience_module():
    spec = importlib.util.find_spec("frontend_experience")
    assert spec is not None, "动态视觉层尚未实现"
    return importlib.import_module("frontend_experience")


def test_brand_mark_keeps_decorative_geometry_out_of_sanitized_html():
    experience = _load_experience_module()

    root = ElementTree.fromstring(experience.brand_markup())
    visible_text = "".join(root.itertext())
    css = experience.motion_styles()

    assert root.attrib["aria-label"] == "律策 LexPilot"
    assert root.attrib["role"] == "img"
    assert "律策" in visible_text
    assert "LEXPILOT" in visible_text
    assert root.find("span[@class='lexpilot-brand__seal']") is None
    assert root.find("{http://www.w3.org/2000/svg}svg") is None
    assert "data:image/svg+xml" in css


def test_keyframes_avoid_continuous_paint_heavy_properties():
    experience = _load_experience_module()

    css = experience.motion_styles()
    keyframe_start = re.compile(r"@keyframes\s+[\w-]+\s*\{")
    keyframe_bodies = []
    for match in keyframe_start.finditer(css):
        depth = 1
        cursor = match.end()
        while depth and cursor < len(css):
            depth += (css[cursor] == "{") - (css[cursor] == "}")
            cursor += 1
        keyframe_bodies.append(css[match.end() : cursor - 1])

    animated_properties = "\n".join(keyframe_bodies)
    assert "filter:" not in animated_properties
    assert "box-shadow:" not in animated_properties


def test_motion_styles_define_a_finite_entrance_and_a_reduced_motion_path():
    experience = _load_experience_module()

    css = experience.motion_styles()
    keyframes = re.findall(r"@keyframes\s+[\w-]+", css)
    reduced_motion = re.search(
        r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(?P<body>.*)\}\s*$",
        css,
        flags=re.DOTALL,
    )

    assert keyframes
    assert reduced_motion is not None
    assert "animation: none" in reduced_motion.group("body")
    assert "infinite" not in css


def test_page_entrance_only_runs_for_a_new_browser_session():
    experience = _load_experience_module()

    assert experience.experience_shell_key(intro_seen=False) == "experience_intro"
    assert experience.experience_shell_key(intro_seen=True) == "experience_steady"


def test_sidebar_entrance_only_runs_for_a_new_browser_session():
    experience = _load_experience_module()

    sidebar_shell_key = getattr(experience, "sidebar_shell_key", None)
    assert callable(sidebar_shell_key)
    assert sidebar_shell_key(intro_seen=False) == "sidebar_intro"
    assert sidebar_shell_key(intro_seen=True) == "sidebar_steady"
