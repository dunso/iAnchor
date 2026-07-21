#!/bin/bash
# ============================================================
# iAnchor WebUI 重启脚本
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
bash stop_ui.sh
sleep 1
bash start_ui.sh "$@"
