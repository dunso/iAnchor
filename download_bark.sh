#!/bin/bash
# ============================================================
# Bark TTS 模型预下载脚本
# 用法: bash download_bark.sh
#
# 说明:
#   - 下载 suno/bark 模型到本地 (~4GB 压缩 / ~20GB 解压)
#   - 使用 HuggingFace 国内镜像加速
#   - 模型缓存到 ~/.cache/huggingface/hub/
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      🎙  Bark TTS 模型下载                  ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ─── 虚拟环境 ────────────────────────────────────────────
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo -e "${GREEN}✓${NC} 已激活虚拟环境"
else
    echo -e "${YELLOW}⚠${NC}  虚拟环境不存在，请先运行: bash install.sh"
    exit 1
fi

# ─── 安装 huggingface_hub ─────────────────────────────────
echo ""
echo -e "${CYAN}[1/3]${NC} 安装 huggingface_hub ..."
pip install -q huggingface_hub 2>/dev/null || pip install huggingface_hub
echo -e "   ${GREEN}✓${NC} 完成"

# ─── 检查已下载 ──────────────────────────────────────────
MODEL_DIR="$HOME/.cache/huggingface/hub/models--suno--bark"
if [ -d "$MODEL_DIR/snapshots" ] && [ "$(ls -A "$MODEL_DIR/snapshots" 2>/dev/null)" ]; then
    echo ""
    echo -e "${YELLOW}⚠${NC}  模型似乎已下载过，位于: $MODEL_DIR"
    echo "  如需重新下载，请先删除该目录后重试。"
    echo ""
    echo -e "${GREEN}✅ 模型已就绪，可以直接使用！${NC}"
    exit 0
fi

# ─── 下载 ─────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[2/3]${NC} 下载 Bark 模型 (suno/bark) ..."
echo "  模型大小: ~4GB (压缩), ~20GB (解压后)"
echo "  下载可能需要 5-30 分钟，取决于网络速度。"
echo "  使用 HuggingFace 国内镜像 (hf-mirror.com) 加速。"
echo ""

export HF_ENDPOINT=https://hf-mirror.com

python3 -c "
import sys
from huggingface_hub import snapshot_download

print('开始下载 suno/bark ...')
try:
    snapshot_download('suno/bark')
    print('✅ Bark 模型下载完成')
except Exception as e:
    print(f'❌ 下载失败: {e}', file=sys.stderr)
    print('', file=sys.stderr)
    print('请尝试:', file=sys.stderr)
    print('  1. 检查网络连接', file=sys.stderr)
    print('  2. 手动下载: https://huggingface.co/suno/bark', file=sys.stderr)
    print('  3. 如在国内，设置 HF_ENDPOINT=https://hf-mirror.com', file=sys.stderr)
    sys.exit(1)
"

echo ""
echo -e "${CYAN}[3/3]${NC} 验证模型 ..."
if [ -d "$MODEL_DIR" ]; then
    SIZE=$(du -sh "$MODEL_DIR" 2>/dev/null | cut -f1)
    echo -e "   ${GREEN}✓${NC} 模型路径: $MODEL_DIR"
    echo -e "   ${GREEN}✓${NC} 占用空间: $SIZE"
else
    echo -e "   ${RED}❌ 模型目录不存在，下载可能未成功${NC}"
    exit 1
fi

# ─── 完成 ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      ✅ Bark 模型下载完成！                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "现在可以生成高质量中文语音了："
echo "  bash run.sh '沪指收涨1.5%报3350点...'"
echo ""
