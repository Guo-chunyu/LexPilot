"""Build two ZIP files that can be uploaded manually to a GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import os
import zipfile
from pathlib import Path


ROOT_FILES = {
    "app.py",
    "consultation_workspace.py",
    "evidence_constellation.py",
    "frontend_experience.py",
    "LICENSE",
}
SOURCE_DIRS = {
    "backend",
    "static",
    "data",
    ".streamlit",
}
DESKTOP_FILES = {
    "desktop/__init__.py",
    "desktop/launcher.py",
    "desktop/requirements-runtime.txt",
}
EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".local_data",
    ".venv",
    "build",
    "dist",
    "release",
    "tests",
    ".git",
}


def iter_macos_source_files(root: Path):
    """Yield only runtime source and public data needed by the Mac bootstrap package."""

    root = Path(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        posix = relative.as_posix()
        if any(part in EXCLUDED_PARTS for part in parts):
            continue
        if path.suffix in {".pyc", ".pyo"} or path.name == ".env":
            continue
        if posix in ROOT_FILES or posix in DESKTOP_FILES:
            yield path
            continue
        if parts[0] in SOURCE_DIRS:
            yield path
            continue
        if len(parts) >= 2 and parts[0] == "datasets" and parts[1] == "synthetic_cases":
            yield path


def write_bytes(
    archive: zipfile.ZipFile,
    archive_name: str,
    content: bytes,
    *,
    executable: bool = False,
) -> None:
    info = zipfile.ZipInfo(archive_name)
    info.create_system = 3
    mode = 0o755 if executable else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, content)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_archives(root: Path, version: str) -> tuple[Path, Path]:
    root = Path(root).resolve()
    release_dir = root / "release"
    release_dir.mkdir(exist_ok=True)
    installer = release_dir / "LexPilot-Windows-x64-Setup-unsigned.exe"
    if not installer.is_file():
        raise FileNotFoundError(f"Build the Windows installer first: {installer}")

    windows_zip = release_dir / f"LexPilot-Windows-v{version}-unsigned.zip"
    windows_folder = f"LexPilot-Windows-v{version}"
    with zipfile.ZipFile(windows_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        output.write(installer, f"{windows_folder}/{installer.name}")
        output.write(root / "desktop" / "首次打开说明.txt", f"{windows_folder}/首次打开说明.txt")
        checksum = f"{sha256(installer)}  {installer.name}\n".encode("ascii")
        write_bytes(output, f"{windows_folder}/SHA256SUMS.txt", checksum)

    mac_zip = release_dir / f"LexPilot-macOS-v{version}-unsigned.zip"
    mac_folder = f"LexPilot-macOS-v{version}"
    manual_dir = root / "desktop" / "manual_macos"
    with zipfile.ZipFile(mac_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name in ("安装 LexPilot.command", "卸载 LexPilot.command"):
            write_bytes(
                output,
                f"{mac_folder}/{name}",
                (manual_dir / name).read_bytes(),
                executable=True,
            )
        output.write(manual_dir / "Mac首次安装说明.txt", f"{mac_folder}/Mac首次安装说明.txt")
        for source in iter_macos_source_files(root):
            relative = source.relative_to(root).as_posix()
            output.write(source, f"{mac_folder}/LexPilot-source/{relative}")

    return windows_zip, mac_zip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    for archive in build_archives(root, args.version):
        print(f"{archive} ({archive.stat().st_size / 1024 / 1024:.2f} MB, SHA256={sha256(archive)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
