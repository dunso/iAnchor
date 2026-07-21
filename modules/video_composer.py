"""
视频合成模块
将可视化动画、数字人口播视频、字幕合成为最终竖屏视频

布局:
- 顶部 25%: 可视化行情动画
- 中间 55%: 数字人口播视频
- 底部 20%: 字幕区域
"""

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VideoComposer:
    """视频合成器 — 多轨道合成最终竖屏视频"""

    def __init__(self, config: dict):
        cfg = config.get("video", {})
        self.width = cfg.get("width", 1080)
        self.height = cfg.get("height", 1920)
        self.fps = cfg.get("fps", 30)
        self.viz_ratio = cfg.get("viz_height_ratio", 0.25)
        self.avatar_ratio = cfg.get("avatar_height_ratio", 0.55)
        self.subtitle_ratio = cfg.get("subtitle_height_ratio", 0.20)
        self.codec = cfg.get("codec", "libx264")
        self.bitrate = cfg.get("bitrate", "8M")
        self.audio_codec = cfg.get("audio_codec", "aac")
        self.audio_bitrate = cfg.get("audio_bitrate", "192k")
        self.margin_top = cfg.get("margin_top", 130)
        self.margin_bottom = cfg.get("margin_bottom", 160)

    def compose_with_moviepy(self, viz_video: str, avatar_video: str,
                              subtitle_clip: str, audio_path: str,
                              output_path: str,
                              cover_video: str = "",
                              cover_dur: float = 1.5) -> str:
        """
        使用 FFmpeg 合成最终视频 (可靠，无 MoviePy 兼容问题)

        布局: viz (顶部 25%) + avatar (中间 55%) → 竖屏 1080x1920
        """
        logger.info(f"compose_with_moviepy 开始: viz={os.path.basename(viz_video)}, avatar={os.path.basename(avatar_video)}")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 获取音频时长
        duration = 10.0
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True, timeout=360000,
            )
            duration = float(result.stdout.strip())
        except Exception:
            logger.debug("ffprobe 失败, 默认10s")
        logger.info(f"合成参数: {self.width}x{self.height}, {duration:.0f}s")

        viz_h = int(self.height * self.viz_ratio)

        # 确保视频时长至少为 1 秒
        safe_duration = max(duration, 1.0)
        if safe_duration > duration:
            logger.debug(f"音频时长 {duration:.1f}s 太短，使用最小时长 1s")

        if avatar_video and os.path.exists(avatar_video):
            if cover_video and os.path.exists(cover_video):
                logger.info(f"compose_with_moviepy: 叠加封面 {os.path.basename(cover_video)}, 持续 {cover_dur}s")
                filter_complex = (
                    f"[1:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[av];"
                    f"[0:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{viz_h}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{viz_h}:(ow-iw)/2:(oh-ih)/2:black@0[viz];"
                    f"[3:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{viz_h}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{viz_h}:(ow-iw)/2:(oh-ih)/2:black@0[cover];"
                    f"[viz][cover]overlay=0:0:enable='between(t,0,{cover_dur})'[viz_with_cover];"
                    f"[av][viz_with_cover]overlay=0:{self.margin_top}[vout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1", "-i", viz_video,
                    "-stream_loop", "-1", "-i", avatar_video,
                    "-i", audio_path,
                    "-stream_loop", "-1", "-i", cover_video,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-map", "2:a",
                    "-c:v", self.codec,
                    "-b:v", self.bitrate,
                    "-c:a", self.audio_codec,
                    "-b:a", self.audio_bitrate,
                    "-t", str(safe_duration),
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ]
            else:
                filter_complex = (
                    f"[1:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[av];"
                    f"[0:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{viz_h}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{viz_h}:(ow-iw)/2:(oh-ih)/2:black@0[viz];"
                    f"[av][viz]overlay=0:{self.margin_top}[vout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1", "-i", viz_video,
                    "-stream_loop", "-1", "-i", avatar_video,
                    "-i", audio_path,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-map", "2:a",
                    "-c:v", self.codec,
                    "-b:v", self.bitrate,
                    "-c:a", self.audio_codec,
                    "-b:a", self.audio_bitrate,
                    "-t", str(safe_duration),
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ]
        else:
            logger.info("compose_with_moviepy: 无数字人视频，全屏 viz")
            if cover_video and os.path.exists(cover_video):
                filter_complex = (
                    f"[0:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[viz];"
                    f"[2:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[cover];"
                    f"[viz][cover]overlay=0:0:enable='between(t,0,{cover_dur})'[vout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1", "-i", viz_video,
                    "-i", audio_path,
                    "-stream_loop", "-1", "-i", cover_video,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-map", "1:a",
                    "-c:v", self.codec,
                    "-b:v", self.bitrate,
                    "-c:a", self.audio_codec,
                    "-b:a", self.audio_bitrate,
                    "-t", str(safe_duration),
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ]
            else:
                filter_complex = (
                    f"[0:v]fps={self.fps},setsar=1,"
                    f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
                    f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[vout]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1", "-i", viz_video,
                    "-i", audio_path,
                    "-filter_complex", filter_complex,
                    "-map", "[vout]",
                    "-map", "1:a",
                    "-c:v", self.codec,
                    "-b:v", self.bitrate,
                    "-c:a", self.audio_codec,
                    "-b:a", self.audio_bitrate,
                    "-t", str(safe_duration),
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ]

        logger.info("compose_with_moviepy: ffmpeg 合成启动...")
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            def _stream():
                for line in iter(process.stdout.readline, ""):
                    line = line.rstrip("\n")
                    if line:
                        logger.info(f"[compose] {line}")
            t = threading.Thread(target=_stream, daemon=True)
            t.start()
            logger.info(f"[compose] ffmpeg PID={process.pid}, 等待完成...")
            process.wait(timeout=360000)
            t.join(timeout=10)
            if process.returncode != 0:
                logger.error(f"[compose] ffmpeg 退出码={process.returncode}")
                raise subprocess.CalledProcessError(process.returncode, cmd)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg 合成失败: exit={e.returncode}")
            raise

        # 字幕叠加 (colorkey 过滤黑色背景，避免黑底遮盖画面)
        if subtitle_clip and os.path.exists(subtitle_clip) and subtitle_clip.endswith(".mp4"):
            temp_out = str(output_path).replace(".mp4", "_sub.mp4")
            overlay_cmd = [
                "ffmpeg", "-y",
                "-i", str(output_path),
                "-i", subtitle_clip,
                "-filter_complex",
                "[1:v]colorchannelmixer=aa=1,"
                "colorkey=0x000000:0.01:0.01[sub];"
                "[0:v][sub]overlay=0:0:shortest=1",
                "-c:v", self.codec,
                "-c:a", "copy",
                temp_out,
            ]
            logger.info("compose_with_moviepy: 字幕叠加启动...")
            try:
                process2 = subprocess.Popen(overlay_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                def _stream2():
                    for line in iter(process2.stdout.readline, ""):
                        line = line.rstrip("\n")
                        if line:
                            logger.info(f"[subtitle_overlay] {line}")
                t2 = threading.Thread(target=_stream2, daemon=True)
                t2.start()
                logger.info(f"[subtitle_overlay] ffmpeg PID={process2.pid}")
                process2.wait(timeout=360000)
                t2.join(timeout=10)
                if process2.returncode != 0:
                    logger.warning(f"[subtitle_overlay] ffmpeg 退出码={process2.returncode}")
                os.replace(temp_out, str(output_path))
                logger.info("字幕视频已叠加")
            except Exception as e:
                logger.warning(f"字幕叠加失败: {e}")

        logger.info(f"最终视频合成完成: {output_path}")
        return str(output_path)

    def compose_with_ffmpeg(self, viz_video: str, avatar_video: str,
                            subtitle_srt: str, audio_path: str,
                            output_path: str) -> str:
        """
        使用 FFmpeg 合成最终视频 (MoviePy 不可用时的回退方案)

        Args:
            viz_video: 可视化动画视频
            avatar_video: 数字人口播视频
            subtitle_srt: SRT 字幕文件
            audio_path: 音频文件
            output_path: 输出路径

        Returns:
            输出路径
        """
        logger.info("使用 FFmpeg 合成最终视频...")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        viz_h = int(self.height * self.viz_ratio)
        avatar_h = int(self.height * self.avatar_ratio)

        # FFmpeg filter_complex 链
        filter_parts = []

        # 输入 0: viz, 输入 1: avatar
        filter_parts.append(f"[0:v]scale={self.width}:{viz_h}:force_original_aspect_ratio=1,"
                           f"pad={self.width}:{viz_h}:(ow-iw)/2:(oh-ih)/2[viz]")

        filter_parts.append(f"[1:v]scale={self.width}:{avatar_h}:force_original_aspect_ratio=1,"
                           f"pad={self.width}:{avatar_h}:(ow-iw)/2:(oh-ih)/2[avatar]")

        # 叠加: viz 在顶部，avatar 在中间
        filter_parts.append(f"[viz][avatar]vstack=inputs=2:shortest=1[stacked]")

        # 最终缩放到目标尺寸
        filter_parts.append(f"[stacked]scale={self.width}:{self.height}:"
                           f"force_original_aspect_ratio=1,"
                           f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2[vout]")

        filter_complex = ";".join(filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", viz_video,
            "-i", avatar_video,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "2:a",
            "-c:v", self.codec,
            "-b:v", self.bitrate,
            "-c:a", self.audio_codec,
            "-b:a", self.audio_bitrate,
            "-shortest",
            "-pix_fmt", "yuv420p",
        ]

        # 如果有字幕文件，添加字幕
        if subtitle_srt and os.path.exists(subtitle_srt):
            # 需要在 filter_complex 中添加字幕
            # 重新构建
            filter_parts[-1] = filter_parts[-1].replace(
                "[vout]",
                "[scaled];[scaled]subtitles="
                f"'{subtitle_srt}':"
                f"force_style='FontSize=28,Alignment=2,"
                f"PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,"
                f"Outline=2'[vout]"
            )

            filter_complex = ";".join(filter_parts)
            cmd[cmd.index("-filter_complex") + 1] = filter_complex

        logger.info("compose_with_ffmpeg: ffmpeg 启动...")
        try:
            process3 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            def _stream3():
                for line in iter(process3.stdout.readline, ""):
                    line = line.rstrip("\n")
                    if line:
                        logger.info(f"[compose_ffmpeg] {line}")
            t3 = threading.Thread(target=_stream3, daemon=True)
            t3.start()
            logger.info(f"[compose_ffmpeg] ffmpeg PID={process3.pid}")
            process3.wait(timeout=360000)
            t3.join(timeout=10)
            if process3.returncode != 0:
                raise subprocess.CalledProcessError(process3.returncode, cmd)
            logger.info(f"FFmpeg 合成完成: {output_path}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg 合成失败: {e.stderr[-300:] if e.stderr else str(e)}")
            raise

        return str(output_path)

    def compose_with_subtitle_burn(self, input_video: str, srt_path: str,
                                   output_path: str) -> str:
        """
        将字幕烧录到现有视频中

        Args:
            input_video: 输入视频
            srt_path: SRT 字幕文件
            output_path: 输出路径

        Returns:
            输出路径
        """
        cmd = [
            "ffmpeg", "-y",
            "-i", input_video,
            "-vf", (
                f"subtitles='{srt_path}':"
                f"force_style='FontSize=36,Alignment=2,"
                f"PrimaryColour=&H00FFFFFF,"
                f"OutlineColour=&H00000000,Outline=2,"
                f"MarginV=60'"
            ),
            "-c:v", self.codec,
            "-c:a", "copy",
            str(output_path),
        ]

        logger.info("compose_with_subtitle_burn: ffmpeg 启动...")
        process4 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        def _stream4():
            for line in iter(process4.stdout.readline, ""):
                line = line.rstrip("\n")
                if line:
                    logger.info(f"[subtitle_burn] {line}")
        t4 = threading.Thread(target=_stream4, daemon=True)
        t4.start()
        logger.info(f"[subtitle_burn] ffmpeg PID={process4.pid}")
        try:
            process4.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            logger.error("[subtitle_burn] ffmpeg 超时, 强制终止")
            try:
                process4.kill()
            except Exception:
                pass
        t4.join(timeout=10)
        if process4.returncode != 0:
            logger.error(f"[subtitle_burn] ffmpeg 退出码={process4.returncode}")
        return str(output_path)
