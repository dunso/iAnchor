#!/bin/bash
# ============================================================
# iAnchor WebUI 启动脚本
# 用法: bash start_ui.sh [端口号]
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
PORT="${1:-7860}"

export IANCHOR_PORT="$PORT"

# 虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "未找到虚拟环境，正在安装..."
    bash install.sh
    source .venv/bin/activate
fi

# 确保 gradio 已安装
pip install gradio -q 2>/dev/null || pip install gradio

# Bark 模型检查
BARK_MODEL_DIR="$HOME/.cache/huggingface/hub/models--suno--bark"
if [ ! -d "$BARK_MODEL_DIR/snapshots" ] || [ -z "$(ls -A "$BARK_MODEL_DIR/snapshots" 2>/dev/null)" ]; then
    echo "正在下载 Bark 语音模型..."
    pip install -q huggingface_hub 2>/dev/null || true
    export HF_ENDPOINT=https://hf-mirror.com
    python3 -c "from huggingface_hub import snapshot_download; snapshot_download('suno/bark')"
fi

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl_cache}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
mkdir -p "$MPLCONFIGDIR" "$HF_HOME" 2>/dev/null

# 记录 PID
PIDFILE="/tmp/ianchor_webui.pid"

if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "WebUI 已在运行 (PID: $OLD_PID)，先停止: bash stop_ui.sh"
        exit 1
    fi
    rm -f "$PIDFILE"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║      🎬 iAnchor WebUI                        ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  地址: http://127.0.0.1:${PORT}                  ║"
echo "║  停止: bash stop_ui.sh                       ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 清除 Python 缓存，每回启动都是最新代码
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
python3 webui.py &
PID=$!
echo $PID > "$PIDFILE"
trap "kill $PID 2>/dev/null; rm -f $PIDFILE; exit 0" INT TERM
wait
