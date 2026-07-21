#!/usr/bin/env python3
"""Patch mlx-examples for SD 1.5 compatibility."""
import os, sys

sd_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/code/git-hub/dunso/mlx-examples")

SD_15_CONFIG = '''    "runwayml/stable-diffusion-v1-5": {
        "unet_config": "unet/config.json",
        "unet": "unet/diffusion_pytorch_model.safetensors",
        "text_encoder_config": "text_encoder/config.json",
        "text_encoder": "text_encoder/model.safetensors",
        "vae_config": "vae/config.json",
        "vae": "vae/diffusion_pytorch_model.safetensors",
        "diffusion_config": "scheduler/scheduler_config.json",
        "tokenizer_vocab": "tokenizer/vocab.json",
        "tokenizer_merges": "tokenizer/merges.txt",
    },
'''

BIN_LOADER = '''
def _load_bin_weights(mapper, model, weight_file, float16: bool = False):
    """Load PyTorch .bin weights and convert to MLX"""
    import torch
    import numpy as np
    dtype = mx.float16 if float16 else mx.float32
    pt = torch.load(weight_file, map_location="cpu", weights_only=True)
    mlx_weights = []
    for k, v in pt.items():
        mx_arr = mx.array(v.float().numpy()).astype(dtype)
        mlx_weights.extend(mapper(k, mx_arr))
    model.update(tree_unflatten(mlx_weights))
'''

OLD_LOAD = '''    weights = mx.load(weight_file)
    weights = _flatten([mapper(k, v.astype(dtype)) for k, v in weights.items()])
    model.update(tree_unflatten(weights))'''

NEW_LOAD = '''    if weight_file.endswith(".bin"):
        _load_bin_weights(mapper, model, weight_file, float16)
        return
    weights = mx.load(weight_file)
    mlx_weights = _flatten([mapper(k, v.astype(dtype)) for k, v in weights.items()])
    try:
        model.update(tree_unflatten(mlx_weights))
    except ValueError:
        valid, skipped = [], []
        for k, v in mlx_weights:
            try:
                model.update(tree_unflatten([(k, v)]))
                valid.append((k, v))
            except ValueError:
                skipped.append(k)
        model.update(tree_unflatten(valid))'''


def main():
    # 1. Replace model path in txt2image.py
    txt2img = os.path.join(sd_dir, "stable_diffusion", "txt2image.py")
    if os.path.exists(txt2img):
        t = open(txt2img).read()
        t = t.replace("stabilityai/stable-diffusion-2-1-base",
                       "runwayml/stable-diffusion-v1-5")
        open(txt2img, "w").write(t)

    # 2. Patch model_io.py
    mio = os.path.join(sd_dir, "stable_diffusion", "stable_diffusion",
                       "model_io.py")
    if not os.path.exists(mio):
        print(f"ERROR: {mio} not found")
        return

    t = open(mio).read()

    # Replace default model
    t = t.replace("stabilityai/stable-diffusion-2-1-base",
                   "runwayml/stable-diffusion-v1-5")

    # Add SD 1.5 config
    if "runwayml/stable-diffusion-v1-5" not in t.split('"stabilityai/sdxl-turbo"')[0]:
        t = t.replace('"stabilityai/sdxl-turbo": {',
                      SD_15_CONFIG + '    "stabilityai/sdxl-turbo": {')

    # Add bin loader
    if "_load_bin_weights" not in t:
        t = t.replace("def _load_safetensor_weights(",
                      BIN_LOADER + "\ndef _load_safetensor_weights(")

    # Update safetensor loader
    t = t.replace(OLD_LOAD, NEW_LOAD)

    open(mio, "w").write(t)
    print(f"Patched: {sd_dir}")


if __name__ == "__main__":
    main()
