#!/bin/bash
# Bark TTS 试听界面 一键启动
cd "$(dirname "$0")"
source .venv/bin/activate
export HF_ENDPOINT=https://hf-mirror.com
echo "启动中... 浏览器打开 http://127.0.0.1:7860"
python tts_demo.py
