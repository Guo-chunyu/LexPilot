#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-0.1.0-dev}"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)*$ ]]; then
  echo "Invalid version: $VERSION" >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "$PROJECT_ROOT"

if [[ "${SKIP_DEPENDENCIES:-0}" != "1" ]]; then
  "$PYTHON_BIN" -m pip install -r desktop/requirements-desktop.txt
fi

export LEXPILOT_VERSION="$VERSION"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean desktop/lexpilot.spec

ARCH="$($PYTHON_BIN -c 'import platform; print(platform.machine())')"
case "$ARCH" in
  arm64) PACKAGE_ARCH="Apple-Silicon-arm64" ;;
  x86_64) PACKAGE_ARCH="Intel-x64" ;;
  *) echo "Unsupported macOS architecture: $ARCH" >&2; exit 3 ;;
esac

mkdir -p release
STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lexpilot-dmg.XXXXXX")"
trap 'rm -rf "$STAGE_DIR"' EXIT
ditto dist/LexPilot.app "$STAGE_DIR/LexPilot.app"
cp desktop/首次打开说明.txt "$STAGE_DIR/首次打开说明.txt"
ln -s /Applications "$STAGE_DIR/Applications"

OUTPUT="release/LexPilot-macOS-${PACKAGE_ARCH}-unsigned.dmg"
hdiutil create -volname "LexPilot 律策" -srcfolder "$STAGE_DIR" -ov -format UDZO "$OUTPUT"
echo "$PROJECT_ROOT/$OUTPUT"
