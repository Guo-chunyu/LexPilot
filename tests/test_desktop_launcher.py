from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from desktop.launcher import (
    configure_runtime,
    find_running_url,
    resolve_app_data_dir,
    resolve_resource_root,
)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/_stcore/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args) -> None:
        return


def test_resolve_app_data_dir_uses_native_user_locations(tmp_path: Path) -> None:
    env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    assert resolve_app_data_dir("win32", env, tmp_path) == tmp_path / "Local" / "LexPilot"
    assert resolve_app_data_dir("darwin", {}, tmp_path) == (
        tmp_path / "Library" / "Application Support" / "LexPilot"
    )
    assert resolve_app_data_dir("linux", {}, tmp_path) == tmp_path / ".local" / "share" / "LexPilot"


def test_configure_runtime_creates_private_paths_and_keeps_existing_values(tmp_path: Path) -> None:
    app_data = tmp_path / "profile"
    resources = tmp_path / "bundle"
    resources.mkdir()
    env = {"LEXPILOT_ENABLE_SEMANTIC_AI": "false"}

    runtime = configure_runtime(app_data, resources, env)

    assert runtime.uploads_dir.is_dir()
    assert runtime.logs_dir.is_dir()
    assert env["LEXPILOT_UPLOAD_DIR"] == str(app_data / "uploads")
    assert env["HF_HOME"] == str(app_data / "models_cache")
    assert env["LEXPILOT_ENABLE_SEMANTIC_AI"] == "false"
    assert runtime.settings_file.read_text(encoding="utf-8").startswith(
        "# LexPilot optional AI settings"
    )
    assert "sk-" not in runtime.settings_file.read_text(encoding="utf-8")


def test_resolve_resource_root_prefers_pyinstaller_bundle(tmp_path: Path) -> None:
    module_file = tmp_path / "source" / "desktop" / "launcher.py"
    bundle = tmp_path / "bundle"
    assert resolve_resource_root(module_file, bundle) == bundle
    assert resolve_resource_root(module_file, None) == module_file.parents[1]


def test_find_running_url_accepts_only_a_live_streamlit_health_endpoint(tmp_path: Path) -> None:
    state_file = tmp_path / "server.json"
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        state_file.write_text(json.dumps({"port": server.server_port}), encoding="utf-8")
        assert find_running_url(state_file) == f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    state_file.write_text(json.dumps({"port": server.server_port}), encoding="utf-8")
    assert find_running_url(state_file, timeout=0.05) is None


def test_configure_runtime_loads_settings_without_overwriting_process_env(tmp_path: Path) -> None:
    app_data = tmp_path / "profile"
    app_data.mkdir()
    (app_data / "settings.env").write_text(
        "QWEN_MODEL=qwen-test\nLEXPILOT_ENABLE_SEMANTIC_AI=true\n",
        encoding="utf-8",
    )
    env = {"LEXPILOT_ENABLE_SEMANTIC_AI": "false"}

    configure_runtime(app_data, tmp_path, env)

    assert env["QWEN_MODEL"] == "qwen-test"
    assert env["LEXPILOT_ENABLE_SEMANTIC_AI"] == "false"

