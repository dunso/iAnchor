**English** | [简体中文](README.md)

<h1 align="center">🎬 iAnchor</h1>

<p align="center"><strong>Drop in a topic + data — get a vertical video with a digital human, subtitles, and animated data cards in 3 minutes.</strong></p>
<p align="center">Fully AI-driven. Zero editing skills. News, tutorials, product intros, storytelling — any niche.</p>

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

## 🎯 What It Does

> You're a content creator. Three videos a day. Each needs a script, voiceover, subtitles, and animation. By yourself, it's impossible.

> **iAnchor automates the entire pipeline.** Drop in your topic and materials — it handles the rest.

```
Input: "Shanghai Composite rose 1.5% to close at 3350, volume broke 1 trillion"

  🤖 Script  →  🧑 AI Avatar  →  🗣️ Voice  →  👄 Lip Sync  →  📊 Cards  →  📝 Subtitles
                         ↓
            🎬 Vertical Video (1080×1920)
```

---

## ✨ Features

| Module | What It Does |
|--------|-------------|
| ✍️ **AI Scripting** | Topic + data → fluent narration. Cloud API / local Ollama switchable |
| 🧑 **AI Anchor Avatar** | HD anchor portrait generated from your script. Local Z-Image-Turbo / cloud API, manual upload supported |
| 🗣️ **TTS Voice** | Microsoft Edge TTS, 16 voices, natural pronunciation |
| 👄 **Lip Sync** | MuseTalk audio-driven, precise mouth-to-voice alignment |
| 📊 **Dynamic Cards** | Price, change%, volume auto-switch with narration across 6 layouts |
| 📝 **Sentence Subtitles** | Gold text + rounded pill background, split by punctuation |
| 🎨 **4 Visual Modes** | PPT Cards / Manim / SD AI Images / Remotion React |

---

## 🚀 5-Command Start

```bash
git clone https://github.com/dunso/iAnchor.git && cd iAnchor
bash install.sh
export DEEPSEEK_API_KEY="sk-xxx"
cp your-photo.png input/avatar.png     # Optional: generate an AI avatar in WebUI instead
bash start_ui.sh        # Open http://127.0.0.1:7860
```

---

## 💻 Compatibility

| Platform | Script | Voice | Lip Sync | Cards | SD | AI Avatar |
|----------|:--:|:--:|:--:|:--:|:--:|:--:|
| macOS M1–M4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| macOS Intel | ✅ | ✅ | ✅ | ✅ | ❌ | ☁️ |
| Windows | ✅ | ✅ | ❌ | ✅ | ❌ | ☁️ |
| Linux | ✅ | ✅ | ✅ | ✅ | ❌ | ☁️ |

> ☁️ = local mflux is Apple Silicon only; other platforms use the cloud API

---

## 🎨 Visual Modes

| Mode | Style | Best For |
|------|-------|----------|
| **card** `default` | PPT cards, 6 layouts | Data broadcast, product intro |
| **manim** | Number animation + transitions | Premium feel |
| **sd** | MLX SD 1.5 image gen | Artistic style |
| **remotion** | React rendering | Deep customization |

---

## 🧑 Anchor Avatar

Upload a photo, or pick "AI Generate" in the WebUI to design an anchor from your script (front-facing, studio style, lip-sync ready):

| Mode | Engine | Setup |
|------|--------|-------|
| Local mflux `default` | Z-Image-Turbo (6B, MLX) | `uv tool install mflux` + download model |
| Cloud API | FLUX.1-schnell / CogView etc. | `export IMAGE_API_KEY=sk-xxx` |

```bash
# One-time model download (~7GB)
.venv/bin/hf download filipstrand/Z-Image-Turbo-mflux-4bit --exclude "*.DS_Store"
```

---

## 🔧 Swap LLM

```yaml
# Local Ollama
llm:
  provider: "ollama"
  model: "qwen2.5:7b"

# Zhipu GLM-5.2
llm:
  provider: "deepseek"
  deepseek_api_base: "https://open.bigmodel.cn/api/paas/v4"
  deepseek_api_key: "your-key"
  model: "glm-5.2"
```

---

## 📁 Structure

```
iAnchor/
├── install.sh        ← One-click setup
├── start_ui.sh       ← Launch WebUI
├── webui.py          ← Gradio interface
├── pipeline.py       ← Main pipeline
├── modules/
│   ├── llm_script.py          ← LLM scripting
│   ├── avatar_image_gen.py    ← AI anchor avatar (mflux/API)
│   ├── tts_generator.py       ← Edge TTS
│   ├── avatar_driver.py       ← MuseTalk lip sync
│   ├── viz_animation.py       ← 4 visual engines
│   ├── subtitle_generator.py  ← Subtitles
│   └── video_composer.py      ← FFmpeg composition
├── input/   ← Avatar (optional)
└── output/  ← Videos
```

---

## 📄 License

MIT © iAnchor
