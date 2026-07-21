[English](README_EN.md) | **简体中文**

<h1 align="center">🎬 iAnchor</h1>

<p align="center"><strong>输入主题 + 素材 → 3 分钟后得到一条带数字人、字幕、数据卡片的竖屏口播视频。</strong></p>
<p align="center">全程 AI 驱动，零剪辑经验。新闻播报、知识科普、产品介绍、故事讲述——场景不限。</p>

<p align="center">
  <a href="https://github.com/dunso/iAnchor"><img src="https://img.shields.io/badge/platform-macOS%20Apple%20Silicon-orange"></a>
  <a href="https://github.com/dunso/iAnchor"><img src="https://img.shields.io/badge/python-3.13-blue"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="https://platform.deepseek.com"><img src="https://img.shields.io/badge/LLM-DeepSeek-536DFE"></a>
  <a href="https://github.com/rany2/edge-tts"><img src="https://img.shields.io/badge/TTS-Edge-0078D7"></a>
  <a href="https://github.com/TMElyralab/MuseTalk"><img src="https://img.shields.io/badge/Lip_Sync-MuseTalk-FF6B6B"></a>
  <a href="https://github.com/Tongyi-MAI/Z-Image"><img src="https://img.shields.io/badge/Avatar_Gen-Z--Image-8A2BE2"></a>
  <a href="https://gradio.app"><img src="https://img.shields.io/badge/WebUI-Gradio-FF7C00"></a>
  <a href="https://dunso.github.io/iAnchor"><img src="https://img.shields.io/badge/Homepage-d4a574"></a>
</p>

<p align="center"><img src="https://dunso.github.io/iAnchor/webui.png" width="85%"></p>

---

## 🎯 它做什么

> 你是一个内容创作者。每天要出 3 条口播视频。每条都要想稿子、录音、做字幕、加动画。一个人根本忙不过来。

> **iAnchor 把整条流水线自动化了。** 你输入主题和素材，剩下的事它来做。

```
输入："沪指涨 1.5% 报 3350 点，成交突破万亿"

  🤖 LLM 写稿  →  🧑 AI 形象  →  🗣️ TTS 配音  →  👄 唇形驱动  →  📊 数据卡片  →  📝 字幕叠加
                         ↓
            🎬 竖屏口播视频 (1080×1920)
```

---

## ✨ 功能

| 模块 | 做了什么 |
|------|---------|
| ✍️ **AI 写稿** | 主题 + 素材 → LLM 重组成流畅口播稿，云端 API / 本地 Ollama 可切换 |
| 🧑 **AI 主播形象** | 根据文案一键生成高清主播形象，本地 Z-Image-Turbo / 云端 API 双引擎，也可手动上传 |
| 🗣️ **语音合成** | Edge TTS 16 种音色，发音自然，试听满意再生成 |
| 👄 **唇形同步** | MuseTalk 音频驱动，嘴型精准对齐 |
| 📊 **动态卡片** | 价格、涨跌幅、成交量随口播自动切换，6 种布局轮换 |
| 📝 **逐句字幕** | 金黄字体 + 圆角背景 + 按标点拆分，一句一条 |
| 🎨 **4 种动画** | PPT 卡片 / Manim 数字动画 / SD AI 生图 / Remotion React |

---

## 🚀 5 行命令开始

```bash
git clone https://github.com/dunso/iAnchor.git && cd iAnchor
bash install.sh
export DEEPSEEK_API_KEY="sk-xxx"
cp your-photo.png input/avatar.png     # 可选：WebUI 里也能 AI 生成主播形象
bash start_ui.sh        # 打开 http://127.0.0.1:7860
```

---

## 💻 兼容性

| 平台 | 写稿 | 语音 | 唇形 | 动画 | SD | AI 形象 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|
| macOS M1–M4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| macOS Intel | ✅ | ✅ | ✅ | ✅ | ❌ | ☁️ |
| Windows | ✅ | ✅ | ❌ | ✅ | ❌ | ☁️ |
| Linux | ✅ | ✅ | ✅ | ✅ | ❌ | ☁️ |

> ☁️ = 本地 mflux 仅支持 Apple Silicon，其余平台走云端 API

---

## 🎨 动画四种

| 模式 | 效果 | 推荐场景 |
|------|------|---------|
| **card** `默认` | PPT 卡片，6 布局轮换 | 数据播报、产品介绍 |
| **manim** | 数字滚动 + 过渡动画 | 高级感动画 |
| **sd** | MLX SD 1.5 文生图 | AI 艺术风格 |
| **remotion** | React 组件渲染 | 可深度定制 |

---

## 🧑 主播形象

上传照片，或在 WebUI 选「AI 生成」让 AI 根据文案设计主播（正面、演播室风格，直接可用于唇形驱动）：

| 方式 | 引擎 | 准备 |
|------|------|------|
| 本地 mflux `默认` | Z-Image-Turbo (6B, MLX) | `uv tool install mflux` + 下载模型 |
| 云端 API | FLUX.1-schnell / CogView 等 | `export IMAGE_API_KEY=sk-xxx` |

```bash
# 本地模型下载（一次即可，约 7GB）
export HF_ENDPOINT=https://hf-mirror.com    # 国内加速，可选
export HF_HUB_DISABLE_XET=1                 # 用镜像时必加，镜像不支持 Xet 协议
.venv/bin/hf download filipstrand/Z-Image-Turbo-mflux-4bit --exclude "*.DS_Store"
```

---

## 🔧 换个 LLM

```yaml
# 本地 Ollama
llm:
  provider: "ollama"
  model: "qwen2.5:7b"

# 智谱 GLM-5.2
llm:
  provider: "deepseek"
  deepseek_api_base: "https://open.bigmodel.cn/api/paas/v4"
  deepseek_api_key: "你的Key"
  model: "glm-5.2"
```

---

## 📁 结构

```
iAnchor/
├── install.sh        ← 一键安装
├── start_ui.sh       ← 启动 WebUI
├── webui.py          ← Gradio 界面
├── pipeline.py       ← 主编排脚本
├── modules/
│   ├── llm_script.py          ← LLM 口播稿
│   ├── avatar_image_gen.py    ← AI 主播形象 (mflux/API)
│   ├── tts_generator.py       ← Edge TTS
│   ├── avatar_driver.py       ← MuseTalk 唇形
│   ├── viz_animation.py       ← 4 种动画
│   ├── subtitle_generator.py  ← 字幕
│   └── video_composer.py      ← FFmpeg 合成
├── input/   ← 头像 (可选)
└── output/  ← 产物
```

---

## 📄 License

MIT © iAnchor
