"""
阿里百炼 Wan2.x 视频生成 API 模块
DashScope 异步接口: POST 提交 → GET 轮询 → 下载视频
"""

import json
import logging
import os
import random
import time
import urllib.request

logger = logging.getLogger(__name__)


def _extract_visual_prompt(script: str, title: str = "") -> str:
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


class BailianGenerator:
    """阿里百炼 Wan2.x 视频生成器"""

    def __init__(self, config: dict):
        cfg = config.get("bailian", {})
        self.api_key = cfg.get("api_key", "") or os.environ.get("DASHSCOPE_API_KEY", "")
        if not self.api_key:
            logger.warning("[百炼] API key 未配置")
        self.base_url = cfg.get(
            "base_url",
            "https://dashscope.aliyuncs.com/api/v1",
        ).rstrip("/")
        self.model = cfg.get("model", "wan2.7-t2v-2026-06-12")
        self.resolution = cfg.get("resolution", "720P")
        self.ratio = cfg.get("ratio", "16:9")
        self.watermark = cfg.get("watermark", False)
        self.prompt_extend = cfg.get("prompt_extend", True)
        self.duration = cfg.get("duration", 5)  # 默认5秒
        self.max_poll = cfg.get("max_poll", 120)
        self.poll_interval = cfg.get("poll_interval", 10)

    def generate_batch(self, segments: list[tuple],
                        on_clip_done=None) -> list[tuple[str, str]]:
        """
        批量生成 - 每段提交异步任务, 轮询下载
        segments: [(prompt, output_path, duration?), ...] duration 为秒数
        """
        n = len(segments)
        logger.info(f"[百炼] 批量提交 {n} 段")

        # 提交所有任务
        task_ids: list[tuple[int, str, str]] = []
        for i, item in enumerate(segments):
            prompt = item[0]
            path = item[1]
            seg_duration = item[2] if len(item) > 2 else self.duration
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

            logger.info(f"[百炼 {i+1}/{n}] 提交: {prompt[:60]}...")
            task_id = self._submit_task(prompt, seg_duration)
            if task_id:
                task_ids.append((i, path, task_id))
            else:
                logger.error(f"[百炼 {i+1}/{n}] 提交失败")

        # 轮询等待
        results: list[tuple[str, str]] = [("", "not submitted")] * n
        remaining = list(task_ids)

        for poll in range(self.max_poll):
            if not remaining:
                break
            time.sleep(self.poll_interval)

            still_waiting = []
            for idx, path, task_id in remaining:
                video_url = self._poll_task(task_id)
                if video_url:
                    try:
                        urllib.request.urlretrieve(video_url, path)
                        results[idx] = (path, "")
                        if on_clip_done:
                            on_clip_done(path)
                        logger.info(f"[百炼 {idx+1}/{n}] 完成")
                    except Exception as e:
                        results[idx] = (path, str(e))
                        logger.error(f"[百炼 {idx+1}/{n}] 下载失败: {e}")
                elif video_url is False:
                    results[idx] = (path, "task failed")
                    logger.error(f"[百炼 {idx+1}/{n}] 任务失败")
                else:
                    still_waiting.append((idx, path, task_id))
            remaining = still_waiting

            total_done = sum(1 for _, e in results if not e)
            if total_done > 0 and total_done < n:
                logger.info(f"[百炼] 进度: {total_done}/{n}, 等待中 {len(remaining)}")

        if remaining:
            for idx, path, task_id in remaining:
                results[idx] = (path, f"timeout after {self.max_poll} polls")
                logger.error(f"[百炼 {idx+1}/{n}] 超时")

        completed = sum(1 for _, e in results if not e)
        logger.info(f"[百炼] 全部完成: {completed}/{n}")
        return results

    def _submit_task(self, prompt: str, duration: int) -> str | None:
        """提交生成任务, 返回 task_id"""
        if not self.api_key:
            logger.error("[百炼] 未配置 API key, 跳过提交")
            return None
        # 确保 duration 在 [2, 15] 范围内
        dur = max(2, min(duration, 15))
        data = {
            "model": self.model,
            "input": {
                "prompt": prompt,
            },
            "parameters": {
                "resolution": self.resolution,
                "ratio": self.ratio,
                "duration": dur,
                "prompt_extend": self.prompt_extend,
                "watermark": self.watermark,
                "seed": random.randint(0, 2147483647),
            },
        }
        try:
            req = urllib.request.Request(
                f"{self.base_url}/services/aigc/video-generation/video-synthesis",
                data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=360000)
            body = json.loads(resp.read())
            task_id = body.get("output", {}).get("task_id")
            if task_id:
                logger.info(f"[百炼] 任务已创建: {task_id[:8]}...")
                return task_id
            logger.error(f"[百炼] 提交失败: {json.dumps(body, ensure_ascii=False)[:300]}")
        except Exception as e:
            err_body = ""
            if hasattr(e, "read"):
                try:
                    err_body = e.read().decode()[:500]
                except Exception:
                    pass
            logger.error(f"[百炼] 提交异常: {e} | {err_body}")
        return None

    def _poll_task(self, task_id: str) -> str | None | bool:
        """轮询任务, 返回 video_url 或 None(进行中) 或 False(失败)"""
        try:
            req = urllib.request.Request(
                f"{self.base_url}/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                },
            )
            resp = urllib.request.urlopen(req, timeout=360000)
            body = json.loads(resp.read())
            output = body.get("output", {})
            status = output.get("task_status")
            if status == "SUCCEEDED":
                return output.get("video_url")
            elif status in ("FAILED", "CANCELED"):
                code = output.get("code", "")
                msg = output.get("message", "")
                logger.error(f"[百炼] 任务失败 {task_id[:8]}: {code} {msg}")
                return False
            # PENDING / RUNNING
            return None
        except Exception as e:
            logger.debug(f"[百炼] 轮询异常 {task_id[:8]}: {e}")
            return None

    def generate(self, prompt: str, output_path: str) -> str:
        results = self.generate_batch([(prompt, output_path)])
        path, err = results[0]
        if err:
            raise RuntimeError(f"百炼 生成失败: {err}")
        return path
