from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.build_manual_release_archives import (
    iter_macos_source_files,
    write_bytes,
)


def test_macos_source_archive_excludes_private_and_build_data(tmp_path: Path) -> None:
    for relative in (
        "app.py",
        "backend/graph.py",
        "static/site.css",
        ".streamlit/config.toml",
        ".env",
        ".local_data/case.txt",
        "release/package.zip",
        "tests/test_app.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")

    selected = {path.relative_to(tmp_path).as_posix() for path in iter_macos_source_files(tmp_path)}

    assert "app.py" in selected
    assert "backend/graph.py" in selected
    assert "static/site.css" in selected
    assert ".streamlit/config.toml" in selected
    assert ".env" not in selected
    assert ".local_data/case.txt" not in selected
    assert "release/package.zip" not in selected
    assert "tests/test_app.py" not in selected


def test_command_files_keep_executable_permission_in_zip(tmp_path: Path) -> None:
    archive = tmp_path / "mac.zip"
    with zipfile.ZipFile(archive, "w") as output:
        write_bytes(output, "LexPilot/安装 LexPilot.command", b"#!/bin/bash\n", executable=True)

    with zipfile.ZipFile(archive) as packaged:
        info = packaged.getinfo("LexPilot/安装 LexPilot.command")
        mode = (info.external_attr >> 16) & 0o777
        assert info.create_system == 3
        assert mode == 0o755

