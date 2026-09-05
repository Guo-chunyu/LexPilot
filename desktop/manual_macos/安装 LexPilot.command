#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/LexPilot-source"
APP_HOME="$HOME/Library/Application Support/LexPilot"
APP_DIR="$APP_HOME/app"
RUNTIME_DIR="$APP_HOME/runtime"
VENV_DIR="$RUNTIME_DIR/.venv"
USER_APPS="$HOME/Applications"
APP_BUNDLE="$USER_APPS/LexPilot.app"
UV_BIN="$RUNTIME_DIR/bin/uv"
UV_VERSION="0.12.10"

pause_on_error() {
  status=$?
  if [[ $status -ne 0 ]]; then
    echo
    echo "安装没有完成。请保留本窗口中的错误信息。"
    read -r -p "按回车键关闭窗口……" _
  fi
  exit "$status"
}
trap pause_on_error EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "这个安装程序只能在 macOS 上运行。"
  exit 2
fi
if [[ ! -f "$SOURCE_DIR/app.py" ]]; then
  echo "安装包不完整：找不到 LexPilot-source/app.py。请重新解压完整 ZIP。"
  exit 3
fi

echo "LexPilot 律策安装程序"
echo "======================"
echo "首次安装需要联网下载独立 Python 环境和运行依赖。"
echo

mkdir -p "$APP_HOME" "$RUNTIME_DIR/bin" "$USER_APPS"
if [[ ! -x "$UV_BIN" ]]; then
  echo "[1/4] 下载独立运行环境管理器……"
  curl --proto '=https' --tlsv1.2 -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" \
    | env UV_UNMANAGED_INSTALL="$RUNTIME_DIR/bin" sh
else
  echo "[1/4] 已找到运行环境管理器。"
fi

echo "[2/4] 安装 Python 3.12 和 LexPilot 依赖……"
export UV_PYTHON_INSTALL_DIR="$RUNTIME_DIR/python"
"$UV_BIN" python install 3.12
"$UV_BIN" venv --python 3.12 --clear "$VENV_DIR"

echo "[3/4] 安装应用文件……"
rm -rf "$APP_DIR"
ditto "$SOURCE_DIR" "$APP_DIR"
"$UV_BIN" pip install --python "$VENV_DIR/bin/python" -r "$APP_DIR/desktop/requirements-runtime.txt"

echo "[4/4] 创建 LexPilot.app……"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"
cat > "$APP_BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key><string>LexPilot 律策</string>
  <key>CFBundleExecutable</key><string>LexPilot</string>
  <key>CFBundleIdentifier</key><string>com.lexpilot.manual</string>
  <key>CFBundleName</key><string>LexPilot</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
cat > "$APP_BUNDLE/Contents/MacOS/LexPilot" <<'LAUNCHER'
#!/bin/bash
APP_HOME="$HOME/Library/Application Support/LexPilot"
cd "$APP_HOME/app" || exit 1
exec "$APP_HOME/runtime/.venv/bin/python" -m desktop.launcher
LAUNCHER
chmod 755 "$APP_BUNDLE/Contents/MacOS/LexPilot"

trap - EXIT
echo
echo "安装完成：$APP_BUNDLE"
echo "LexPilot 即将启动，日后可在个人‘应用程序’文件夹中双击打开。"
open "$APP_BUNDLE"
read -r -p "按回车键关闭安装窗口……" _
