"""
字幕生成模块
按标点拆分，逐句展示，金黄字体 + 透明背景
"""

import json
import logging
import os
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """字幕生成器 — 逐句拆分，金黄字体，透明背景"""

    def __init__(self, config: dict):
        cfg = config.get("subtitle", {})
        video_cfg = config.get("video", {})
        self.font_name = cfg.get("font", "Microsoft YaHei")
        self.font = self._resolve_font_path(self.font_name)
        self.font_size = cfg.get("font_size", 44)
        self.font_color = cfg.get("font_color", "#FFD700")       # 金黄
        self.stroke_color = cfg.get("stroke_color", "#1a1a2e")    # 深色描边
        self.stroke_width = cfg.get("stroke_width", 3)
        self.position = cfg.get("position", "bottom")
        self.bottom_margin = cfg.get("bottom_margin", 0.12)
        self.max_chars_per_line = cfg.get("max_chars_per_line", 24)
        self.video_width = video_cfg.get("width", 1080)
        self.video_height = video_cfg.get("height", 1920)
        self.video_fps = video_cfg.get("fps", 30)

    @staticmethod
    def _resolve_font_path(font_name: str) -> str:
        """解析字体路径，优先粗体"""
        import platform
        if platform.system() == "Darwin":
            candidates = [
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "/Library/Fonts/Arial Unicode.ttf",
            ]
            for path in candidates:
                if os.path.exists(path):
                    logger.info(f"字幕字体: {path}")
                    return path
        logger.warning(f"未找到字体 {font_name}，使用默认")
        return font_name

    # ─── 按标点拆分为短句 ──────────────────────────

    @staticmethod
    def split_by_punctuation(text: str) -> list[str]:
        """按标点符号拆分，每句干净短小，去掉末尾标点"""
        parts = re.split(r"(?<=[。！？；\n])\s*", text)
        result = []
        for part in parts:
            sub = re.split(r"(?<=[，、：,])\s*", part)
            for s in sub:
                s = s.strip()
                if s:
                    # 去掉末尾标点
                    s = re.sub(r"[，。！？；：、,\.\!\?\;\:\n]+$", "", s)
                    if s.strip():
                        result.append(s.strip())
        return result

    # ─── SRT 生成 ──────────────────────────────────

    def generate_srt(self, timestamps: list[dict], output_path: str) -> str:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        for i, ts in enumerate(timestamps, 1):
            start = ts.get("start", 0)
            end = ts.get("end", 0)
            text = ts.get("text", "").strip()
            text = re.sub(r"[，。！？；：、,\.\!\?\;\:\n]+$", "", text)
            if not text:
                continue

            start_str = self._format_time(start)
            end_str = self._format_time(end)

            lines.append(str(i))
            lines.append(f"{start_str} --> {end_str}")
            lines.append(text)
            lines.append("")

        content = "\n".join(lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"generate_srt 开始: {len(timestamps)} 条 -> {output_path}")
        logger.info(f"SRT: {output_path} ({len(timestamps)} 条)")
        return str(output_path)

    # ─── 字幕视频片段（金黄字体 + 透明背景）───────

    def generate_subtitle_clip(self, timestamps: list[dict],
                               duration: float, output_path: str) -> str:
        try:
            from moviepy import TextClip, CompositeVideoClip, ImageClip
        except ImportError:
            logger.warning("MoviePy 不可用")
            return ""

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"generate_subtitle_clip 开始: {len(timestamps)} 条, {duration:.1f}s")
        # 字幕缓存: 内容+样式哈希
        import hashlib
        sub_data = json.dumps([{"t": t.get("text",""), "s": t.get("start",0), "e": t.get("end",0)} for t in timestamps], ensure_ascii=False, sort_keys=True)
        sub_cache_key = hashlib.md5(f"{sub_data}|{duration:.1f}|{self.font_size}|{self.font_color}|{self.video_width}|{self.video_height}|{self.video_fps}".encode()).hexdigest()[:16]
        sub_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "subtitle")
        os.makedirs(sub_cache_dir, exist_ok=True)
        sub_cached = os.path.join(sub_cache_dir, f"sub_{sub_cache_key}.mp4")
        if os.path.isfile(sub_cached) and os.path.getsize(sub_cached) > 1024:
            logger.info(f"字幕缓存命中: {sub_cache_key}")
            shutil.copy2(sub_cached, output_path)
            return str(output_path)

        logger.info(f"字幕生成: {len(timestamps)} 条...")
        clips = []
        for ts in timestamps:
            text = ts.get("text", "").strip()
            text = re.sub(r"[，。！？；：、,\.\!\?\;\:\n]+$", "", text)
            if not text:
                continue
            start = ts.get("start", 0)
            end = ts.get("end", duration)
            seg_duration = max(end - start, 0.5)

            try:
                txt_clip = TextClip(
                    text=text,
                    font=self.font,
                    font_size=self.font_size,
                    color=self.font_color,
                    stroke_color=self.stroke_color,
                    stroke_width=self.stroke_width,
                    method="label",
                )

                # 半透明圆角背景 pill
                pad_x, pad_y = 40, 18
                bw, bh = txt_clip.w + pad_x * 2, txt_clip.h + pad_y * 2
                bg_img = self._make_rounded_rect(bw, bh, radius=22,
                                                  color=(10, 10, 20, 160))
                import numpy as np
                bg_clip = ImageClip(np.array(bg_img), duration=seg_duration)

                comp = CompositeVideoClip(
                    [bg_clip, txt_clip.with_position(("center", pad_y))],
                    size=(bw, bh),
                )

                y_pos = int(self.video_height * (1 - self.bottom_margin) - bh)
                y_pos = max(20, y_pos)
                comp = (comp
                    .with_position(("center", y_pos))
                    .with_start(start)
                    .with_duration(seg_duration))

                clips.append(comp)
            except Exception as e:
                logger.warning(f"字幕创建失败 ({start}-{end}): {e}")
                continue

        if not clips:
            logger.warning("无有效字幕片段")
            return ""

        try:
            composite = CompositeVideoClip(
                clips, size=(self.video_width, self.video_height)
            )
            logger.info(f"字幕编码中 ({len(clips)} 段)...")
            composite.write_videofile(
                str(output_path),
                fps=self.video_fps,
                codec="libx264",
                logger=None,
            )
            # 存入字幕缓存
            try:
                shutil.copy2(output_path, sub_cached)
            except Exception as e:
                logger.debug(f"字幕缓存写入失败(无影响): {e}")
            logger.info(f"generate_subtitle_clip 完成: {output_path}")
            return str(output_path)
        except Exception as e:
            logger.error(f"字幕合成失败: {e}")
            return ""

    @staticmethod
    def _make_rounded_rect(w: int, h: int, radius: int,
                           color: tuple) -> "PIL.Image":
        """PIL 绘制圆角矩形，4 通道 RGBA"""
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([(0, 0), (w - 1, h - 1)],
                               radius=radius, fill=color)
        return img

    # ─── 工具 ──────────────────────────────────────

    @staticmethod
    def _format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _wrap_text(self, text: str) -> str:
        """按 max_chars_per_line 换行"""
        if len(text) <= self.max_chars_per_line:
            return text
        lines = []
        remaining = text
        while len(remaining) > self.max_chars_per_line:
            cut = self.max_chars_per_line
            for i in range(self.max_chars_per_line,
                           max(0, self.max_chars_per_line - 6), -1):
                if i < len(remaining) and remaining[i - 1] in "，。！？；：、,":
                    cut = i
                    break
            lines.append(remaining[:cut])
            remaining = remaining[cut:].lstrip("，。！？；：、,")
        if remaining:
            lines.append(remaining)
        return "\n".join(lines)

    # ─── 时间戳生成 ───────────────────────────────

    def generate_srt_from_segments(self, segments: list[dict],
                                   audio_duration: float) -> list[dict]:
        """从口播稿生成时间戳，按标点拆短句"""
        logger.info(f"generate_srt_from_segments 开始: {len(segments)} segs, {audio_duration:.1f}s")
        # 先按标点拆成短句
        all_text = "".join(seg.get("text", "") for seg in segments)
        phrases = self.split_by_punctuation(all_text)

        total_len = sum(len(p) for p in phrases)
        if total_len == 0:
            return []

        timestamps = []
        current = 0.0
        for phrase in phrases:
            seg_duration = (len(phrase) / total_len) * audio_duration
            timestamps.append({
                "start": round(current, 2),
                "end": round(current + seg_duration, 2),
                "text": phrase,
            })
            current += seg_duration

        return timestamps

