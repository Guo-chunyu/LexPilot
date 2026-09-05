import importlib
import json
from pathlib import Path
import shutil
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARTICLE_MODULE = PROJECT_ROOT / "static" / "evidence_constellation.mjs"


def _load_constellation_module():
    return importlib.import_module("evidence_constellation")


def _javascript_contract() -> dict:
    node = shutil.which("node")
    assert node is not None, "粒子动效需要 Node.js 来验证浏览器端预算"
    assert PARTICLE_MODULE.is_file(), "粒子动效脚本尚未实现"

    module_url = PARTICLE_MODULE.as_uri()
    script = f"""
      import({json.dumps(module_url)}).then((visual) => {{
        const targets = visual.balanceTargets(84, 1440, 900);
        const compactTargets = visual.balanceTargets(52, 480, 320);
        const hasCycleState = typeof visual.cycleState === "function";
        const hasSceneDimensions = typeof visual.sceneDimensions === "function";
        const hasLocalPointer = typeof visual.localPointer === "function";
        console.log(JSON.stringify({{
          desktop: visual.particleBudget(1440, 8, false),
          tablet: visual.particleBudget(900, 8, false),
          hero: visual.particleBudget(480, 8, false),
          mobile: visual.particleBudget(390, 8, false),
          constrained: visual.particleBudget(1440, 4, false),
          reduced: visual.particleBudget(1440, 8, true),
          runsVisible: visual.animationShouldRun(false, true),
          runsHidden: visual.animationShouldRun(false, false),
          runsReduced: visual.animationShouldRun(true, true),
          hasCycleState,
          gatherStart: hasCycleState ? visual.cycleState(0) : null,
          hold: hasCycleState ? visual.cycleState(4000) : null,
          release: hasCycleState ? visual.cycleState(7000) : null,
          drift: hasCycleState ? visual.cycleState(10500) : null,
          repeat: hasCycleState ? visual.cycleState(12000) : null,
          hasSceneDimensions,
          sceneDimensions: hasSceneDimensions ? visual.sceneDimensions(479.6, 319.8) : null,
          zeroHeightDimensions: hasSceneDimensions ? visual.sceneDimensions(479.6, 0) : null,
          hasLocalPointer,
          localPointer: hasLocalPointer
            ? visual.localPointer(720, 180, {{ left: 480, top: 20, width: 480, height: 320 }})
            : null,
          outsidePointer: hasLocalPointer
            ? visual.localPointer(220, 180, {{ left: 480, top: 20, width: 480, height: 320 }})
            : null,
          secondAnchor: visual.particleAnchor(5, 1440, 900),
          targetCount: targets.length,
          targetSpread: Math.max(...targets.map((point) => point.x)) - Math.min(...targets.map((point) => point.x)),
          targetCenter: (Math.max(...targets.map((point) => point.x)) + Math.min(...targets.map((point) => point.x))) / 2,
          targetsInViewport: targets.every((point) =>
            point.x >= 0 && point.x <= 1440 && point.y >= 0 && point.y <= 900
          ),
          compactTargetCount: compactTargets.length,
          compactTargetSpread: Math.max(...compactTargets.map((point) => point.x)) - Math.min(...compactTargets.map((point) => point.x)),
          compactTargetsInFrame: compactTargets.every((point) =>
            point.x >= 0 && point.x <= 480 && point.y >= 0 && point.y <= 320
          ),
          evidencePhase: visual.phaseSignal("证据核对"),
          fallbackPhase: visual.phaseSignal("未知阶段")
        }}));
      }}).catch((error) => {{
        console.error(error);
        process.exit(1);
      }});
    """
    result = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_component_payload_normalizes_phase_and_intro_state():
    constellation = _load_constellation_module()

    assert constellation.particle_payload("证据核对", intro=True) == {
        "phase": "证据核对",
        "phaseIndex": 1,
        "intro": True,
    }


def test_component_reserves_an_in_flow_hero_region(monkeypatch):
    constellation = _load_constellation_module()
    calls = []

    monkeypatch.setattr(
        constellation,
        "_renderer_for_active_runtime",
        lambda: lambda **kwargs: calls.append(kwargs),
    )

    constellation.render_evidence_constellation("事实梳理", intro=True)

    assert calls[0]["width"] == "stretch"
    assert calls[0]["height"] == 300
    assert constellation.particle_payload("未知阶段", intro=1) == {
        "phase": "事实梳理",
        "phaseIndex": 0,
        "intro": True,
    }


def test_particle_budget_scales_down_for_mobile_hardware_and_reduced_motion():
    contract = _javascript_contract()

    assert contract["desktop"] == 84
    assert contract["tablet"] == 52
    assert contract["hero"] == 52
    assert contract["mobile"] == 28
    assert contract["constrained"] < contract["desktop"]
    assert contract["reduced"] == 24


def test_animation_lifecycle_stops_for_hidden_or_reduced_motion_documents():
    contract = _javascript_contract()

    assert contract["runsVisible"] is True
    assert contract["runsHidden"] is False
    assert contract["runsReduced"] is False
    assert contract["secondAnchor"]["x"] > 900
    assert 0 < contract["secondAnchor"]["y"] < 900


def test_canvas_uses_its_hero_frame_instead_of_viewport_coordinates():
    contract = _javascript_contract()

    assert contract["hasSceneDimensions"] is True
    assert contract["sceneDimensions"] == {"width": 480, "height": 320}
    assert contract["zeroHeightDimensions"] == {"width": 480, "height": 300}
    assert contract["hasLocalPointer"] is True
    assert contract["localPointer"] == {"x": 240, "y": 160, "active": True}
    assert contract["outsidePointer"]["active"] is False


def test_particle_cycle_repeatedly_gathers_holds_releases_and_drifts():
    contract = _javascript_contract()

    assert contract["hasCycleState"] is True
    assert contract["gatherStart"] == {"stage": "gather", "blend": 0, "cycleIndex": 0}
    assert contract["hold"]["stage"] == "hold"
    assert contract["hold"]["blend"] == 1
    assert contract["release"]["stage"] == "release"
    assert 0 < contract["release"]["blend"] < 1
    assert contract["drift"]["stage"] == "drift"
    assert contract["drift"]["blend"] == 0
    assert contract["repeat"] == {"stage": "gather", "blend": 0, "cycleIndex": 1}


def test_balance_formation_and_phase_mapping_are_deterministic():
    contract = _javascript_contract()

    assert contract["targetCount"] == 84
    assert contract["targetSpread"] >= 280
    assert 900 <= contract["targetCenter"] <= 1030
    assert contract["targetsInViewport"] is True
    assert contract["compactTargetCount"] == 52
    assert contract["compactTargetSpread"] >= 110
    assert contract["compactTargetsInFrame"] is True
    assert contract["evidencePhase"]["index"] == 1
    assert contract["evidencePhase"]["label"] == "证据核对"
    assert contract["fallbackPhase"]["index"] == 0
