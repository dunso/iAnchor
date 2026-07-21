#!/bin/bash
# ============================================================
# iAnchor 一键安装 — 四种动画模式全部就绪
# 用法: bash install.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
step(){ echo -e "${CYAN}[$1]${NC} $2"; }
ok(){ echo -e "   ${GREEN}V${NC} $1"; }
warn(){ echo -e "   ${YELLOW}!${NC}  $1"; }
fail(){ echo -e "   ${RED}X $1${NC}"; }

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}   iAnchor (card+manim+sd+remotion)${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# ===========================================================
# 1. brew
# ===========================================================
step "1/8" "brew ..."
need_brew=false
for cmd in ffmpeg node python3.13; do
    command -v "$cmd" &>/dev/null && ok "$cmd" || { fail "$cmd"; need_brew=true; }
done
command -v latex &>/dev/null && ok "latex (manim)" || warn "latex (brew install --cask mactex-no-gui)"
if $need_brew; then
    command -v brew &>/dev/null || { fail "install Homebrew: https://brew.sh"; exit 1; }
    command -v python3.13 &>/dev/null || brew install python@3.13
    command -v ffmpeg &>/dev/null      || brew install ffmpeg
    command -v node &>/dev/null        || brew install node
fi

# ===========================================================
# 2. Python venv + core
# ===========================================================
step "2/8" "Python venv + core deps ..."
PYTHON=""
for p in python3.13 python3.12 python3.11; do
    command -v "$p" &>/dev/null && { PYTHON="$p"; break; }
done
[ -z "$PYTHON" ] && { fail "Python 3.11+"; exit 1; }

rm -rf .venv
$PYTHON -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q 2>/dev/null || true
pip install edge-tts gradio pyyaml matplotlib pillow numpy scipy requests openai moviepy -q 2>&1 | tail -1
ok "card"

# ===========================================================
# 3. Manim
# ===========================================================
step "3/8" "Manim ..."
pip install manim -q 2>&1 | tail -1
command -v latex &>/dev/null && ok "manim" || warn "manim (need latex)"

# ===========================================================
# 4. Remotion
# ===========================================================
step "4/8" "Remotion ..."
RE_DIR="$SCRIPT_DIR/modules/remotion_viz"
if command -v node &>/dev/null; then
    cd "$RE_DIR" && npm install --silent 2>&1 | tail -1 && cd "$SCRIPT_DIR"
    ok "remotion"
else
    fail "remotion (no node)"
fi

# ===========================================================
# 5. MLX SD
# ===========================================================
step "5/8" "MLX SD ..."
SD_DIR="${MLX_DIR:-$HOME/code/git-hub/dunso/mlx-examples}"

if [ ! -d "$SD_DIR" ]; then
    mkdir -p "$(dirname "$SD_DIR")"
    git clone https://github.com/ml-explore/mlx-examples "$SD_DIR" 2>&1 | tail -1
fi

if [ ! -d "$SD_DIR/.venv" ]; then
    python3.13 -m venv "$SD_DIR/.venv" 2>/dev/null || true
    "$SD_DIR/.venv/bin/pip" install -r "$SD_DIR/stable_diffusion/requirements.txt" -q 2>&1 | tail -1
    "$SD_DIR/.venv/bin/pip" install torch -q 2>&1 | tail -1
fi

# Patch: SD 2.1->1.5 + .bin + skip unknown params
PATCH="$SCRIPT_DIR/scripts/patch_mlx_sd.py"
if [ -f "$PATCH" ]; then
    "$PYTHON" "$PATCH" "$SD_DIR" 2>/dev/null && ok "sd" || warn "sd patch failed"
else
    ok "sd (code)"
fi

# ===========================================================
# 6. MuseTalk 数字人
# ===========================================================
step "6/8" "MuseTalk ..."
MT_DIR="${MUSETALK_DIR:-$HOME/code/git-hub/dunso/musetalk-mac}"
if [ -d "$MT_DIR" ]; then
    ok "museTalk found"
else
    warn "MuseTalk 未安装, 数字人不可用"
    warn "  安装: git clone https://github.com/TMElyralab/MuseTalk $MT_DIR"
    warn "  然后按项目 README 装依赖和模型"
fi
# Ensure /tmp model cache
if [ -d "$MT_DIR/upstream" ] && [ ! -d "/tmp/MuseTalk/upstream" ]; then
    mkdir -p /tmp/MuseTalk
    cp -r "$MT_DIR/upstream" /tmp/MuseTalk/ 2>/dev/null && ok "models cached" || true
fi

# ===========================================================
# 7. mflux (AI 形象生成, 可选)
# ===========================================================
step "7/8" "mflux (AI avatar gen) ..."
UV_BIN="$(command -v uv || true)"
[ -z "$UV_BIN" ] && [ -x "$HOME/.local/bin/uv" ] && UV_BIN="$HOME/.local/bin/uv"
if command -v mflux-generate-z-image-turbo &>/dev/null || [ -x "$HOME/.local/bin/mflux-generate-z-image-turbo" ]; then
    ok "mflux"
elif [ -n "$UV_BIN" ]; then
    "$UV_BIN" tool install mflux 2>&1 | tail -1 && ok "mflux" || warn "mflux install failed"
else
    warn "uv 未安装, AI 形象生成不可用 (可选功能)"
    warn "  安装: brew install uv && uv tool install mflux"
fi
# Z-Image 模型仅检测, 不自动下载 (~7GB)
ZIMG_CACHE="${HF_HOME:-$HOME/.cache/huggingface}/hub/models--filipstrand--Z-Image-Turbo-mflux-4bit"
if [ -d "$ZIMG_CACHE" ]; then
    ok "Z-Image-Turbo model"
else
    warn "Z-Image 模型未下载 (~7GB), 需要 AI 生成形象时执行:"
    warn "  .venv/bin/hf download filipstrand/Z-Image-Turbo-mflux-4bit"
fi

# ===========================================================
# 8. Config
# ===========================================================
step "8/8" "Config ..."
[ ! -f "config.yaml" ] && cp config.example.yaml config.yaml && ok "config.yaml"
mkdir -p input output

# ===========================================================
# Done
# ===========================================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   Done! 4 modes ready${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "card     V"
echo "manim    $(command -v latex &>/dev/null && echo V || echo '(need latex)')"
echo "remotion $(command -v node &>/dev/null && echo V || echo '(need node)')"
echo "sd       V"
echo "museTalk $([ -d "$MT_DIR" ] && echo V || echo '(need clone)')"
echo "mflux    $( (command -v mflux-generate-z-image-turbo &>/dev/null || [ -x "$HOME/.local/bin/mflux-generate-z-image-turbo" ]) && echo V || echo '(optional)')"
echo ""
echo "Setup:"
echo "  1. LLM key:  edit config.yaml -> deepseek_api_key"
echo "  2. HF token:  export HF_TOKEN=hf_xxx  (only sd mode)"
echo "  3. Avatar:    put image at input/avatar.png, or use WebUI 'AI 生成'"
echo "  4. AI avatar model (optional, ~7GB):"
echo "     .venv/bin/hf download filipstrand/Z-Image-Turbo-mflux-4bit"
echo ""
echo "  WebUI: bash start_ui.sh"
echo "  CLI:   bash run.sh 'text...'"
echo ""
