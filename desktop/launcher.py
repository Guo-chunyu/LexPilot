"""Native desktop entry point that starts the bundled Streamlit application."""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Mapping, MutableMapping
from urllib.error import URLError
from urllib.request import urlopen


APP_NAME = "LexPilot"
HOST = "127.0.0.1"
SETTINGS_TEMPLATE = """# LexPilot optional AI settings
# The app works in offline rule mode when no API key is configured.
# Add your own key here only on this computer; never publish this file.
DASHSCOPE_API_KEY=
QWEN_MODEL=qwen3.8-flash
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_ENABLE_THINKING=true
LEXPILOT_ENABLE_SEMANTIC_AI=true
LLM_REQUEST_TIMEOUT_SECONDS=8
"""


@dataclass(frozen=True)
class RuntimePaths:
    app_data_dir: Path
    uploads_dir: Path
    logs_dir: Path
    models_dir: Path
    settings_file: Path
    state_file: Path


def resolve_app_data_dir(
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the per-user application data directory for the current OS."""

    platform_name = platform_name or sys.platform
    environ = environ or os.environ
    home = Path.home() if home is None else Path(home)
    if platform_name == "win32":
        base = Path(environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return base / APP_NAME
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    base = Path(environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return base / APP_NAME


def resolve_resource_root(module_file: Path, bundle_root: str | Path | None) -> Path:
    """Locate app.py and bundled static resources in source or PyInstaller builds."""

    if bundle_root:
        return Path(bundle_root).resolve()
    return Path(module_file).resolve().parents[1]


def _read_settings(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def configure_runtime(
    app_data_dir: Path,
    resource_root: Path,
    environ: MutableMapping[str, str] | None = None,
) -> RuntimePaths:
    """Create writable user directories and load the user's optional AI settings."""

    environ = os.environ if environ is None else environ
    app_data_dir = Path(app_data_dir)
    uploads_dir = app_data_dir / "uploads"
    logs_dir = app_data_dir / "logs"
    models_dir = app_data_dir / "models_cache"
    for directory in (app_data_dir, uploads_dir, logs_dir, models_dir):
        directory.mkdir(parents=True, exist_ok=True)

    settings_file = app_data_dir / "settings.env"
    if not settings_file.exists():
        settings_file.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
    for key, value in _read_settings(settings_file).items():
        environ.setdefault(key, value)

    environ.setdefault("LEXPILOT_UPLOAD_DIR", str(uploads_dir))
    environ.setdefault("HF_HOME", str(models_dir))
    environ.setdefault("LEXPILOT_RESOURCE_ROOT", str(Path(resource_root)))
    environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    return RuntimePaths(
        app_data_dir=app_data_dir,
        uploads_dir=uploads_dir,
        logs_dir=logs_dir,
        models_dir=models_dir,
        settings_file=settings_file,
        state_file=app_data_dir / "server.json",
    )


def _health_url(port: int) -> str:
    return f"http://{HOST}:{port}/_stcore/health"


def _app_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def find_running_url(state_file: Path, timeout: float = 0.3) -> str | None:
    """Return an existing local LexPilot URL only when its health check succeeds."""

    try:
        state = json.loads(Path(state_file).read_text(encoding="utf-8"))
        port = int(state["port"])
        if not 1024 <= port <= 65535:
            return None
        with urlopen(_health_url(port), timeout=timeout) as response:  # noqa: S310 - localhost only
            if response.status == 200 and response.read(32).strip().lower() == b"ok":
                return _app_url(port)
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError, URLError, OSError, TimeoutError):
        return None
    return None


def _choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((HOST, 0))
        return int(candidate.getsockname()[1])


def _write_state(state_file: Path, port: int) -> None:
    pending = state_file.with_suffix(".tmp")
    pending.write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")
    pending.replace(state_file)


def _open_browser_when_ready(port: int, attempts: int = 120) -> None:
    for _ in range(attempts):
        try:
            with urlopen(_health_url(port), timeout=0.25) as response:  # noqa: S310 - localhost only
                if response.status == 200:
                    webbrowser.open(_app_url(port), new=1)
                    return
        except (URLError, OSError, TimeoutError):
            time.sleep(0.25)


def _smoke_test_when_ready(port: int, result_file: Path, attempts: int = 120) -> None:
    """Exercise the bundled HTTP server, record the result, then end the test process."""

    result = {"healthy": False, "port": port}
    for _ in range(attempts):
        try:
            with urlopen(_health_url(port), timeout=0.5) as health:  # noqa: S310 - localhost only
                health_ok = health.status == 200 and health.read(32).strip().lower() == b"ok"
            with urlopen(_app_url(port), timeout=1.0) as page:  # noqa: S310 - localhost only
                page_ok = page.status == 200 and bool(page.read(256))
            if health_ok and page_ok:
                result["healthy"] = True
                break
        except (URLError, OSError, TimeoutError):
            time.sleep(0.25)
    result_file.write_text(json.dumps(result), encoding="utf-8")
    os._exit(0 if result["healthy"] else 3)


def _show_startup_error(message: str) -> None:
    try:
        from tkinter import messagebox

        messagebox.showerror("LexPilot 启动失败", message)
    except Exception:
        return


def main() -> int:
    smoke_test = "--smoke-test" in sys.argv[1:]
    resource_root = resolve_resource_root(Path(__file__), getattr(sys, "_MEIPASS", None))
    paths = configure_runtime(resolve_app_data_dir(), resource_root)
    logging.basicConfig(
        filename=paths.logs_dir / "lexpilot.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )

    existing_url = find_running_url(paths.state_file)
    if existing_url:
        if smoke_test:
            port = int(existing_url.rsplit(":", 1)[1])
            (paths.app_data_dir / "smoke-test.json").write_text(
                json.dumps({"healthy": True, "port": port}),
                encoding="utf-8",
            )
        else:
            webbrowser.open(existing_url, new=1)
        return 0

    app_script = resource_root / "app.py"
    if not app_script.is_file():
        message = f"找不到应用文件：{app_script}"
        logging.error(message)
        _show_startup_error(message)
        return 1

    port = _choose_port()
    _write_state(paths.state_file, port)
    os.chdir(resource_root)
    if smoke_test:
        Thread(
            target=_smoke_test_when_ready,
            args=(port, paths.app_data_dir / "smoke-test.json"),
            daemon=True,
        ).start()
    else:
        Thread(target=_open_browser_when_ready, args=(port,), daemon=True).start()

    try:
        from streamlit.web import cli as streamlit_cli

        sys.argv = [
            "streamlit",
            "run",
            str(app_script),
            f"--server.address={HOST}",
            f"--server.port={port}",
            "--server.headless=true",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
            "--global.developmentMode=false",
        ]
        result = streamlit_cli.main()
        return int(result or 0)
    except Exception as exc:
        logging.exception("LexPilot failed to start")
        _show_startup_error(f"LexPilot 无法启动。\n\n请查看日志：{paths.logs_dir / 'lexpilot.log'}\n\n{exc}")
        return 1
    finally:
        try:
            state = json.loads(paths.state_file.read_text(encoding="utf-8"))
            if int(state.get("pid", -1)) == os.getpid():
                paths.state_file.unlink(missing_ok=True)
        except (OSError, ValueError, json.JSONDecodeError):
            pass


if __name__ == "__main__":
    raise SystemExit(main())
