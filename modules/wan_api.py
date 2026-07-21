"""
Wan2.1 Replicate API 视频生成模块
云端调用 wan-video/wan-2.5-t2v-fast, 快速高质量
"""

import logging
import os
import random
import urllib.request

logger = logging.getLogger(__name__)


def _extract_visual_prompt(script: str, title: str = "") -> str:
    """从口播稿提取英文 visual prompt (复用同逻辑)"""
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
    return f"{base}, cinematic lighting, 4K quality, smooth camera movement"


class WanApiGenerator:
    """Replicate Wan2.5 T2V API 生成器"""

    def __init__(self, config: dict):
        cfg = config.get("wan_api", {})
        self.api_token = cfg.get("api_token", "") or os.environ.get("REPLICATE_API_TOKEN", "")
        if not self.api_token:
            logger.warning("[WanAPI] Replicate token 未配置")
        self.model = cfg.get("model", "wan-video/wan-2.5-t2v-fast")
        w, h = cfg.get("size", [1072, 384])
        self.size = (w, h)
        self.frames = cfg.get("frames", 33)

    def generate_batch(self, segments: list[tuple],
                        on_clip_done=None) -> list[tuple[str, str]]:
        """
        批量生成 - 每段一个 API 调用, 并行提交
        segments: [(prompt, output_path, frames?), ...]
        """
        import replicate

        client = replicate.Client(api_token=self.api_token)
        n = len(segments)
        logger.info(f"[WanAPI] 批量提交 {n} 段到 Replicate")

        # 并行提交所有任务
        futures = []
        for i, item in enumerate(segments):
            prompt = item[0]
            path = item[1]
            frames = item[2] if len(item) > 2 else self.frames
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            logger.info(f"[WanAPI {i+1}/{n}] 提交: {prompt[:60]}...")
            input_data = {
                "prompt": prompt,
                "width": self.size[0],
                "height": self.size[1],
                "num_frames": frames,
            }
            try:
                future = client.predictions.async_create(
                    model=self.model, input=input_data
                )
                futures.append((i, path, future))
            except Exception as e:
                logger.error(f"[WanAPI {i+1}/{n}] 提交失败: {e}")
                futures.append((i, path, None))

        # 等待完成
        results: list[tuple[str, str]] = [("", "pending")] * n
        completed = 0
        for idx, path, future in futures:
            label = f"{idx+1}/{n}"
            if future is None:
                results[idx] = (path, "submission failed")
                logger.error(f"[WanAPI {label}] 提交失败, 跳过")
                continue
            logger.info(f"[WanAPI {label}] 等待完成...")
            try:
                output = client.predictions.wait(future)
                if output and output.output:
                    # 下载视频
                    video_url = output.output
                    if isinstance(video_url, list):
                        video_url = video_url[0]
                    urllib.request.urlretrieve(video_url, path)
                    results[idx] = (path, "")
                    completed += 1
                    if on_clip_done:
                        on_clip_done(path)
                    logger.info(f"[WanAPI {label}] 完成")
                else:
                    results[idx] = (path, "no output from API")
                    logger.error(f"[WanAPI {label}] 无输出")
            except Exception as e:
                results[idx] = (path, str(e))
                logger.error(f"[WanAPI {label}] 失败: {e}")

        logger.info(f"[WanAPI] 全部完成: {completed}/{n}")
        return results

    def generate(self, prompt: str, output_path: str) -> str:
        results = self.generate_batch([(prompt, output_path)])
        path, err = results[0]
        if err:
            raise RuntimeError(f"WanAPI 生成失败: {err}")
        return path
