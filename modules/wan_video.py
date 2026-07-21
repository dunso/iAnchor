"""
Wan2.1 MLX 视频生成模块 — Apple Silicon 原生
文字 → AI 视频片段 (人物/建筑/场景)
管道复用: 一次子进程批量处理所有片段
"""

import json
import logging
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_WAN_DIR = os.path.expanduser("~/code/git-hub/dunso/mlx-examples/video/wan2.1")
_WAN_VENV = os.path.expanduser("~/code/git-hub/dunso/mlx-examples/.venv/bin/python3")
_BATCH_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wan_batch.py")
if _WAN_DIR not in sys.path:
    sys.path.insert(0, _WAN_DIR)


def _extract_visual_prompt(script: str, title: str = "") -> str:
    """从口播稿中提取适合视频生成的英文 visual prompt"""
    up_scenes = [
        "bull market trading floor with green charts rising, professional traders celebrating, bright upbeat atmosphere",
        "stock prices soaring upward, green arrows flying through modern financial district, skyscrapers with digital displays showing gains",
        "prosperous city skyline at golden hour, upward trending data lines, confident business people walking",
    ]
    down_scenes = [
        "stormy weather over financial district, red downward charts, traders looking concerned at screens",
        "dark clouds over city skyline, falling stock graphs, tense atmosphere in trading room",
        "rainy night in business district, red downward arrows on digital billboards, cautious investors watching markets",
    ]
    neutral_scenes = [
        "busy trading room with multiple screens showing financial data, professional analysts working, dynamic energy",
        "modern city landscape with data visualizations floating in air, technology and finance merging",
        "sleek financial news studio with holographic charts and graphs, professional broadcast atmosphere",
    ]

    up_kw = ["涨", "升", "上扬", "反弹", "突破", "新高", "牛市", "飘红", "攀升", "走强", "利好"]
    down_kw = ["跌", "下", "回落", "承压", "跌破", "新低", "熊市", "翻绿", "下滑", "走弱", "利空"]

    text = script + (title or "")
    if any(k in text for k in up_kw):
        base = random.choice(up_scenes)
    elif any(k in text for k in down_kw):
        base = random.choice(down_scenes)
    else:
        base = random.choice(neutral_scenes)

    topic = (title or script[:60]).strip()
    if any('\u4e00' <= c <= '\u9fff' for c in topic):
        all_scenes = up_scenes + down_scenes + neutral_scenes
        base = random.choice(all_scenes)

    return f"{base}, cinematic lighting, 4K quality, smooth camera movement"


class WanVideoGenerator:
    """Wan2.1 视频生成器 — 批量管道复用"""

    def __init__(self, config: dict):
        cfg = config.get("wan_video", {})
        self.model = cfg.get("model", "t2v-1.3B")
        w, h = cfg.get("size", (624, 352))
        self.size = list((w, h))
        self.frames = cfg.get("frames", 33)
        self.steps = cfg.get("steps", 20)
        self.guidance = cfg.get("guidance", 1.0)
        self.shift = cfg.get("shift", 5.0)
        self.quantize = cfg.get("quantize", 8)
        self.teacache = cfg.get("teacache", 0.05)
        self.n_prompt = cfg.get(
            "n_prompt", "Text, watermarks, blurry image, JPEG artifacts, low quality, distorted, ugly"
        )
        self.seed_val = cfg.get("seed", None)
        self.timeout = cfg.get("timeout", 3600)

    def generate_batch(self, segments: list[tuple],
                        on_clip_done=None) -> list[tuple[str, str]]:
        """
        批量生成 — 一次子进程, 管道加载一次复用到所有段
        segments: [(prompt, output_path, frames?), ...] frames 可选, 默认用全局配置
        on_clip_done: 每段完成后回调 on_clip_done(path)
        返回: [(output_path, error_or_empty), ...]
        """
        # 构建 JSON 配置
        seg_data = []
        for item in segments:
            prompt = item[0]
            path = item[1]
            frames = item[2] if len(item) > 2 else self.frames
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            seed = self.seed_val if self.seed_val is not None else random.randint(0, 2**31 - 1)
            seg_data.append({"prompt": prompt, "output": path, "seed": seed, "frames": frames})

        batch_config = {
            "model": self.model,
            "size": self.size,
            "frames": self.frames,
            "steps": self.steps,
            "guidance": self.guidance,
            "shift": self.shift,
            "quantize": self.quantize,
            "teacache": self.teacache,
            "n_prompt": self.n_prompt,
            "segments": seg_data,
        }

        config_path = os.path.join(tempfile.mkdtemp(), "wan_batch.json")
        with open(config_path, "w") as f:
            json.dump(batch_config, f)

        n = len(segments)
        logger.info(f"[Wan2.1] 批量生成 {n} 段, 管道复用, guidance={self.guidance}")
        self._ensure_batch_script()

        # 调用批量脚本
        cmd = [_WAN_VENV, _BATCH_SCRIPT, config_path]
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        try:
            last_log = [0.0]
            def _stream():
                for line in iter(process.stdout.readline, ""):
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("[WAN-DONE]") and on_clip_done:
                        path = line.split("] ", 1)[-1].strip()
                        on_clip_done(path)
                        continue
                    if "[WAN-" in line or time.time() - last_log[0] >= 3.0:
                        logger.info(f"{line}")
                        last_log[0] = time.time()
            t = threading.Thread(target=_stream, daemon=True)
            t.start()
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error(f"Wan2.1 批量超时 (>{self.timeout}s)")
                raise
            finally:
                try:
                    process.stdout.close()
                except Exception:
                    pass
                t.join(timeout=360000)

            if process.returncode != 0:
                logger.error(f"Wan2.1 子进程异常退出, exit={process.returncode}")
        finally:
            # 清理临时配置
            try:
                os.unlink(config_path)
            except Exception:
                pass

        # 收集结果
        results = []
        for i, (_, path) in enumerate(segments):
            if os.path.isfile(path) and os.path.getsize(path) > 1024:
                results.append((path, ""))
            else:
                results.append((path, f"segment {i+1} no valid output"))
        return results

    def generate(self, prompt: str, output_path: str,
                 image_path: str = "", label: str = "",
                 seg_frames: int = None) -> str:
        """单段生成 (兼容旧接口)"""
        item = (prompt, output_path)
        if seg_frames is not None:
            item = (prompt, output_path, seg_frames)
        results = self.generate_batch([item])
        path, err = results[0]
        if err:
            raise RuntimeError(f"Wan2.1 生成失败: {err}")
        if not os.path.isfile(path) or os.path.getsize(path) < 1024:
            raise RuntimeError(f"Wan2.1 未产出有效视频: {path}")
        return path

    @staticmethod
    def _ensure_batch_script():
        """确保批量脚本存在且为最新版本"""
        with open(_BATCH_SCRIPT, "w") as f:
            f.write(_BATCH_SCRIPT_CONTENT)
        os.chmod(_BATCH_SCRIPT, 0o755)

_BATCH_SCRIPT_CONTENT = '''"""Wan2.1 批量生成 — 管道加载一次, 处理多个 prompt"""
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
'''
