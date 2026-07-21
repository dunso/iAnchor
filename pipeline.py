#!/usr/bin/env python3
"""
数字人口播全链路 Pipeline 主编排脚本

用法:
    python pipeline.py --image 数字人.jpg --text "今日股市行情..."

输入: 数字人图片 + 股票文本
输出: 完整口播视频 (可视化动画 + 数字人 + 字幕)

全链路:
  [1] LLM 生成口播稿 → [2] TTS 音频合成 → [3] 可视化动画 ─┐
                                                          ├→ [5] 视频合成 → 最终视频
                               [4] 数字人驱动 ─────────────┘
                               [字幕] ─────────────────────┘
"""

import argparse
import concurrent.futures
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import yaml

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.llm_script import LLMScriptGenerator
from modules.tts_generator import TTSGenerator
from modules.viz_animation import VizAnimationGenerator
from modules.avatar_driver import AvatarDriver
from modules.subtitle_generator import SubtitleGenerator
from modules.video_composer import VideoComposer


# ─── 日志配置 ────────────────────────────────────────────
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)
    # 减少第三方库日志噪音
    for lib in ["matplotlib", "matplotlib.font_manager", "PIL", "moviepy"]:
        logging.getLogger(lib).setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ─── 辅助函数 ────────────────────────────────────────────
def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║      🎬 数字人口播全链路 Pipeline          ║
║      Mac M4 · 完全本地 · 高质量            ║
╚══════════════════════════════════════════════╝
""")


def print_step(step: int, total: int, name: str):
    msg = f"[{step}/{total}] {name}"
    logger.info(msg)
    print(f"\n{'─' * 50}")
    print(f"  {msg}")
    print(f"{'─' * 50}")


def format_duration(seconds: float) -> str:
    """格式化时长"""
    m, s = divmod(int(seconds), 60)
    return f"{m}分{s}秒" if m > 0 else f"{s}秒"


# ─── Pipeline 主类 ──────────────────────────────────────
class DigitalHumanPipeline:
    """数字人口播全链路 Pipeline"""

    def __init__(self, config: dict):
        self.config = config
        self.paths = config.get("paths", {})
        self.pipeline_cfg = config.get("pipeline", {})

        # 输出目录
        output_dir = Path(self.paths.get("output_dir", "./output"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = output_dir / timestamp
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 中间产物路径
        self.script_path = self.session_dir / "script.json"
        self.audio_path = self.session_dir / "audio.wav"
        self.viz_path = self.session_dir / "viz_animation.mp4"
        self.avatar_path = self.session_dir / "avatar_video.mp4"
        self.srt_path = self.session_dir / "subtitles.srt"
        self.subtitle_clip_path = self.session_dir / "subtitle_clip.mp4"
        self.final_path = self.session_dir / "final_output.mp4"

        # 初始化模块
        self.llm = LLMScriptGenerator(config)
        self.tts = TTSGenerator(config)
        self.viz = VizAnimationGenerator(config)
        self.avatar = AvatarDriver(config)
        self.subtitle = SubtitleGenerator(config)
        self.composer = VideoComposer(config)

        # 状态追踪
        self.results = {}

    def check_prerequisites(self) -> dict:
        """检查所有前置依赖"""
        status = {
            "python": True,
            "ffmpeg": False,
            "llm": False,
            "tts_bark": False,
            "musetalk": False,
        }

        # FFmpeg
        try:
            subprocess.run(["which", "ffmpeg"], check=True, capture_output=True)
            status["ffmpeg"] = True
        except Exception:
            logger.debug("ffmpeg 检查失败")

        # LLM (DeepSeek API / Ollama)
        status["llm"] = self.llm.check_availability()

        # TTS Bark
        status["tts_bark"] = self.tts.check_bark()

        # MuseTalk
        status["musetalk"] = self.avatar.check_availability()

        return status

    def run(self, image_path: str, stock_text: str, skip_llm: bool = False, script_data: dict = None, animation_only: bool = False):
        """运行完整 Pipeline"""
        start_time = time.time()

        print_banner()
        logger.info(f"输入图片: {image_path}")
        logger.info(f"输入文本长度: {len(stock_text)} 字符")
        logger.info(f"输出目录: {self.session_dir}")

        # 检查前置条件
        status = self.check_prerequisites()
        self._print_status(status)

        total_steps = 5
        current = 0

        # ─── Step 1: LLM 口播稿生成 ───
        current += 1
        print_step(current, total_steps, "LLM 口播稿生成")
        if script_data and script_data.get("segments"):
            # 使用已生成的口播稿数据，跳过 LLM
            logger.info("使用已生成的口播稿，跳过 LLM")
        else:
            script_data = self._step_llm(stock_text, skip_llm)
        self.results["script"] = script_data

        # 保存口播稿
        with open(self.script_path, "w", encoding="utf-8") as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)
        logger.info(f"口播稿已保存: {self.script_path}")

        print(f"  📝 标题: {script_data.get('title', 'N/A')}")
        print(f"  📝 段落数: {len(script_data.get('segments', []))}")

        # ─── Step 2: TTS 音频生成 ───
        current += 1
        segments = script_data.get("segments", [])
        print_step(current, total_steps, "TTS 音频合成")
        logger.info(f"TTS 并行生成中 ({len(segments)} 段)...")
        if segments:
            audio_result = self._step_tts_segments(segments, script_data["script"])
        else:
            audio_result = self._step_tts(script_data["script"])
        self.results["audio"] = audio_result
        duration = audio_result["duration"]
        print(f"  🔊 音频时长: {format_duration(duration)}")
        print(f"  🔊 时间戳数: {len(audio_result.get('timestamps', []))}")

        # ─── Step 3: 并行 — 可视化动画 + 数字人驱动 ───
        current += 1
        if animation_only:
            print_step(current, total_steps, "可视化动画 (全屏竖屏)")
            self.viz.height = 1920
            self.viz.width = 1080
            viz_path = self._step_viz(
                script_data["title"],
                audio_result.get("sub_segments", script_data["segments"]),
                duration,
                audio_result.get("timestamps", []),
            )
            avatar_path = ""
        else:
            viz_mode = self.config.get("visualization", {}).get("mode", "card")
            parallel = viz_mode not in ("wan", "wan_api", "bailian")  # wan 模式抢显存, 串行
            label = "可视化动画 & 数字人驱动 (并行)" if parallel else "可视化动画 & 数字人驱动 (串行)"
            print_step(current, total_steps, label)

            if parallel:
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    viz_future = executor.submit(
                        self._step_viz,
                        script_data["title"],
                        audio_result.get("sub_segments", script_data["segments"]),
                        duration,
                        audio_result.get("timestamps", []),
                    )
                    avatar_future = executor.submit(
                        self._step_avatar_segments, image_path, audio_result
                    )
                    logger.info("等待可视化动画完成... (卡住=>检查 viz 子进程)")
                    viz_path = viz_future.result()
                    logger.info(f"可视化动画完成: {viz_path}")
                    logger.info("等待数字人驱动完成... (卡住=>检查 avatar 子进程)")
                    avatar_path = avatar_future.result()
                    logger.info(f"数字人驱动完成: {avatar_path}")
            else:
                # wan 模式: 先跑 viz, 释放显存后再跑 avatar
                logger.info("wan 模式: 先生成 AI 视频...")
                viz_path = self._step_viz(
                    script_data["title"],
                    audio_result.get("sub_segments", script_data["segments"]),
                    duration,
                    audio_result.get("timestamps", []),
                )
                logger.info("wan 模式: 再驱动数字人...")
                avatar_path = self._step_avatar_segments(image_path, audio_result)

        self.results["viz"] = viz_path
        self.results["avatar"] = avatar_path

        if viz_path:
            print(f"  📊 可视化: {viz_path}")
        if avatar_path:
            print(f"  🎭 数字人: {avatar_path}")

        # ─── Step 4: 字幕生成 ───
        current += 1
        print_step(current, total_steps, "字幕生成")
        if animation_only:
            srt_result = {"srt": "", "clip": ""}
            logger.info("animation_only 模式: 跳过字幕")
        else:
            srt_result = self._step_subtitle(
                audio_result.get("sub_segments", script_data["segments"]),
                audio_result.get("timestamps", []),
                duration,
                str(self.audio_path),
            )
        self.results["subtitle"] = srt_result

        if srt_result.get("srt"):
            print(f"  📝 SRT 字幕: {srt_result['srt']}")
        if srt_result.get("clip"):
            print(f"  📝 字幕视频: {srt_result['clip']}")

        # ─── Step 5: 视频合成 ───
        current += 1
        print_step(current, total_steps, "视频合成")
        final_path = self._step_compose(
            viz_path,
            avatar_path,
            srt_result,
            str(self.audio_path),
            duration,
        )
        self.results["final"] = final_path

        # ─── 完成 ───
        elapsed = time.time() - start_time
        print(f"\n{'═' * 50}")
        print(f"  ✅ Pipeline 完成!")
        print(f"  ⏱  总耗时: {format_duration(elapsed)}")
        print(f"  🎬 最终视频: {final_path}")
        print(f"  📁 工作目录: {self.session_dir}")
        print(f"{'═' * 50}")

        # 可选：打开视频
        if self.pipeline_cfg.get("open_on_complete", False):
            subprocess.run(["open", final_path])

        return final_path

    # ─── 各步骤实现 ─────────────────────────────────────

    @staticmethod
    def _run_ffmpeg_logging(cmd: list, label: str, timeout: int = 360000) -> int:
        """ffmpeg subprocess streaming (INFO throttled + heartbeat), returns exit code"""
        import threading as _thr
        import time as _t
        logger.info(f"[{label}] ffmpeg starting...")
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        _last_info = [0.0]
        _last_line = [""]
        def _stream():
            for line in iter(process.stdout.readline, ""):
                line = line.rstrip("\n")
                if not line:
                    continue
                _last_line[0] = line
                now = _t.time()
                if now - _last_info[0] >= 3.0:
                    logger.info(f"[{label}] {line}")
                    _last_info[0] = now
        t = _thr.Thread(target=_stream, daemon=True)
        t.start()
        _heart = [True]
        _counter = [0]
        def _heartbeat():
            while _heart[0]:
                _t.sleep(5)
                if not _heart[0]:
                    return
                _counter[0] += 5
                last = _last_line[0]
                msg = f"[{label}] still running (PID={process.pid}, {_counter[0]}s)..."
                if last:
                    msg += f" latest: {last[-80:]}"
                logger.info(msg)
        ht = _thr.Thread(target=_heartbeat, daemon=True)
        ht.start()
        logger.info(f"[{label}] ffmpeg PID={process.pid}, waiting (timeout={timeout}s)...")
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error(f"[{label}] ffmpeg timeout, killing")
            try:
                process.kill()
            except Exception:
                pass
        finally:
            _heart[0] = False
        t.join(timeout=10)
        ht.join(timeout=1)
        rc = process.returncode
        if rc != 0:
            logger.error(f"[{label}] ffmpeg exit={rc}")
        else:
            logger.info(f"[{label}] ffmpeg done, exit=0")
        return rc

    def _step_llm(self, stock_text: str, skip: bool) -> dict:
        """Step 1: LLM 口播稿生成"""
        logger.info("_step_llm 开始")
        if skip:
            # 按所有标点拆成短句
            parts = re.split(r"(?<=[。！？；\n])", stock_text)
            phrases = []
            for part in parts:
                sub = re.split(r"(?<=[，、：,])", part)
                phrases.extend(s.strip() for s in sub if s.strip())
            segments = [{"text": p, "data": {"time_label": "", "price": "--", "change_pct": "--", "volume": "--"}} for p in phrases]
            result = {"title": "口播视频", "script": stock_text, "segments": segments}
            logger.info(f"_step_llm 完成 (skip): {len(segments)} 段")
            return result
        result = self.llm.generate(stock_text)
        logger.info(f"_step_llm 完成: {len(result.get('segments',[]))} 段")
        return result

    def _step_tts(self, script_text: str) -> dict:
        """Step 2: TTS 音频合成"""
        logger.info("_step_tts 开始")
        result = self.tts.generate(script_text, str(self.audio_path))
        logger.info(f"_step_tts 完成: {result.get('duration',0):.1f}s")
        return result

    def _step_tts_segments(self, segments: list, fallback_text: str) -> dict:
        """逐段 TTS 生成，累积精确时间戳，拼接音频"""
        logger.info(f"_step_tts_segments 开始: {len(segments)} 段")
        if not segments:
            return self._step_tts(fallback_text)

        # 按标点拆短句，确保字幕逐句展示
        expanded = []
        for seg in segments:
            text = seg.get("text", "").strip()
            if not text:
                continue
            # 用句号/问号/感叹号拆分
            parts = re.split(r"(?<=[。！？；\n])", text)
            for part in parts:
                # 再用逗号/顿号拆
                sub = re.split(r"(?<=[，、：,])", part)
                for s in sub:
                    s = s.strip()
                    if s:
                        expanded.append({"text": s, "data": seg.get("data", {})})
        segments = expanded or segments

        # 并行 TTS: 保留精确时间戳, 用线程池加速
        seg_results = [None] * len(segments)
        def _gen_tts(idx, text):
            if not text.strip():
                return idx, None
            # 缓存: 文字 + 音色 哈希
            import hashlib as _h
            voice = self.tts.voice if hasattr(self.tts, "voice") else "default"
            cache_key = _h.md5(f"{text}|{voice}".encode()).hexdigest()[:16]
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "tts")
            os.makedirs(cache_dir, exist_ok=True)
            seg_path = os.path.join(cache_dir, f"tts_{cache_key}.wav")
            # 命中缓存
            if os.path.isfile(seg_path) and os.path.getsize(seg_path) > 1024:
                import struct, wave
                try:
                    with wave.open(seg_path, "rb") as wf:
                        dur = wf.getnframes() / wf.getframerate()
                    return idx, {"path": seg_path, "duration": dur, "text": text}
                except Exception:
                    pass
            try:
                r = self.tts.generate(text, seg_path)
                return idx, {"path": seg_path, "duration": r["duration"], "text": text}
            except Exception as e:
                logger.error(f"TTS 段 {idx} 失败: {e}")
                return idx, None

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(_gen_tts, i, seg["text"]): i for i, seg in enumerate(segments)}
            for f in concurrent.futures.as_completed(futures):
                idx, result = f.result()
                if result:
                    seg_results[idx] = result
                    logger.info(f"TTS {idx+1}/{len(segments)}: {result['duration']:.1f}s")

        # 按顺序拼接 + 累积时间戳
        seg_files = []
        timestamps = []
        current = 0.0
        failed_count = sum(1 for x in seg_results if x is None)
        if failed_count:
            logger.warning(f"TTS: {failed_count}/{len(segments)} 段失败, 音频可能不完整")
        for r in seg_results:
            if r is None:
                continue
            seg_files.append(r["path"])
            timestamps.append({
                "start": round(current, 2),
                "end": round(current + r["duration"], 2),
                "text": r["text"],
            })
            current += r["duration"]

        # ffmpeg concat
        concat_list = os.path.join(tempfile.gettempdir(), "concat.txt")
        with open(concat_list, "w") as f:
            for sf in seg_files:
                f.write(f"file '{sf}'\n")
        rc = self._run_ffmpeg_logging(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list,
             "-c", "copy", str(self.audio_path)],
            label="TTS concat", timeout=30,
        )
        if rc != 0:
            logger.error(f"TTS 音频拼接失败, exit={rc}")
        try:
            os.unlink(concat_list)
        except Exception:
            pass
        duration = self.tts.get_audio_duration(str(self.audio_path))
        logger.info(f"_step_tts_segments 完成: {len(timestamps)} 段, {duration:.1f}s")
        return {"audio_path": str(self.audio_path), "duration": duration, "timestamps": timestamps, "sub_segments": segments}

    def _step_viz(self, title: str, segments: list, duration: float, timestamps: list = None) -> str:
        """Step 3a: 可视化动画生成"""
        logger.info(f"_step_viz 开始: mode={self.viz.mode}, {len(segments) if segments else 0} segs, {duration:.1f}s")
        result = self.viz.generate(
            title=title,
            segments=segments,
            duration=duration,
            output_path=str(self.viz_path),
            timestamps=timestamps,
        )
        logger.info(f"_step_viz 完成: {result}")
        return result

    def _step_avatar(self, image_path: str, audio_path: str) -> str:
        """Step 3b: 数字人驱动"""
        logger.info(f"_step_avatar 开始: image={os.path.basename(image_path)}")
        dur = self._get_audio_dur(audio_path)
        logger.info(f"数字人驱动开始 (音频 {dur:.0f}s, 预计 {max(dur*2, 60):.0f}s)...")
        result = self.avatar.generate(
            src_image=image_path,
            dri_audio=audio_path,
            output_path=str(self.avatar_path),
        )
        logger.info("数字人驱动完成")
        return result

    @staticmethod
    def _get_audio_dur(path: str) -> float:
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                path], capture_output=True, text=True, timeout=10)
            return float(r.stdout.strip())
        except Exception:
            logger.debug("ffprobe 失败, 默认10s")
            return 10.0

    def _step_avatar_segments(self, image_path: str, audio_result: dict) -> str:
        """数字人驱动 — 整段音频一次处理，不逐段拆分"""
        logger.info("_step_avatar_segments 开始")
        result = self._step_avatar(image_path, audio_result["audio_path"])
        logger.info(f"_step_avatar_segments 完成: {result}")
        return result

    def _step_subtitle(self, segments: list, tts_timestamps: list,
                       duration: float, audio_path: str = "") -> dict:
        """Step 4: 字幕生成"""
        logger.info(f"_step_subtitle 开始: {len(segments)} segs, {duration:.1f}s")
        result = {"srt": "", "clip": ""}

        # TTS 时间戳按比例估算（实际测试 Whisper tiny 中文识别太差，暂弃）
        timestamps = tts_timestamps if tts_timestamps else \
            self.subtitle.generate_srt_from_segments(segments, duration)

        if timestamps:
            # 生成 SRT
            result["srt"] = self.subtitle.generate_srt(
                timestamps, str(self.srt_path)
            )

            # 生成字幕视频片段 (用于 MoviePy 叠加)
            try:
                result["clip"] = self.subtitle.generate_subtitle_clip(
                    timestamps, duration, str(self.subtitle_clip_path)
                )
            except Exception as e:
                logger.warning(f"字幕视频生成失败 (将使用 SRT 烧录): {e}")

        logger.info(f"_step_subtitle 完成: srt={bool(result.get('srt'))}, clip={bool(result.get('clip'))}")
        return result

    def _step_compose(self, viz_path: str, avatar_path: str,
                       srt_result: dict, audio_path: str,
                       duration: float) -> str:
        """Step 5: 视频合成"""
        logger.info(f"_step_compose 开始: viz={os.path.basename(viz_path) if viz_path else 'NONE'}, dur={duration:.1f}s")
        if not viz_path:
            logger.error("可视化动画未生成, 无法合成")
            raise RuntimeError("可视化动画生成失败，请检查上方日志中的 viz 错误（常见：Remotion 分块失败、无卡片数据）")
        cover_video = getattr(self.viz, '_cover_video', None) or ""
        cover_dur = getattr(self.viz, '_cover_dur', 1.5)
        result = self.composer.compose_with_moviepy(
            viz_video=viz_path,
            avatar_video=avatar_path,
            subtitle_clip=srt_result.get("clip", ""),
            audio_path=audio_path,
            output_path=str(self.final_path),
            cover_video=cover_video,
            cover_dur=cover_dur,
        )
        logger.info(f"_step_compose 完成: {result}")
        return result

    @staticmethod
    def _print_status(status: dict):
        """打印前置条件检查结果"""
        print("\n📋 环境检查:")
        icons = {True: "✅", False: "❌"}
        labels = {
            "python": "Python 3",
            "ffmpeg": "FFmpeg",
            "llm": "LLM (DeepSeek API / Ollama)",
            "tts_bark": "Bark TTS (本地高质量中文语音)",
            "musetalk": "MuseTalk (音频驱动唇形同步)",
        }
        for key, label in labels.items():
            ok = status.get(key, False)
            icon = icons[ok]
            note = ""
            if key == "llm" and not ok:
                note = " — 请设置 DEEPSEEK_API_KEY"
            elif key == "tts_bark" and not ok:
                note = " — 请先运行 bash install.sh"
            elif key == "musetalk" and not ok:
                note = " — 请安装 MuseTalk (设置 avatar.fallback_image_mode: true 可跳过)"
            print(f"  {icon} {label}{note}")
        print()


# ─── 命令行入口 ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="数字人口播全链路 Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法
  python pipeline.py --image avatar.jpg --text "今日股市行情..."

  # 使用文本文件作为输入
  python pipeline.py --image avatar.png --text-file news.txt

  # 跳过 LLM (使用模板)
  python pipeline.py --image avatar.jpg --text "..." --skip-llm

  # 自定义配置
  python pipeline.py --image avatar.jpg --text "..." --config my_config.yaml

  # 输出到指定目录
  python pipeline.py --image avatar.jpg --text "..." -o ./my_output
        """,
    )
    parser.add_argument("--image", "-i", default="", help="数字人图片路径")
    parser.add_argument("--text", "-t", default="", help="股票文本 (直接输入)")
    parser.add_argument("--text-file", "-f", default="", help="股票文本文件路径")
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--output", "-o", default="", help="输出目录 (覆盖配置文件)")
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM，使用模板生成口播稿")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志")
    parser.add_argument("--viz-mode", default="", help="可视化模式 (覆盖 config): card|sd|manim|manim_comic|remotion|wan|wan_api|bailian")
    parser.add_argument("--sd-provider", default="", help="SD 后端 (覆盖 config): mflux|flux")
    parser.add_argument("--check", action="store_true", help="仅检查环境依赖，不运行 pipeline")
    parser.add_argument("--animation-only", action="store_true", help="动画模式(无主播, 全屏竖屏)")

    args = parser.parse_args()

    # 日志
    setup_logging(args.verbose)

    # 加载配置
    config_path = args.config
    if not os.path.isfile(config_path):
        print(f"⚠️  配置文件不存在: {config_path}，使用默认配置")
        config = {"paths": {"output_dir": "./output"}}
    else:
        config = load_config(config_path)

    # 覆盖输出目录
    if args.output:
        config.setdefault("paths", {})["output_dir"] = args.output
    # 覆盖可视化模式
    if args.viz_mode:
        config.setdefault("visualization", {})["mode"] = args.viz_mode
        print(f"  viz mode: {args.viz_mode}")
    if args.sd_provider:
        config.setdefault("visualization", {})["sd_provider"] = args.sd_provider
        print(f"  sd provider: {args.sd_provider}")

    # 初始化 Pipeline
    pipeline = DigitalHumanPipeline(config)

    if args.check:
        # 仅检查环境（不需要图片和文本）
        status = pipeline.check_prerequisites()
        pipeline._print_status(status)
        return

    # 获取输入文本
    stock_text = args.text
    if not stock_text and args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            stock_text = f.read()

    if not stock_text.strip():
        print("❌ 请提供股票文本 (--text 或 --text-file)")
        print("   示例: python pipeline.py --image avatar.jpg --text '今日沪指收涨...'")
        sys.exit(1)

    # 检查图片
    if not args.image or not os.path.isfile(args.image):
        print(f"❌ 图片文件不存在: {args.image or '(未指定)'}")
        sys.exit(1)

    # 运行
    final_path = pipeline.run(
        image_path=args.image,
        stock_text=stock_text,
        skip_llm=args.skip_llm,
        animation_only=args.animation_only,
    )

    print(f"\n🎉 口播视频已生成: {final_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
