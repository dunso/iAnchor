"""Wan2.1 批量生成 — 管道加载一次, 处理多个 prompt"""
import json, os, sys, time, random
sys.path.insert(0, os.path.expanduser("~/code/git-hub/dunso/mlx-examples/video/wan2.1"))

import mlx.core as mx
import mlx.nn as nn
from wan import WanPipeline
from wan.utils import save_video
from tqdm import tqdm

def main():
    config_path = sys.argv[1]
    with open(config_path) as f:
        cfg = json.load(f)

    model = cfg.get("model", "t2v-1.3B")
    size = tuple(cfg.get("size", [624, 352]))
    frames = cfg.get("frames", 33)
    steps_per = cfg.get("steps", 20)
    guidance = cfg.get("guidance", 1.0)
    shift = cfg.get("shift", 5.0)
    quantize_bits = cfg.get("quantize", 8)
    teacache = cfg.get("teacache", 0.05)
    n_prompt = cfg.get("n_prompt", "")
    segments = cfg["segments"]

    mx.set_default_device(mx.gpu)

    print(f"[WAN-BATCH] 加载 {model} ...", flush=True)
    t0 = time.time()
    pipeline = WanPipeline(model)
    if quantize_bits:
        nn.quantize(pipeline.flow, bits=quantize_bits)
        print(f"[WAN-BATCH] 量化: {quantize_bits}-bit", flush=True)
    pipeline.ensure_models_are_loaded()
    print(f"[WAN-BATCH] 模型就绪 ({time.time()-t0:.0f}s)", flush=True)

    n = len(segments)
    for seg_i, seg in enumerate(segments):
        prompt = seg["prompt"]
        output_path = seg["output"]
        seed = seg.get("seed", random.randint(0, 2**31 - 1))
        seg_frames = seg.get("frames", frames)  # 按段定帧数
        label = f"{seg_i+1}/{n}"

        print(f"[WAN-{label}] {prompt[:80]}...", flush=True)
        t_seg = time.time()

        try:
            latents = pipeline.generate_latents(
                prompt, negative_prompt=n_prompt,
                size=size, frame_num=seg_frames, num_steps=steps_per,
                guidance=guidance, shift=shift, seed=seed, teacache=teacache,
            )
            conditioning = next(latents)
            mx.eval(conditioning)
            del pipeline.t5
            mx.clear_cache()

            for step_i, x_t in enumerate(tqdm(latents, total=steps_per, desc=label, leave=False)):
                mx.eval(x_t)
                if (step_i + 1) % 5 == 0 or step_i == steps_per - 1:
                    print(f"[WAN-{label}] 去噪 {step_i+1}/{steps_per} ({(time.time()-t_seg):.0f}s)", flush=True)

            del pipeline.flow
            mx.clear_cache()

            video = pipeline.decode(x_t)
            mx.eval(video)
            save_video(video, output_path)
            mx.clear_cache()
            elapsed = time.time() - t_seg
            print(f"[WAN-{label}] 完成 ({elapsed:.0f}s) -> {output_path}", flush=True)
            print(f"[WAN-DONE] {output_path}", flush=True)

        except Exception as e:
            print(f"[WAN-{label}] 错误: {e}", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()

        # 重建模型给下一段 (也包 try)
        if seg_i < n - 1:
            try:
                print(f"[WAN-BATCH] 重建模型 ({seg_i+2}/{n})...", flush=True)
                from wan.utils import load_dit, load_t5
                pipeline.flow = load_dit(model)
                pipeline.t5 = load_t5(model)
                if quantize_bits:
                    nn.quantize(pipeline.flow, bits=quantize_bits)
                mx.clear_cache()
                print(f"[WAN-BATCH] 模型重载完成", flush=True)
            except Exception as e:
                print(f"[WAN-BATCH] 重建模型失败: {e}", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                # 即使重建失败也继续尝试下一段
                continue

    del pipeline
    mx.clear_cache()
    print(f"[WAN-BATCH] 全部完成", flush=True)

if __name__ == "__main__":
    main()
