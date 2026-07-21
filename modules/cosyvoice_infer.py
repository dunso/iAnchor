#!/usr/bin/env python3
"""
CosyVoice 本地推理 (由 pipeline 通过 subprocess 调用)
用法: <cosyvoice_venv>/python cosyvoice_infer.py <文本> <输出wav> [参考wav] [参考文本]
"""
import os
import sys

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_cache")
os.makedirs("/tmp/numba_cache", exist_ok=True)

_COSYVOICE_HOME = os.path.expanduser("~/CosyVoice-mps")
_MATCHA = os.path.join(_COSYVOICE_HOME, "third_party", "Matcha-TTS")
if _MATCHA not in sys.path:
    sys.path.insert(0, _MATCHA)
if _COSYVOICE_HOME not in sys.path:
    sys.path.insert(0, _COSYVOICE_HOME)

text = sys.argv[1]
out_path = sys.argv[2]
ref_wav = sys.argv[3] if len(sys.argv) > 3 else ""
ref_text = sys.argv[4] if len(sys.argv) > 4 else ""

from cosyvoice.cli.cosyvoice import CosyVoice2
model_dir = os.path.join(_COSYVOICE_HOME, "pretrained_models", "CosyVoice2-0.5B")
cosyvoice = CosyVoice2(model_dir, load_jit=False, load_trt=False, fp16=False)

# 调试：打印可用音色
import sys
print(f"DEBUG: 可用音色: {list(cosyvoice.spk2info.keys())[:10]}", file=sys.stderr)

import torch, torchaudio

if ref_wav and os.path.exists(ref_wav):
    wav, sr = torchaudio.load(ref_wav)
    sr_val = int(sr)
    if wav.dim() > 1 and wav.shape[0] > 1:
        wav = wav.mean(dim=0, keepdim=True)
    if sr_val != 16000:
        wav = torchaudio.functional.resample(wav, sr_val, 16000)
    prompt = wav.squeeze(0).float()[:48000]
    output = list(cosyvoice.inference_zero_shot(text, ref_text or "你好", prompt))
else:
    # 使用第一个可用的音色
    available_speakers = list(cosyvoice.spk2info.keys())
    if available_speakers:
        speaker = available_speakers[0]
        print(f"DEBUG: 使用音色: {speaker}", file=sys.stderr)
        output = list(cosyvoice.inference_sft(text, speaker))
    else:
        raise RuntimeError("CosyVoice: 没有可用的预训练音色")

if output and len(output) > 0:
    sr, audio = output[0]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    torchaudio.save(out_path, audio.unsqueeze(0) if audio.dim() == 1 else audio, sr)
    print(f"OK {out_path}")
else:
    print("FAIL: no output")
    sys.exit(1)
