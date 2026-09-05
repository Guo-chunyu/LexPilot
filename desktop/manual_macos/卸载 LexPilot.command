#!/bin/bash
set -euo pipefail

APP_HOME="$HOME/Library/Application Support/LexPilot"
APP_BUNDLE="$HOME/Applications/LexPilot.app"

echo "这会删除 LexPilot、运行环境、设置以及保存在本机的全部案件材料。"
read -r -p "输入 DELETE 后按回车确认卸载：" answer
if [[ "$answer" != "DELETE" ]]; then
  echo "已取消。"
  exit 0
fi

pkill -f "$APP_HOME/runtime/.venv/bin/python.*desktop.launcher" 2>/dev/null || true
rm -rf "$APP_BUNDLE" "$APP_HOME"
echo "LexPilot 已卸载。"
read -r -p "按回车键关闭窗口……" _
