#!/usr/bin/env python3
"""Bark 音色试听网站"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import gradio as gr
import numpy as np
from bark import SAMPLE_RATE, generate_audio, preload_models

VOICES = [
    ("中文_0 (男)", "v2/zh_speaker_0"), ("中文_1 (男)", "v2/zh_speaker_1"),
    ("中文_2 (男)", "v2/zh_speaker_2"),     ("中文_3 (女)", "v2/zh_speaker_3"),
    ("中文_4 (女)", "v2/zh_speaker_4"), ("中文_5 (男)", "v2/zh_speaker_5"),
    ("中文_6 (女)", "v2/zh_speaker_6"), ("中文_7 (女)", "v2/zh_speaker_7"),
    ("中文_8 (男)", "v2/zh_speaker_8"), ("中文_9 (女)", "v2/zh_speaker_9"),
    ("英文男_6", "v2/en_speaker_6"), ("英文男_7", "v2/en_speaker_7"),
]

print("加载 Bark 模型...")
# PyTorch 2.6 兼容：Bark 老模型需要 weights_only=False
import torch
import numpy as np
torch.serialization.add_safe_globals([np.core.multiarray.scalar])
_orig_load = torch.load
torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, 'weights_only': False})
try:
    preload_models()
finally:
    torch.load = _orig_load

def tts(text, voice_idx):
    voice = VOICES[int(voice_idx)][1]
    audio = generate_audio(text, history_prompt=voice)
    return (SAMPLE_RATE, audio.astype(np.float32))

with gr.Blocks(title="Bark 音色试听") as demo:
    gr.Markdown("# 🎙 Bark TTS 音色试听")
    with gr.Row():
        text = gr.Textbox(label="输入文本", value="沪指收涨1.5%，报3350点，成交额突破万亿。", lines=3)
    with gr.Row():
        voice = gr.Radio(
            choices=[(v[0], i) for i, v in enumerate(VOICES)],
            value=3, label="音色"
        )
        speed = gr.Slider(0.5, 2.0, value=1.3, label="语速")
    btn = gr.Button("生成试听", variant="primary")
    audio_out = gr.Audio(label="试听")

    def gen(text, voice_idx, speed):
        audio = tts(text, voice_idx)
        # 加速处理
        if speed != 1.0:
            import subprocess, tempfile
            tmp_in = os.path.join(tempfile.gettempdir(), "bark_tmp.wav")
            tmp_out = os.path.join(tempfile.gettempdir(), "bark_spd.wav")
            from scipy.io.wavfile import write
            write(tmp_in, SAMPLE_RATE, audio[1])
            subprocess.run(["ffmpeg", "-y", "-i", tmp_in, "-af", f"atempo={speed}",
                           "-ar", "16000", tmp_out], capture_output=True)
            from scipy.io.wavfile import read
            sr, data = read(tmp_out)
            return (sr, data.astype(np.float32) / 32768.0)
        return audio

    btn.click(gen, [text, voice, speed], audio_out)

demo.launch(server_name="0.0.0.0", server_port=7860, share=False)
