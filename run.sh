#!/bin/bash
# ============================================================
# iAnchor 一键运行 — 自动检测、自动修复、直接出片
# 用法: bash run.sh "口播文本"
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── 解析参数 ──────────────────────────────────────────────
IMAGE=""
TEXT=""
SKIP_LLM=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--image) IMAGE="$2"; shift 2 ;;
        -t|--text)  TEXT="$2"; shift 2 ;;
        --skip-llm) SKIP_LLM="--skip-llm"; shift ;;
        -h|--help)
            echo "用法: bash run.sh [选项] <口播文本>"
            echo "  -i  图片路径 (默认自动检测 input/ 目录)"
            echo "  --skip-llm  跳过 AI 写稿"
            exit 0 ;;
        *) TEXT="$1"; shift ;;
    esac
done

if [ -z "$TEXT" ]; then
    echo "❌ 请提供口播文本:  bash run.sh '今天沪指收涨1.5%...'"
    exit 1
fi

# ─── 自动检测图片 ──────────────────────────────────────────
if [ -z "$IMAGE" ]; then
    for f in input/avatar.png input/avatar.jpg input/avatar.jpeg; do
        [ -f "$f" ] && IMAGE="$f" && break
    done
fi
if [ -z "$IMAGE" ] || [ ! -f "$IMAGE" ]; then
    echo "❌ 未找到图片，请放入 input/ 目录:  cp 你的照片.png input/avatar.png"
    exit 1
fi

# ─── 虚拟环境 ──────────────────────────────────────────────
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "未找到虚拟环境，正在自动安装..."
    bash "$SCRIPT_DIR/install.sh"
    source .venv/bin/activate
fi

# ─── 自动检查并修复 Bark ───────────────────────────────────
echo ""
echo "🔍 检查 Bark TTS ..."

# 1. suno-bark 包
if ! python3 -c "import bark" 2>/dev/null; then
    echo "   安装 suno-bark ..."
    pip install suno-bark scipy -q 2>/dev/null || pip install suno-bark scipy
fi

# 2. Bark 模型文件
BARK_MODEL_DIR="$HOME/.cache/huggingface/hub/models--suno--bark"
if [ ! -d "$BARK_MODEL_DIR/snapshots" ] || [ -z "$(ls -A "$BARK_MODEL_DIR/snapshots" 2>/dev/null)" ]; then
    echo "   下载 Bark 语音模型 (~20GB，仅首次)..."
    pip install -q huggingface_hub 2>/dev/null || true
    export HF_ENDPOINT=https://hf-mirror.com
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('suno/bark')
"
    echo "   ✅ Bark 模型下载完成"
else
    echo "   ✅ Bark 已就绪"
fi

# ─── 验证 Bark 能正常加载 ─────────────────────────────────
if ! python3 -c "
import os, numpy as np, torch
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')
torch.serialization.add_safe_globals([np.core.multiarray.scalar])
_orig = torch.load
torch.load = lambda *a, **kw: _orig(*a, **{**kw, 'weights_only': False})
from bark import preload_models
preload_models()
" 2>/dev/null; then
    echo "❌ Bark 模型加载失败，请检查后重试"
    exit 1
fi
echo "   ✅ Bark 加载成功"
echo ""

# ─── 环境变量 ──────────────────────────────────────────────
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl_cache}"
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
mkdir -p "$MPLCONFIGDIR" "$HF_HOME" 2>/dev/null

# ─── 运行 ───────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════╗"
echo "║      🎬 iAnchor · 开始生成                  ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

python3 pipeline.py \
    --image "$IMAGE" \
    --text "$TEXT" \
    $SKIP_LLM \
    --verbose

# ─── 结果 ───────────────────────────────────────────────────
FINAL=$(ls -t output/*/final_output.mp4 2>/dev/null | head -1)
echo ""
if [ -n "$FINAL" ]; then
    echo "🎉 视频已生成: $FINAL"
else
    echo "⚠️  未找到输出视频，请检查上方日志"
fi
