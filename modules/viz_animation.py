"""
可视化动画 — 支持四种模式:
  mode=card:     PPT 卡片 (LLM 数据, 零额外API)
  mode=sd:       MLX SD 1.5 文生图 (本地)
  mode=manim:    Manim 数字动画 (本地)
  mode=remotion: Remotion React 组件渲染
"""

import json
import logging
import os
import random
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_FLUX_DIR = os.path.expanduser("~/code/git-hub/dunso/mlx-examples/flux")
_FLUX_VENV = os.path.expanduser("~/code/git-hub/dunso/mlx-examples/.venv/bin/python3")

_LAYOUTS = ["center_big", "left_align", "split_row", "right_badge",
            "minimal", "accent_bar"]


def _stream_run_ffmpeg(cmd: list, label: str, check: bool = True, timeout: int = 360000) -> int:
    """ffmpeg 子进程流式输出(INFO节流)，返回 exit code"""
    import time as _t
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
    t = threading.Thread(target=_stream, daemon=True)
    t.start()
    # 心跳: 每5秒打一次，防误以为卡住
    _heart = [True]
    _counter = [0]
    def _heartbeat():
        while _heart[0]:
            _t.sleep(5)
            if not _heart[0]:
                return
            _counter[0] += 5
            last = _last_line[0]
            msg = f"[{label}] 仍在运行 (PID={process.pid}, {_counter[0]}s)..."
            if last:
                msg += f" 最近: {last[-80:]}"
            logger.info(msg)
    ht = threading.Thread(target=_heartbeat, daemon=True)
    ht.start()
    logger.info(f"[{label}] ffmpeg PID={process.pid}, 等待完成 (timeout={timeout}s)...")
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.error(f"[{label}] ffmpeg 超时, 强制终止")
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
        logger.error(f"[{label}] ffmpeg 退出码={rc}")
        if check:
            raise subprocess.CalledProcessError(rc, cmd)
    else:
        logger.info(f"[{label}] ffmpeg 完成, exit=0")
    return rc


class VizAnimationGenerator:
    """PPT 卡片 / SD 文生图，双模式"""

    @staticmethod
    def _stream_run(cmd: list, label: str, check: bool = True, timeout: int = 360000) -> int:
        return _stream_run_ffmpeg(cmd, label, check, timeout)

    def __init__(self, config: dict):
        self._config = config  # 保存完整配置, 传给子模块
        cfg = config.get("visualization", {})
        video_cfg = config.get("video", {})
        self.width = cfg.get("width", 1080)
        # 高度由视频总高 × viz 比例计算 (config 里的 height 仅作参考)
        video_height = video_cfg.get("height", 1920)
        viz_ratio = video_cfg.get("viz_height_ratio", 0.20)
        self.height = int(video_height * viz_ratio)
        self.fps = cfg.get("fps", 30)
        self.bg_color = cfg.get("bg_color", "#1a1a2e")
        self.text_color = cfg.get("text_color", "#e0e0e0")
        self.accent_color = cfg.get("accent_color", "#ffb74d")
        self.color_up = cfg.get("color_up", "#ef5350")
        self.color_down = cfg.get("color_down", "#26a69a")
        self.font_size_title = cfg.get("font_size_title", 32)
        self.mode = cfg.get("mode", "card")  # card | sd | manim | manim_comic | remotion
        self.sd_provider = cfg.get("sd_provider", "mflux")  # mflux | flux
        self.sd_timeout = cfg.get("sd_timeout", 360000)
        self.sd_model = cfg.get("mflux_model", "z-image-turbo")
        self.flux_model = cfg.get("flux_model", "dev")
        self.sd_steps = cfg.get("sd_steps", None)
        self.manim_quality = cfg.get("manim_quality", "qh")  # ql | qm | qh
        self.comic_style = cfg.get("comic_style", True)  # 漫画风格 prompt + Ken Burns

    def generate(self, title: str, segments: list[dict], duration: float,
                 output_path: str, timestamps: list = None) -> str:
        logger.info(f"===== VizAnimationGenerator.generate() 开始: mode={self.mode}, title={title[:40] if title else ''}, {len(segments) if segments else 0} segs, {duration:.1f}s, ts={len(timestamps) if timestamps else 0} =====")
        # Prepend cover frame (extract date from script)
        all_text = title + " " + " ".join(
            seg.get("text", "") for seg in segments)
        cover_path = self._make_cover_frame(all_text)
        has_cover = cover_path is not None

        if self.mode == "sd":
            result = self._gen_sd_slideshow(title, segments, duration,
                                             output_path, timestamps)
        elif self.mode == "manim":
            result = self._gen_manim_video(title, segments, duration,
                                             output_path, timestamps)
        elif self.mode == "manim_comic":
            result = self._gen_manim_comic_video(title, segments, duration,
                                                  output_path, timestamps)
        elif self.mode == "wan":
            result = self._gen_wan_video(title, segments, duration,
                                          output_path, timestamps)
        elif self.mode == "wan_api":
            result = self._gen_wan_api_video(title, segments, duration,
                                              output_path, timestamps)
        elif self.mode == "bailian":
            result = self._gen_bailian_video(title, segments, duration,
                                              output_path, timestamps)
        elif self.mode == "remotion":
            result = self._gen_remotion_video(title, segments, duration,
                                               output_path, timestamps)
        else:
            result = self._gen_card_slideshow(title, segments, duration,
                                              output_path, timestamps)

        self._cover_video = None
        if has_cover:
            self._cover_video = self._make_cover_video(cover_path)
        logger.info(f"===== VizAnimationGenerator.generate() 完成: {result} =====")
        return result

    # ═══════════════════════════════════════════════
    #  模式 1: PPT 卡片 (真实 LLM 数据)
    # ═══════════════════════════════════════════════

    def _gen_card_slideshow(self, title, segments, duration,
                            output_path, timestamps):
        logger.info(f"_gen_card_slideshow 开始: {len(segments)} segs, {duration:.1f}s")
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        self._setup_chinese_font(font_manager, matplotlib)

        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": ""
        }]

        # 给每个时间戳分配数据：找到其所属 segment 的真实 data
        for ts in ts_list:
            match = self._find_segment_data(ts, segments, timestamps, duration)
            ts["_price"] = match.get("price")
            ts["_change"] = match.get("change_pct")
            ts["_volume"] = match.get("volume", "")
            ts["_label"] = match.get("time_label", "")

        dpi = 100
        fig_w, fig_h = self.width / dpi, self.height / dpi
        slide_dir = tempfile.mkdtemp()
        slide_files = []

        for i, ts in enumerate(ts_list):
            if i % max(len(ts_list) // 10, 1) == 0:
                logger.info(f"Card 渲染: {i+1}/{len(ts_list)}")
            layout = _LAYOUTS[i % len(_LAYOUTS)]
            price = ts.get("_price")
            change = ts.get("_change")
            volume = ts.get("_volume", "")
            label = ts.get("_label", "")
            # 无数字 → 提取关键词做卡片文字
            card_keywords = ""
            if price is None:
                raw = ts.get("text", "").strip()
                func_chars = set("的了在是我与及或为被把对从到让给但只可便也就还却又其之而因所此已由以能会要于个中不有上下来去出一说过大")
                cleaned = re.sub(r"[，。！？；：、,!\?\;\:\n]", "", raw)
                tokens = []
                cur = ""
                for ch in cleaned:
                    if ch in func_chars:
                        if len(cur) >= 2: tokens.append(cur)
                        cur = ""
                    else:
                        cur += ch
                if len(cur) >= 2: tokens.append(cur)
                result = " ".join(tokens[:3]) if tokens else raw[:10]
                card_keywords = result[:9] if len(result) > 9 else result
            if change is not None:
                try:
                    c = float(change)
                    color = self.color_up if c >= 0 else self.color_down
                except (ValueError, TypeError):
                    logger.debug(f"change_pct 解析失败: {change}")
                    color = self.accent_color
            else:
                color = self.accent_color

            slide_path = os.path.join(slide_dir, f"slide_{i:03d}.png")
            self._render_card(fig_w, fig_h, dpi, layout,
                              i + 1, len(ts_list),
                              price, change, volume, label, color,
                              card_keywords, slide_path)
            slide_files.append((slide_path, ts["start"], ts["end"]))

        result = self._concat_slides(slide_files, str(output_path))
        # 清理临时幻灯片 PNG
        try:
            shutil.rmtree(slide_dir, ignore_errors=True)
        except Exception:
            pass
        return result

    @staticmethod
    def _find_segment_data(ts, segments, timestamps, duration):
        """找到字幕短句所属的 LLM segment，返回其 data；fallback 从文字提取"""
        t_mid = (ts["start"] + ts["end"]) / 2
        text = ts.get("text", "")
        for i, seg in enumerate(segments):
            seg_ts = timestamps[i] if timestamps and i < len(timestamps) else None
            seg_start = seg_ts["start"] if seg_ts else i * duration / len(segments)
            seg_end = seg_ts["end"] if seg_ts else (i + 1) * duration / len(segments)
            if seg_start <= t_mid < seg_end:
                d = seg.get("data", {})
                price_str = d.get("price", "")
                if price_str and price_str != "--":
                    try:
                        p = float(str(price_str).replace(",", "").replace("¥", ""))
                    except (ValueError, TypeError):
                        logger.debug(f"price 解析失败: {price_str}")
                        p = None
                else:
                    p = None
                chg_str = d.get("change_pct", "")
                try:
                    chg = float(str(chg_str).replace("%", "").replace("+", ""))
                except (ValueError, TypeError):
                    chg = None
                if p is not None:
                    return {"price": p, "change_pct": chg,
                            "volume": d.get("volume", ""),
                            "time_label": d.get("time_label", "")}
                break  # found the segment, fallthrough to text extraction

        # LLM 无数据 → 从字幕文字中提取数字
        p, chg, vol = None, None, ""
        for m in re.finditer(r"([\d,.]{3,})\s*(?:点|元|报|收?于)", text):
            p = float(m.group(1).replace(",", ""))
            break
        _decline_kw = ("跌", "降", "低", "挫", "↓", "▼", "跌幅")
        for m in re.finditer(r"([+-]?[\d.]+)\s*%", text):
            try:
                val = float(m.group(1))
                before = text[:m.start()] if m.start() > 0 else ""
                if any(kw in before[-4:] + m.group(0) for kw in _decline_kw):
                    val = -abs(val)
                chg = val; break
            except Exception as e:
                logger.debug(f"change_pct 解析失败: {m.group(0)}")
        for m in re.finditer(r"(\d+[\d.]*)\s*(?:亿|万|万亿)", text):
            vol = m.group(0); break
        return {"price": p, "change_pct": chg, "volume": vol, "time_label": ""}

    def _render_card(self, fig_w, fig_h, dpi, layout,
                     idx, total, price, change, volume, label, color,
                     card_text, save_path):
        import matplotlib.pyplot as plt
        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi,
                         facecolor=self.bg_color)
        ax = fig.add_axes([0, 0, 1, 1], facecolor=self.bg_color)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        ax.text(0.96, 0.95, f"{idx}/{total}", transform=ax.transAxes,
                fontsize=16, color=self.text_color + "66",
                ha="right", va="top")

        ps = f"¥{price:.1f}" if price is not None else card_text or ""
        sign = "+" if (change is not None and change >= 0) else ""
        cs = f"{sign}{change:.2f}%" if change is not None else ""

        if layout == "center_big":
            if ps:
                ax.text(0.5, 0.65, ps, transform=ax.transAxes,
                        fontsize=72, fontweight="bold", color=color,
                        ha="center", va="center")
            if cs:
                ax.text(0.5, 0.40, cs, transform=ax.transAxes,
                        fontsize=48, fontweight="bold", color=color,
                        ha="center", va="center")
            ax.plot([0.2, 0.8], [0.85, 0.85], color=color, linewidth=3,
                    transform=ax.transAxes, alpha=0.5)

        elif layout == "left_align":
            if ps:
                ax.text(0.08, 0.60, ps, transform=ax.transAxes,
                        fontsize=68, fontweight="bold", color=color,
                        ha="left", va="center")
            if cs:
                ax.text(0.08, 0.35, cs, transform=ax.transAxes,
                        fontsize=38, fontweight="bold", color=color,
                        ha="left", va="center")
            ax.barh(0.65, 0.08, height=0.15, left=0.87, color=color,
                    alpha=0.3, transform=ax.transAxes)

        elif layout == "split_row":
            if ps:
                ax.text(0.5, 0.78, ps, transform=ax.transAxes,
                        fontsize=66, fontweight="bold", color=color,
                        ha="center", va="center")
            if cs:
                ax.text(0.25, 0.38, cs, transform=ax.transAxes,
                        fontsize=44, fontweight="bold", color=color,
                        ha="center", va="center")
            if volume:
                ax.text(0.75, 0.38, f"成交\n{volume}",
                        transform=ax.transAxes,
                        fontsize=26, color=self.text_color + "cc",
                        ha="center", va="center")
            ax.plot([0.05, 0.95], [0.55, 0.55], color=self.text_color,
                    alpha=0.15, linewidth=1, transform=ax.transAxes)

        elif layout == "right_badge":
            if ps:
                ax.text(0.5, 0.60, ps, transform=ax.transAxes,
                        fontsize=64, fontweight="bold", color=color,
                        ha="center", va="center")
            if cs:
                ax.text(0.5, 0.35, cs, transform=ax.transAxes,
                        fontsize=40, fontweight="bold", color=color,
                        ha="center", va="center")
            from matplotlib.patches import Circle
            circle = Circle((0.85, 0.45), 0.07, facecolor=color,
                            alpha=0.3, edgecolor=color, linewidth=2,
                            transform=ax.transAxes)
            ax.add_patch(circle)

        elif layout == "minimal":
            if ps:
                ax.text(0.5, 0.60, ps, transform=ax.transAxes,
                        fontsize=60, fontweight="light", color=color,
                        ha="center", va="center")
            if cs:
                ax.text(0.5, 0.38, cs, transform=ax.transAxes,
                        fontsize=36, fontweight="light", color=color,
                        ha="center", va="center")
            ax.plot([0.25, 0.75], [0.72, 0.72], color=color + "55",
                    linewidth=1, transform=ax.transAxes, alpha=0.5)

        elif layout == "accent_bar":
            if ps:
                ax.text(0.5, 0.60, ps, transform=ax.transAxes,
                        fontsize=70, fontweight="bold", color=color,
                        ha="center", va="center")
            if cs:
                ax.text(0.5, 0.35, cs, transform=ax.transAxes,
                        fontsize=42, fontweight="bold", color=color,
                        ha="center", va="center")
            ax.barh(0.99, 1.0, height=0.025, left=0, color=color,
                    alpha=0.3, transform=ax.transAxes)

        # 底部进度
        frac = idx / max(total, 1)
        ax.barh(0.02, frac * 0.96, height=0.01, left=0.02,
                color=self.accent_color, alpha=0.5)

        fig.savefig(save_path, dpi=dpi, facecolor=self.bg_color,
                    pad_inches=0)
        plt.close(fig)

    # ═══════════════════════════════════════════════
    #  模式 2: SD 文生图
    # ═══════════════════════════════════════════════

    def _gen_sd_slideshow(self, title, segments, duration,
                          output_path, timestamps):
        logger.info(f"_gen_sd_slideshow 开始: provider={self.sd_provider}, model={self.sd_model}, {len(segments)} segs, {duration:.1f}s")
        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": title,
        }]
        # 全局缓存目录, 跨会话复用
        # 全局缓存目录, 跨会话复用
        img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "sd")
        model_name = self.flux_model if self.sd_provider == "flux" else self.sd_model
        img_dir = os.path.join(img_dir, model_name)
        os.makedirs(img_dir, exist_ok=True)
        logger.info(f"SD 缓存: {img_dir}, 共 {len(ts_list)} 段")
        img_files = []

        for i, ts in enumerate(ts_list):
            text = ts.get("text", "").strip()
            if not text:
                continue
            # 内容哈希缓存: 相同文字 + 相同参数 → 跳过生成
            import hashlib
            cache_key = hashlib.md5(f"{text}|{self.width}|{self.height}|{model_name}".encode()).hexdigest()[:12]
            img_path = os.path.join(img_dir, f"sd_{i:03d}_{cache_key}.png")
            if os.path.isfile(img_path) and os.path.getsize(img_path) > 1024:
                logger.info(f"SD 图 {i+1}/{len(ts_list)} 命中缓存: {text[:20]}...")
                img_files.append((img_path, ts["start"], ts["end"]))
                continue
            logger.info(f"SD 图 {i+1}/{len(ts_list)} 开始生成...")
            if self._gen_sd_image(text, img_path, label=f"SD {i+1}/{len(ts_list)}"):
                img_files.append((img_path, ts["start"], ts["end"]))
                logger.info(f"SD 图 {i+1}/{len(ts_list)}: {text[:20]}...")
            else:
                logger.warning(f"SD 图 {i+1} 失败 ({text[:20]})")

        if not img_files:
            logger.warning("无 SD 图片")
            return ""

        result = self._concat_slides(img_files, str(output_path))
        logger.info(f"_gen_sd_slideshow 完成: {result}")
        return result

    def _gen_sd_image(self, text: str, output: str, label: str = "") -> bool:
        """SD 出图 — mflux 或 MLX FLUX"""
        if self.sd_provider == "flux":
            return self._gen_sd_flux(text, output, label)
        return self._gen_sd_mflux(text, output, label)

    def _gen_sd_mflux(self, text: str, output: str, label: str = "") -> bool:
        """mflux Z-Image-Turbo 出图"""
        if self.comic_style:
            prompt = self._comic_sd_prompt(text)
        else:
            moods = ["rising up trend bullish green", "market overview neutral blue",
                     "volatile trading red green", "steady growth upward gold",
                     "closing bell summary orange", "data analytics dashboard"]
            mood = moods[hash(text) % len(moods)]
            prompt = (f"financial stock market abstract art, {mood}, "
                      f"professional dark background, clean minimal, "
                      f"bloomberg terminal style, 8k")
        import shutil as _sh
        mflux_bin = "mflux-generate-z-image-turbo"
        found = next((p for p in [
            os.path.expanduser(f"~/.local/bin/{mflux_bin}"),
            _sh.which(mflux_bin) or "",
        ] if p and os.path.isfile(p)), "")
        if not found:
            logger.warning("mflux 未找到")
            return False
        # 每个模型默认步数, 用户可通过 sd_steps 覆盖
        model_steps = {
            "z-image-turbo": 4, "flux2-klein-4b": 4, "flux2-klein-9b": 4,
            "qwen": 30, "ideogram4": 12, "fibo": 8, "fibo-lite": 4,
            "ernie-image-turbo": 4, "dev": 20, "schnell": 4,
        }
        steps = self.sd_steps or model_steps.get(self.sd_model, 4)

        cmd = [
            found,
            "--prompt", prompt,
            "--model", self.sd_model,
            "--width", str(self.width), "--height", str(self.height),
            "--steps", str(steps),
            "--seed", str(random.randint(0, 2**31 - 1)),
            "--output", output,
        ]
        logger.info(f"[{label}] mflux model={self.sd_model}, {self.width}x{self.height}, steps={steps}")
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        for k in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)

        try:
            prefix = f"[{label}] " if label else ""
            logger.info(f"{prefix}mflux 启动...")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True, bufsize=1, env=env)
            def _stream():
                for line in iter(process.stdout.readline, ""):
                    line = line.rstrip("\n")
                    if line:
                        logger.info(f"{prefix}{line}")
            t = threading.Thread(target=_stream, daemon=True)
            t.start()
            logger.info(f"{prefix}mflux PID={process.pid}, 等待完成...")
            process.wait(timeout=self.sd_timeout)
            t.join(timeout=10)
            if process.returncode != 0:
                logger.warning(f"mflux failed, exit={process.returncode}")
            logger.info(f"mflux exit code={process.returncode}, output exists={os.path.exists(output)}")
            return os.path.exists(output)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                logger.debug("process.kill() 失败", exc_info=True)
            logger.warning(f"{prefix}mflux timeout: {text[:20]}")
            return False
        except Exception as e:
            logger.error(f"{prefix}mflux 异常: {e}", exc_info=True)
            return False

    def _gen_sd_flux(self, text: str, output: str, label: str = "") -> bool:
        """MLX FLUX.dev 出图"""
        if self.comic_style:
            prompt = self._comic_sd_prompt_flux(text)
        else:
            moods = ["rising up trend bullish green", "market overview neutral blue",
                     "volatile trading red green", "steady growth upward gold",
                     "closing bell summary orange", "data analytics dashboard"]
            mood = moods[hash(text) % len(moods)]
            prompt = (f"financial stock market abstract art, {mood}, "
                      f"professional dark background, clean minimal, "
                      f"bloomberg terminal style, 8k")
        cmd = [
            _FLUX_VENV, os.path.join(_FLUX_DIR, "txt2image.py"),
            prompt,
            "--model", self.flux_model,
            "--n-images", "1",
            "--image-size", f"{self.width}x{self.height}",
            "--output", output,
        ]
        if self.sd_steps:
            cmd += ["--steps", str(self.sd_steps)]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        for k in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)
        if "HF_TOKEN" not in env:
            env["HF_TOKEN"] = os.environ.get("HF_TOKEN", "")

        try:
            prefix = f"[{label}] " if label else ""
            logger.info(f"{prefix}flux 启动...")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT,
                                        text=True, bufsize=1,
                                        cwd=_FLUX_DIR, env=env)
            def _stream():
                for line in iter(process.stdout.readline, ""):
                    line = line.rstrip("\n")
                    if line:
                        logger.info(f"{prefix}{line}")
            t = threading.Thread(target=_stream, daemon=True)
            t.start()
            logger.info(f"{prefix}flux PID={process.pid}, 等待完成...")
            process.wait(timeout=self.sd_timeout)
            t.join(timeout=10)
            if process.returncode != 0:
                logger.warning(f"{prefix}flux failed, exit={process.returncode}")
            logger.info(f"{prefix}flux exit code={process.returncode}, output exists={os.path.exists(output)}")
            return os.path.exists(output)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                logger.debug("process.kill() 失败", exc_info=True)
            logger.warning(f"{prefix}flux timeout: {text[:20]}")
            return False
        except Exception as e:
            logger.error(f"{prefix}flux 异常: {e}", exc_info=True)
            return False

    def _comic_sd_prompt(self, text: str) -> str:
        """根据字幕内容生成漫画风格 prompt"""
        up_keywords = ["涨", "升", "上扬", "反弹", "突破", "新高", "牛市", "飘红", "攀升", "走强"]
        down_keywords = ["跌", "下", "回落", "承压", "跌破", "新低", "熊市", "翻绿", "下滑", "走弱"]
        neutral_keywords = ["震荡", "盘整", "横盘", "整理", "轮动", "分化", "缩量", "观望"]

        text_lower = text
        if any(k in text_lower for k in up_keywords):
            mood = "bullish rising market, green upward arrows, rockets launching, celebration atmosphere"
            color_theme = "warm red and gold tones"
        elif any(k in text_lower for k in down_keywords):
            mood = "bearish falling market, red downward trend, stormy weather, tension"
            color_theme = "cool blue and dark tones"
        else:
            mood = "market analysis, trading floor, busy traders, dynamic energy"
            color_theme = "balanced neutral tones"

        texts = text.replace('"', '').replace("'", "")[:80]
        return (
            f"Chinese manhua comic style illustration, financial news theme, "
            f"{mood}, {color_theme}, "
            f"clean bold ink lines, dynamic composition, dramatic perspective, "
            f"speech bubble with text: '{texts}', "
            f"vibrant color, professional manga artwork, 8k, high detail"
        )

    def _comic_sd_prompt_flux(self, text: str) -> str:
        """FLUX 版本 — 不含中文 (tokenizer不支持)"""
        up_keywords = ["涨", "升", "上扬", "反弹", "突破", "新高", "牛市", "飘红", "攀升", "走强"]
        down_keywords = ["跌", "下", "回落", "承压", "跌破", "新低", "熊市", "翻绿", "下滑", "走弱"]

        if any(k in text for k in up_keywords):
            mood = "bullish rising market, green upward arrows, celebration atmosphere"
            color_theme = "warm red and gold tones"
        elif any(k in text for k in down_keywords):
            mood = "bearish falling market, red downward trend, stormy weather, tension"
            color_theme = "cool blue and dark tones"
        else:
            mood = "market analysis, trading floor, busy traders, dynamic energy"
            color_theme = "balanced neutral tones"

        return (
            f"Chinese manhua comic style illustration, financial news theme, "
            f"{mood}, {color_theme}, "
            f"clean bold ink lines, dynamic composition, dramatic perspective, "
            f"vibrant color, professional manga artwork, 8k, high detail"
        )

    # ═══════════════════════════════════════════════
    #  模式 3: Remotion (React 组件渲染)
    # ═══════════════════════════════════════════════

    def _gen_remotion_video(self, title, segments, duration,
                            output_path, timestamps):
        """Remotion: 生成 cards.json → npx remotion render"""
        logger.info(f"_gen_remotion_video 开始: {len(segments)} segs, {duration:.1f}s")
        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": ""
        }]
        if not ts_list:
            return ""

        logger.info(f"Remotion prep: {len(ts_list)} timestamps, {len(segments)} segments, {duration:.1f}s")
        for ts in ts_list:
            match = self._find_segment_data(ts, segments, timestamps, duration)
            ts["_price"] = match.get("price")
            ts["_change"] = match.get("change_pct")
            ts["_volume"] = match.get("volume", "")

        import json
        cards = []
        for i, ts in enumerate(ts_list):
            price = ts.get("_price")
            change = ts.get("_change")
            # 无数字 → 提取关键词(去掉单字虚词)
            card_text = ""
            if price is None:
                raw = ts.get("text", "").strip()
                # 去掉标点和单字虚词，保留至少2字的词组
                cleaned = re.sub(r"[，。！？；：、,!\?\;\:\n]", "", raw)
                # 常见单字虚词/连接词
                func_chars = set("的了在是我与及或为被把对从到让给但只可便也就还却又其之而因所此已由以能会要于个中不有上下来去出一说过大")
                tokens = []
                cur = ""
                for ch in cleaned:
                    if ch in func_chars:
                        if len(cur) >= 2:
                            tokens.append(cur)
                        cur = ""
                    else:
                        cur += ch
                if len(cur) >= 2:
                    tokens.append(cur)
                result = " ".join(tokens[:3]) if tokens else cleaned[:10]
                card_text = result[:9] if len(result) > 9 else result
            # 只保留真实数据，None 不编造
            if change is not None:
                try:
                    change = float(change)
                except (ValueError, TypeError):
                    change = None
            cards.append({
                "price": price,
                "change": change,  # None 时 React 不显示涨跌幅
                "text": card_text,
                "label": ts.get("_label", ""),
                "volume": ts.get("_volume", ""),
                "startFrame": int(ts["start"] * self.fps),
                "endFrame": int(ts["end"] * self.fps),
                "color": (self.color_up if (change is not None and change >= 0) else self.color_down if change is not None else self.accent_color) if price is not None else self.accent_color,
            })

        if not cards:
            logger.warning("Remotion: 没有有效的卡片数据")
            return ""

        total_frames = max(int(duration * self.fps), 1)

        # 写数据 JSON
        _RE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "modules", "remotion_viz")
        data_path = os.path.join(_RE_DIR, "public", "cards.json")
        with open(data_path, "w") as f:
            json.dump({"cards": cards, "totalDuration": duration,
                        "totalFrames": total_frames, "height": self.height}, f)

        # Ensure output dir exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Find npx
        npx_bin = shutil.which("npx") or os.path.expanduser(
            "~/.nvm/versions/node/v22.23.1/bin/npx")
        node_bin = os.path.dirname(npx_bin)
        env = os.environ.copy()
        env["PATH"] = f"{node_bin}:{env.get('PATH', '')}"

        # Remotion 大帧数会崩溃, 分段渲染后 ffmpeg 拼接
        chunk_frames = 450  # 15 秒一段
        abs_out = os.path.abspath(str(output_path))
        chunk_dir = tempfile.mkdtemp()
        chunk_files = []

        for chunk_start in range(0, total_frames, chunk_frames):
            chunk_end = min(chunk_start + chunk_frames - 1, total_frames - 1)
            chunk_idx = chunk_start // chunk_frames + 1
            chunk_total = (total_frames + chunk_frames - 1) // chunk_frames
            chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_start:05d}.mp4")
            logger.info(f"Remotion chunk {chunk_idx}/{chunk_total}: {chunk_start}-{chunk_end}")
            cmd = [npx_bin, "remotion", "render", "FinancialCards",
                   chunk_path, f"--frames={chunk_start}-{chunk_end}"]
            for attempt in range(3):
                try:
                    logger.info(f"Remotion chunk {chunk_idx}/{chunk_total} attempt {attempt+1}/3...")
                    proc = subprocess.Popen(cmd, cwd=_RE_DIR, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
                    def _stream_chunk():
                        for line in iter(proc.stdout.readline, ""):
                            line = line.rstrip("\n")
                            if line:
                                logger.debug(f"[Remotion chunk{chunk_idx}] {line}")
                    tc = threading.Thread(target=_stream_chunk, daemon=True)
                    tc.start()
                    proc.wait(timeout=360000)
                    tc.join(timeout=10)
                    if proc.returncode != 0:
                        logger.error(f"Remotion chunk fail: exit={proc.returncode}")
                        if attempt < 2:
                            time.sleep(2)  # backoff before retry
                            continue
                        return ""
                    if os.path.exists(chunk_path):
                        chunk_files.append(chunk_path)
                    break
                except subprocess.TimeoutExpired:
                    logger.warning(f"Remotion chunk timeout (attempt {attempt+1})")
                    if attempt >= 2:
                        logger.error("Remotion chunk timeout")
                        return ""

        if not chunk_files:
            return ""

        # ffmpeg concat 拼接
        concat_list = os.path.join(chunk_dir, "concat.txt")
        with open(concat_list, "w") as f:
            for cf in chunk_files:
                f.write(f"file '{cf}'\n")
        logger.info(f"Remotion concat: {len(chunk_files)} 块拼接中...")
        try:
            _stream_run_ffmpeg([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy", abs_out,
            ], label="remotion_concat", check=True, timeout=360000)
        except subprocess.CalledProcessError:
            logger.error("Chunk concat failed")
            return ""

        # 缩放
        if os.path.exists(abs_out):
            tmp = abs_out + ".tmp.mp4"
            logger.info("Remotion 缩放中...")
            _stream_run_ffmpeg([
                "ffmpeg", "-y", "-i", abs_out,
                "-vf", f"scale={self.width}:{self.height}"
                ":force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                "-pix_fmt", "yuv420p", "-r", str(self.fps), tmp,
            ], label="remotion_scale", check=True, timeout=360000)
            os.replace(tmp, abs_out)
            logger.info(f"_gen_remotion_video 完成: {abs_out}")
            shutil.rmtree(chunk_dir, ignore_errors=True)
            return abs_out
        logger.warning("_gen_remotion_video 失败: 缩放后输出不存在")
        shutil.rmtree(chunk_dir, ignore_errors=True)
        return ""

    # ═══════════════════════════════════════════════
    #  模式 4: Manim 动画 (数字滚动 + 过渡效果)
    # ═══════════════════════════════════════════════

    def _gen_manim_video(self, title, segments, duration,
                         output_path, timestamps):
        """Manim: 生成 Python 场景文件 → 渲染为视频"""
        logger.info(f"_gen_manim_video 开始: {len(segments)} segs, {duration:.1f}s")
        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": ""
        }]
        if not ts_list:
            return ""

        # 给每个时间戳关联 LLM 数据
        for ts in ts_list:
            match = self._find_segment_data(ts, segments, timestamps, duration)
            ts["_price"] = match.get("price")
            ts["_change"] = match.get("change_pct")
            ts["_label"] = match.get("time_label", "")

        # 生成 Manim 场景代码
        scene_code = self._build_manim_scene(ts_list, duration)

        import hashlib
        cache_key = hashlib.md5(
            f"{scene_code}|{self.manim_quality}|{self.width}|{self.height}".encode()
        ).hexdigest()[:12]
        manim_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       ".cache", "manim")
        os.makedirs(manim_cache_dir, exist_ok=True)
        cached_mp4 = os.path.join(manim_cache_dir, f"manim_{cache_key}.mp4")
        if os.path.isfile(cached_mp4) and os.path.getsize(cached_mp4) > 1024:
            shutil.copy2(cached_mp4, str(output_path))
            logger.info(f"Manim 缓存命中: {output_path}")
            return str(output_path)

        scene_file = os.path.join(tempfile.gettempdir(), "viz_manim_scene.py")
        with open(scene_file, "w") as f:
            f.write(scene_code)

        # 渲染
        manim_out = os.path.join(tempfile.gettempdir(), "manim_out")
        os.makedirs(manim_out, exist_ok=True)
        _VENV_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv")
        manim_bin = os.path.join(_VENV_DIR, "bin", "manim")
        cmd = [
            manim_bin, f"-{self.manim_quality}", "--format", "mp4",
            scene_file, "FinancialScene",
            "-o", os.path.join(manim_out, "scene.mp4"),
        ]
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        logger.info(f"Manim 渲染: {len(ts_list)} 个数据点, {duration:.1f}s")
        process = subprocess.Popen(cmd, cwd=os.path.dirname(__file__), env=env,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
        last_log = [0.0]
        def _stream():
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if line and time.time() - last_log[0] >= 2.0:
                    logger.info(f"[Manim] {line}")
                    last_log[0] = time.time()
        t = threading.Thread(target=_stream, daemon=True)
        t.start()
        try:
            process.wait(timeout=360000)
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error("Manim 超时 (300s)")
            try:
                os.unlink(scene_file)
            except Exception:
                pass
            shutil.rmtree(manim_out, ignore_errors=True)
            return ""
        t.join(timeout=10)
        if process.returncode != 0:
            logger.error(f"Manim 失败 (exit {process.returncode})")
            try:
                os.unlink(scene_file)
            except Exception:
                pass
            shutil.rmtree(manim_out, ignore_errors=True)
            return ""

        # 找输出文件
        import glob
        candidates = glob.glob(os.path.join(manim_out, "**", "*.mp4"),
                               recursive=True)
        if not candidates:
            logger.error("Manim 未生成输出文件")
            try:
                os.unlink(scene_file)
            except Exception:
                pass
            shutil.rmtree(manim_out, ignore_errors=True)
            return ""

        src = max(candidates, key=os.path.getmtime)
        # 缩放到目标尺寸
        logger.info(f"Manim 缩放: {src} -> {output_path}")
        _stream_run_ffmpeg([
            "ffmpeg", "-y", "-i", src,
            "-vf", f"scale={self.width}:{self.height}"
            ":force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", str(self.fps),
            str(output_path),
        ], label="manim_scale", check=True, timeout=360000)
        shutil.copy2(str(output_path), cached_mp4)
        try:
            os.unlink(scene_file)
        except Exception:
            pass
        shutil.rmtree(manim_out, ignore_errors=True)
        logger.info(f"Manim 完成: {output_path}")
        return str(output_path)

    def _build_manim_scene(self, ts_list: list, total_duration: float) -> str:
        """构建 Manim 场景 Python 代码 — 顺序播放卡牌动画, 每张卡持续对应字幕时长"""
        bg = self.bg_color
        accent = self.accent_color
        up_c = self.color_up
        down_c = self.color_down
        font_name = self._detect_chinese_font()

        cards: list[dict] = []
        for i, ts in enumerate(ts_list):
            price = ts.get("_price")
            change = ts.get("_change")
            text = (ts.get("text") or "").strip()
            seg_dur = max(ts["end"] - ts["start"], 0.6)

            card = {"dur": seg_dur}
            if price is not None:
                color = up_c if (change or 0) >= 0 else down_c if change is not None else accent
                card["price_str"] = f"{price:.1f}"
                card["chg_str"] = ""
                if change is not None:
                    card["chg_str"] = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                card["color"] = color
                card["kind"] = "data"
            elif text:
                card["label"] = text[:40].replace('\n', ' ').replace('"', "'")
                card["color"] = accent
                card["kind"] = "label"
            else:
                continue
            cards.append(card)

        data_json = json.dumps(cards, ensure_ascii=False)

        return f'''# Auto-generated Manim scene — sequential data cards with glow effects
from manim import *
import json

config.disable_latex = True
config.pixel_height = {self.height}
config.pixel_width = {self.width}
config.frame_rate = {self.fps}
config.background_color = "{bg}"

_FONT = "{font_name}"
DATA = {data_json}

class FinancialScene(Scene):
    def construct(self):
        # 动态背景圆点
        dots = VGroup(*[
            Dot(radius=0.02, fill_opacity=0.08, color=WHITE)
            for _ in range(40)
        ])
        for d in dots:
            d.move_to(np.array([
                np.random.uniform(-config.frame_width/2, config.frame_width/2),
                np.random.uniform(-config.frame_height/2, config.frame_height/2),
                0
            ]))
        self.add(dots)

        for idx, card in enumerate(DATA):
            dur = card["dur"]
            color = card["color"]
            objs = []

            if card.get("kind") == "data":
                price = Text(card["price_str"], font_size=72, font=_FONT,
                             weight=BOLD, color=color)
                # 发光光环
                glow = price.copy().set_stroke(color, width=8, opacity=0.3)
                price.move_to(UP * 0.4)
                glow.move_to(UP * 0.4)
                self.add(glow)
                objs.extend([price, glow])

                if card.get("chg_str"):
                    change = Text(card["chg_str"], font_size=44, font=_FONT,
                                  weight=BOLD, color=color)
                    change.next_to(price, DOWN, buff=0.45)
                    objs.append(change)
                else:
                    change = None

                # 入场: 放大弹入
                anims = [GrowFromCenter(price, run_time=0.4),
                         GrowFromCenter(glow, run_time=0.4)]
                if change:
                    anims.append(FadeIn(change, shift=UP * 0.3, run_time=0.35))
                self.play(*anims)

            else:
                label = Text(card["label"], font_size=38, font=_FONT, color=color)
                label.move_to(ORIGIN)
                objs.append(label)
                self.play(FadeIn(label, shift=UP * 0.4, run_time=0.4))

            # 停留
            hold = max(dur - 0.7, 0.15)
            self.wait(hold)

            # 出场
            self.play(*[FadeOut(o, run_time=0.3) for o in objs])

        self.wait(0.3)

    @staticmethod
    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
'''

    def _detect_chinese_font(self) -> str:
        """探测系统可用中文字体"""
        import subprocess
        candidates = ["PingFang SC", "Noto Sans SC", "STHeiti", "Microsoft YaHei", "SimHei", "Arial Unicode MS"]
        try:
            r = subprocess.run(["fc-list", ":lang=zh"], capture_output=True, text=True, timeout=360000)
            available = r.stdout
            for c in candidates:
                if c in available:
                    return c
        except Exception:
            pass
        for c in candidates:
            try:
                from manim import Text
                Text("测", font=c)
                return c
            except Exception:
                continue
        return "Arial"

    # ═══════════════════════════════════════════════
    #  模式 5: Manim 漫画分镜 (速度线+对话框+冲击特效)
    # ═══════════════════════════════════════════════

    def _gen_manim_comic_video(self, title, segments, duration,
                                output_path, timestamps):
        """Manim 漫画: 分镜式漫画动画, 每帧一个漫画格"""
        logger.info(f"_gen_manim_comic_video 开始: {len(segments)} segs, {duration:.1f}s")
        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": ""
        }]
        if not ts_list:
            return ""

        for ts in ts_list:
            match = self._find_segment_data(ts, segments, timestamps, duration)
            ts["_price"] = match.get("price")
            ts["_change"] = match.get("change_pct")
            ts["_label"] = match.get("time_label", "")

        scene_code = self._build_manim_comic_scene(ts_list, duration)

        import hashlib
        cache_key = hashlib.md5(
            f"{scene_code}|{self.manim_quality}|{self.width}|{self.height}".encode()
        ).hexdigest()[:12]
        manim_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       ".cache", "manim")
        os.makedirs(manim_cache_dir, exist_ok=True)
        cached_mp4 = os.path.join(manim_cache_dir, f"manim_comic_{cache_key}.mp4")
        if os.path.isfile(cached_mp4) and os.path.getsize(cached_mp4) > 1024:
            shutil.copy2(cached_mp4, str(output_path))
            logger.info(f"Manim 漫画缓存命中: {output_path}")
            return str(output_path)

        scene_file = os.path.join(tempfile.gettempdir(), "viz_manim_comic.py")
        with open(scene_file, "w") as f:
            f.write(scene_code)

        manim_out = os.path.join(tempfile.gettempdir(), "manim_comic_out")
        os.makedirs(manim_out, exist_ok=True)
        _VENV_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv")
        manim_bin = os.path.join(_VENV_DIR, "bin", "manim")
        cmd = [
            manim_bin, f"-{self.manim_quality}", "--format", "mp4",
            scene_file, "ComicScene",
            "-o", os.path.join(manim_out, "scene.mp4"),
        ]
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        logger.info(f"Manim 漫画渲染: {len(ts_list)} 个分镜, {duration:.1f}s")
        process = subprocess.Popen(cmd, cwd=os.path.dirname(__file__), env=env,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
        last_log = [0.0]
        def _stream():
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if line and time.time() - last_log[0] >= 2.0:
                    logger.info(f"[Manim Comic] {line}")
                    last_log[0] = time.time()
        t = threading.Thread(target=_stream, daemon=True)
        t.start()
        try:
            process.wait(timeout=360000)
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error("Manim 漫画超时 (300s)")
            try:
                os.unlink(scene_file)
            except Exception:
                pass
            shutil.rmtree(manim_out, ignore_errors=True)
            return ""
        t.join(timeout=10)
        if process.returncode != 0:
            logger.error(f"Manim 漫画失败 (exit {process.returncode})")
            try:
                os.unlink(scene_file)
            except Exception:
                pass
            shutil.rmtree(manim_out, ignore_errors=True)
            return ""

        import glob as _glob
        candidates = _glob.glob(os.path.join(manim_out, "**", "*.mp4"), recursive=True)
        if not candidates:
            logger.error("Manim 漫画未生成输出文件")
            try:
                os.unlink(scene_file)
            except Exception:
                pass
            shutil.rmtree(manim_out, ignore_errors=True)
            return ""

        src = max(candidates, key=os.path.getmtime)
        logger.info(f"Manim comic 缩放: {src} -> {output_path}")
        _stream_run_ffmpeg([
            "ffmpeg", "-y", "-i", src,
            "-vf", f"scale={self.width}:{self.height}"
            ":force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", str(self.fps),
            str(output_path),
        ], label="manim_comic_scale", check=True, timeout=360000)
        shutil.copy2(str(output_path), cached_mp4)
        try:
            os.unlink(scene_file)
        except Exception:
            pass
        shutil.rmtree(manim_out, ignore_errors=True)
        logger.info(f"Manim 漫画完成: {output_path}")
        return str(output_path)

    def _build_manim_comic_scene(self, ts_list: list, total_duration: float) -> str:
        """构建漫画分镜 Manim 场景 — 速度线 + 对话框 + 冲击特效"""
        bg = self.bg_color
        accent = self.accent_color
        up_c = self.color_up
        down_c = self.color_down
        font_name = self._detect_chinese_font()

        cards: list[dict] = []
        for i, ts in enumerate(ts_list):
            price = ts.get("_price")
            change = ts.get("_change")
            text = (ts.get("text") or "").strip()
            seg_dur = max(ts["end"] - ts["start"], 0.6)

            card = {"dur": seg_dur}
            if price is not None:
                color = up_c if (change or 0) >= 0 else down_c if change is not None else accent
                card["price_str"] = f"{price:.1f}"
                card["chg_str"] = ""
                if change is not None:
                    card["chg_str"] = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                card["color"] = color
                card["kind"] = "data"
            elif text:
                card["label"] = text[:40].replace('\n', ' ').replace('"', "'")
                card["color"] = accent
                card["kind"] = "label"
            else:
                continue
            cards.append(card)

        data_json = json.dumps(cards, ensure_ascii=False)
        w = self.width / 100.0   # 用于归一化坐标

        return f'''# Auto-generated Manim comic scene — speed lines + bubbles + impact FX
from manim import *
import json, random

config.disable_latex = True
config.pixel_height = {self.height}
config.pixel_width = {self.width}
config.frame_rate = {self.fps}
config.background_color = "{bg}"

_FONT = "{font_name}"
_W = {w}
DATA = {data_json}

class ComicScene(Scene):
    def construct(self):
        for idx, card in enumerate(DATA):
            dur = card["dur"]
            color = card["color"]
            objs = []

            # ── 分镜框 (comic panel border) ──
            panel = Rectangle(
                width=config.frame_width - 0.8, height=config.frame_height - 0.8,
                stroke_color=color, stroke_width=4, stroke_opacity=0.7,
                fill_opacity=0
            )
            panel.move_to(ORIGIN)
            objs.append(panel)

            # ── 速度线 (speed lines, 从四角汇聚) ──
            speed_lines = VGroup()
            for _ in range(12):
                angle = random.uniform(0, TAU)
                length = random.uniform(2, 6)
                start = np.array([
                    random.uniform(-config.frame_width/2, config.frame_width/2),
                    random.uniform(-config.frame_height/2, config.frame_height/2),
                    0
                ])
                end = start + np.array([np.cos(angle), np.sin(angle), 0]) * length
                line = Line(start, end, stroke_color=GRAY, stroke_width=1, stroke_opacity=0.25)
                speed_lines.add(line)
            objs.append(speed_lines)

            # ── 冲击爆发 (starburst around key number) ──
            burst = VGroup()
            for _ in range(8):
                a = random.uniform(0, TAU)
                r = random.uniform(0.8, 1.6)
                end_pt = np.array([np.cos(a) * r, np.sin(a) * r, 0])
                l = Line(ORIGIN, end_pt, stroke_color=color, stroke_width=2, stroke_opacity=0.5)
                burst.add(l)
            objs.append(burst)

            if card.get("kind") == "data":
                # ── 对话框 (speech bubble) ──
                bubble = RoundedRectangle(
                    width=4.5, height=2.2, corner_radius=0.3,
                    stroke_color=color, stroke_width=3, stroke_opacity=0.9,
                    fill_color=BLACK, fill_opacity=0.6
                )
                bubble.move_to(ORIGIN)
                objs.append(bubble)

                price = Text(card["price_str"], font_size=60, font=_FONT,
                             weight=BOLD, color=color)
                price.move_to(UP * 0.3)
                objs.append(price)

                if card.get("chg_str"):
                    change = Text(card["chg_str"], font_size=40, font=_FONT,
                                  weight=BOLD, color=color)
                    change.next_to(price, DOWN, buff=0.4)
                    objs.append(change)
                else:
                    change = None

                # 入场: 分镜框 + 速度线 fade in, 数字 scale bounce
                self.play(
                    FadeIn(panel, run_time=0.25),
                    FadeIn(speed_lines, run_time=0.35),
                    GrowFromCenter(bubble, run_time=0.3),
                    GrowFromCenter(price, run_time=0.4),
                )
                if change:
                    self.play(FadeIn(change, shift=UP * 0.3, run_time=0.3))

                # 冲击爆发一闪
                self.play(FadeIn(burst, run_time=0.15), FadeOut(burst, run_time=0.15))

            else:
                # 纯文字漫画格
                bubble = RoundedRectangle(
                    width=5.5, height=1.8, corner_radius=0.3,
                    stroke_color=color, stroke_width=3, stroke_opacity=0.9,
                    fill_color=BLACK, fill_opacity=0.5
                )
                bubble.move_to(ORIGIN)
                label = Text(card["label"], font_size=34, font=_FONT, color=color)
                label.move_to(ORIGIN)
                objs.extend([bubble, label])

                self.play(
                    FadeIn(panel, run_time=0.25),
                    FadeIn(speed_lines, run_time=0.3),
                    GrowFromCenter(bubble, run_time=0.3),
                    FadeIn(label, shift=UP * 0.3, run_time=0.35),
                )

            # 停留
            hold = max(dur - 0.85, 0.1)
            self.wait(hold)

            # ── 翻页转场 (page turn transition) ──
            self.play(*[FadeOut(o, run_time=0.35, shift=LEFT * 0.5) for o in objs])

        self.wait(0.3)
'''

    # ═══════════════════════════════════════════════
    #  模式 6: Wan2.1 AI 视频生成 (Apple Silicon MLX)
    # ═══════════════════════════════════════════════

    def _gen_wan_video(self, title, segments, duration,
                        output_path, timestamps):
        """Wan2.1: 多句字幕合并为一组, 每组生成一个视频 → 拼接, 管道复用"""
        logger.info(f"_gen_wan_video 开始: {len(segments)} segs, {duration:.1f}s")
        from modules.wan_video import WanVideoGenerator, _extract_visual_prompt

        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": title,
        }]
        ts_list = [t for t in ts_list if (t.get("text") or "").strip()]
        if not ts_list:
            return ""

        # 关联 LLM 数据 (价格/涨跌幅)
        for ts in ts_list:
            match = self._find_segment_data(ts, segments, timestamps, duration)
            ts["_price"] = match.get("price")
            ts["_change"] = match.get("change_pct")

        # 分组: 按总时长聚合, 每组不超过 max_group_dur 秒 (受 Wan2.1 81帧=5s限制)
        max_group_dur = self._config.get("wan_video", {}).get("max_group_dur", 4)
        groups = []
        current_group = []
        current_dur = 0.0
        for ts in ts_list:
            seg_dur = max(ts["end"] - ts["start"], 0.5)
            current_group.append(ts)
            current_dur += seg_dur
            if current_dur >= max_group_dur:
                groups.append(current_group)
                current_group = []
                current_dur = 0.0
        if current_group:
            groups.append(current_group)

        n_groups = len(groups)
        logger.info(f"Wan2.1 时长分组: {len(ts_list)} 句 → {n_groups} 组 (每组≤{max_group_dur}s)")

        gen = WanVideoGenerator(self._config)
        clip_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "wan")
        os.makedirs(clip_dir, exist_ok=True)
        completed = []

        def _seg_frames(dur: float) -> int:
            frames = max(int(dur * 16), 9)
            frames = ((frames - 1) // 4) * 4 + 1
            return min(frames, 81)

        # 构建批量任务: 每组一个视频, 带内容哈希缓存
        import hashlib
        batch = []
        batch_indices = []
        pre_cached = {}
        for gi, group in enumerate(groups):
            texts = [t.get("text", "").strip() for t in group]
            combined = " | ".join(texts)
            total_dur = sum(max(t["end"] - t["start"], 0.8) for t in group)
            n_frames = _seg_frames(total_dur)
            prompt = _extract_visual_prompt(combined, "")
            cache_key = hashlib.md5(
                f"{prompt}|{n_frames}|{self._config.get('wan_video',{}).get('model','')}".encode()
            ).hexdigest()[:12]
            clip_path = os.path.join(clip_dir, f"wan_{cache_key}.mp4")
            logger.info(f"Wan 组 {gi+1}: {len(group)}句, {total_dur:.1f}s → {n_frames}帧")

            if os.path.isfile(clip_path) and os.path.getsize(clip_path) > 1024:
                logger.info(f"Wan 组 {gi+1} 缓存命中")
                pre_cached[gi] = (clip_path, "")
                continue
            batch.append((prompt, clip_path, n_frames))
            batch_indices.append(gi)

        results = {}
        if batch:
            try:
                batch_results = gen.generate_batch(batch, on_clip_done=completed.append)
            except Exception as e:
                logger.error(f"Wan2.1 批量生成崩溃: {e}")
                import traceback
                traceback.print_exc()
                return ""
            for idx, res in zip(batch_indices, batch_results):
                results[idx] = res
        results.update(pre_cached)

        # 每组视频映射到组内所有字幕片段, 带数据叠加文本
        clips: list[tuple] = []  # (path, offset, seg_start, seg_end, overlay_text)
        for gi, group in enumerate(groups):
            path, err = results.get(gi, ("", "missing"))
            if not err and os.path.isfile(path) and os.path.getsize(path) > 1024:
                # 获取实际视频时长 vs 字幕总时长
                group_dur = sum(max(t["end"] - t["start"], 0.5) for t in group)
                actual_dur = group_dur
                try:
                    r = subprocess.run([
                        "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path,
                    ], capture_output=True, text=True, timeout=360000)
                    actual_dur = float(r.stdout.strip()) if r.stdout.strip() else group_dur
                except Exception:
                    pass
                logger.info(f"Wan 组 {gi+1}: 视频 {actual_dur:.1f}s, 字幕 {group_dur:.1f}s")

                offset = 0.0
                for ts in group:
                    seg_dur = max(ts["end"] - ts["start"], 0.5)
                    # cap offset at video duration to avoid seeking past end
                    safe_offset = min(offset, max(actual_dur - 0.1, 0))
                    overlay = ""
                    p = ts.get("_price")
                    c = ts.get("_change")
                    if p is not None:
                        overlay = f"{p:.1f}"
                        if c is not None:
                            overlay += f"  {'+' if c >= 0 else ''}{c:.2f}%"
                    clips.append((path, safe_offset, ts["start"], ts["end"], overlay))
                    offset += seg_dur
            else:
                logger.warning(f"Wan2.1 组 {gi+1} 跳过: err={err}")

        if not clips:
            logger.error("Wan2.1 所有片段生成失败")
            return ""

        result = self._concat_video_clips(clips, str(output_path))
        logger.info(f"_gen_wan_video 完成: {result}")
        return result

    @staticmethod
    def _concat_video_clips(clips: list, output_path: str) -> str:
        """拼接视频片段: [(path, offset, t_start, t_end[, overlay]), ...]"""
        temp_dir = tempfile.mkdtemp()
        scaled_clips = []

        for i, clip in enumerate(clips):
            path = clip[0]
            offset = clip[1]
            t_start = clip[2]
            t_end = clip[3]
            overlay_text = clip[4] if len(clip) >= 5 else ""
            seg_dur = max(t_end - t_start, 0.5)
            seg_out = os.path.join(temp_dir, f"seg_{i:03d}.mp4")
            try:
                vf = "null"
                if overlay_text:
                    # 转义 ffmpeg drawtext 特殊字符
                    escaped = overlay_text.replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
                    font_size = 22 if len(overlay_text) < 20 else 18
                    vf = (f"drawtext=text='{escaped}':"
                          f"fontsize={font_size}:fontcolor=white:x=(w-tw)/2:y=(h-th)/2:"
                          f"box=1:boxcolor=black@0.4")
                _stream_run_ffmpeg([
                    "ffmpeg", "-y",
                    "-ss", str(offset),
                    "-i", path,
                    "-t", str(seg_dur),
                    "-vf", vf,
                    "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                    "-pix_fmt", "yuv420p",
                    seg_out,
                ], label=f"clip_seg_{i:03d}", check=True, timeout=360000)
                scaled_clips.append(seg_out)
            except Exception as e:
                logger.warning(f"ffmpeg 截取片段 {i} 失败: {e}")
                continue

        if not scaled_clips:
            logger.error("无有效片段可拼接")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return ""

        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, "w") as f:
            for s in scaled_clips:
                f.write(f"file '{s}'\n")

        logger.info(f"_concat_video_clips: {len(scaled_clips)} 片段拼接中...")
        try:
            _stream_run_ffmpeg([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                str(output_path),
            ], label="clip_concat", check=True, timeout=360000)
        except Exception as e:
            logger.error(f"ffmpeg 拼接失败: {e}", exc_info=True)
            shutil.rmtree(temp_dir, ignore_errors=True)
            return ""

        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"视频拼接完成: {len(clips)} 片段 → {output_path}")
        return str(output_path)

    # ═══════════════════════════════════════════════
    #  模式 7: Wan2.1 API (Replicate 云端)
    # ═══════════════════════════════════════════════

    def _gen_wan_api_video(self, title, segments, duration,
                            output_path, timestamps):
        """WanAPI: 每句字幕通过 Replicate API 生成视频 → 拼接"""
        logger.info(f"_gen_wan_api_video 开始: {len(segments)} segs, {duration:.1f}s")
        from modules.wan_api import WanApiGenerator, _extract_visual_prompt

        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": title,
        }]
        ts_list = [t for t in ts_list if (t.get("text") or "").strip()]
        if not ts_list:
            return ""

        gen = WanApiGenerator(self._config)
        clip_dir = os.path.join(os.path.dirname(os.path.abspath(str(output_path))), "wan_clips")
        os.makedirs(clip_dir, exist_ok=True)
        completed = []

        def _seg_frames(dur: float) -> int:
            frames = max(int(dur * 16), 9)
            frames = ((frames - 1) // 4) * 4 + 1
            return min(frames, 81)

        batch = []
        for i, ts in enumerate(ts_list):
            text = ts.get("text", "").strip()
            seg_dur = max(ts["end"] - ts["start"], 0.8)
            clip_path = os.path.join(clip_dir, f"wan_{i:03d}.mp4")
            prompt = _extract_visual_prompt(text, "")
            batch.append((prompt, clip_path, _seg_frames(seg_dur)))

        results = gen.generate_batch(batch, on_clip_done=completed.append)

        clips = []
        for i, ((clip_path, err), ts) in enumerate(zip(results, ts_list)):
            if not err and os.path.isfile(clip_path) and os.path.getsize(clip_path) > 1024:
                clips.append((clip_path, ts["start"], ts["end"]))
            else:
                logger.warning(f"WanAPI 片段 {i+1} 跳过: err={err}")

        if not clips:
            return ""
        result = self._concat_video_clips(clips, str(output_path))
        logger.info(f"_gen_wan_api_video 完成: {result}")
        return result

    # ═══════════════════════════════════════════════
    #  模式 8: 阿里百炼 Wan2.1 API (支付宝)
    # ═══════════════════════════════════════════════

    def _gen_bailian_video(self, title, segments, duration,
                            output_path, timestamps):
        """百炼: 每句字幕通过 DashScope API 生成视频 → 拼接"""
        logger.info(f"_gen_bailian_video 开始: {len(segments)} segs, {duration:.1f}s")
        from modules.wan_bailian import BailianGenerator, _extract_visual_prompt

        ts_list = timestamps if timestamps else [{
            "start": 0, "end": duration, "text": title,
        }]
        ts_list = [t for t in ts_list if (t.get("text") or "").strip()]
        if not ts_list:
            return ""

        gen = BailianGenerator(self._config)
        clip_dir = os.path.join(os.path.dirname(os.path.abspath(str(output_path))), "wan_clips")
        os.makedirs(clip_dir, exist_ok=True)
        completed = []

        batch = []
        for i, ts in enumerate(ts_list):
            text = ts.get("text", "").strip()
            seg_dur = max(int(ts["end"] - ts["start"]), 2)  # 百炼要求 2-15 秒
            clip_path = os.path.join(clip_dir, f"wan_{i:03d}.mp4")
            prompt = _extract_visual_prompt(text, "")
            batch.append((prompt, clip_path, seg_dur))

        results = gen.generate_batch(batch, on_clip_done=completed.append)

        clips = []
        for i, ((clip_path, err), ts) in enumerate(zip(results, ts_list)):
            if not err and os.path.isfile(clip_path) and os.path.getsize(clip_path) > 1024:
                clips.append((clip_path, ts["start"], ts["end"]))
            else:
                logger.warning(f"百炼 片段 {i+1} 跳过: err={err}")

        if not clips:
            return ""
        result = self._concat_video_clips(clips, str(output_path))
        logger.info(f"_gen_bailian_video 完成: {result}")
        return result

    # ═══════════════════════════════════════════════
    #  封面帧
    # ═══════════════════════════════════════════════

    def _make_cover_frame(self, script_text: str = "") -> str:
        """生成封面 PNG: 日期居中。优先从文案提取，否则用当天。带缓存"""
        logger.info("_make_cover_frame 开始...")
        import hashlib
        from datetime import date
        today = date.today().strftime("%Y/%m/%d")

        # 尝试从文案中提取日期
        extracted = None
        patterns = [
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"(\d{4})/(\d{1,2})/(\d{1,2})",
            r"(\d{1,2})月(\d{1,2})日",
        ]
        for pat in patterns:
            m = re.search(pat, script_text)
            if m:
                g = m.groups()
                if len(g) == 3:
                    extracted = f"{g[0]}/{int(g[1]):02d}/{int(g[2]):02d}"
                elif len(g) == 2:
                    extracted = f"{date.today().year}/{int(g[0]):02d}/{int(g[1]):02d}"
                break

        display_date = extracted or today
        cache_key = hashlib.md5(
            f"cover|{display_date}|{self.width}|{self.height}|{self.bg_color}".encode()
        ).hexdigest()[:12]
        cover_cache = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   ".cache", "cover")
        os.makedirs(cover_cache, exist_ok=True)
        path = os.path.join(cover_cache, f"cover_{cache_key}.png")
        if os.path.isfile(path) and os.path.getsize(path) > 1024:
            return path

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        self._setup_chinese_font(font_manager, matplotlib)
        date_color = "#FFFFFF"     # 白色字体
        pill_color = "#DA4E48"      # 红色背景

        dpi = 100
        fig_w, fig_h = self.width / dpi, self.height / dpi
        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi,
                         facecolor=self.bg_color)
        ax = fig.add_axes([0, 0, 1, 1], facecolor=self.bg_color)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        # 先量文字大小，再画 pill (20px padding)
        from matplotlib.patches import FancyBboxPatch
        # 用 renderer 量文字
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        t = ax.text(0.5, 0.5, display_date, transform=ax.transAxes,
                     fontsize=65, fontweight="bold", color=date_color,
                     ha="center", va="center")
        bbox = t.get_window_extent(renderer=renderer)
        t.remove()
        # 转成 axes 坐标
        inv = ax.transAxes.inverted()
        bbox_ax = inv.transform(bbox)
        tw = bbox_ax[1][0] - bbox_ax[0][0]
        th = bbox_ax[1][1] - bbox_ax[0][1]
        bw, bh = tw, th  # 紧贴文字，无 padding
        bx, by = 0.5 - bw / 2, 0.5 - bh / 2
        pill = FancyBboxPatch((bx, by), bw, bh,
                              boxstyle=f"round,pad=0.02",
                              facecolor=pill_color,
                              edgecolor="none",
                              transform=ax.transAxes)
        ax.add_patch(pill)
        # 日期居中
        ax.text(0.5, 0.5, display_date, transform=ax.transAxes,
                fontsize=65, fontweight="bold", color=date_color,
                ha="center", va="center")

        path = os.path.join(cover_cache, f"cover_{cache_key}.png")
        fig.savefig(path, dpi=dpi, facecolor=self.bg_color,
                    pad_inches=0)
        plt.close(fig)
        logger.info(f"_make_cover_frame 完成: {path}")
        return path

    def _make_cover_video(self, cover_path: str) -> str:
        self._cover_dur = 1.5
        covered = cover_path + ".cover.mp4"
        if os.path.isfile(covered) and os.path.getsize(covered) > 1024:
            return covered
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(self._cover_dur), "-i", cover_path,
            "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", "30",
            covered,
        ]
        self._stream_run(cmd, label="make_cover_video", check=True, timeout=60)
        return covered

    def _prepend_cover(self, cover_path: str, main_video: str,
                       output_path: str = "") -> str:
        """封面 1.5s + 主视频 = 最终视频。输出到缓存目录(main_video.covered.mp4)"""
        cover_dur = 1.5
        covered = main_video + ".covered.mp4"
        logger.info(f"_prepend_cover 开始: cover={os.path.basename(cover_path)}, main={os.path.basename(main_video)}")
        try:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", str(self._cover_dur), "-i", cover_path,
                "-i", main_video,
                "-filter_complex",
                f"[0:v]scale={self.width}:{self.height}"
                ":force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1[cover];"
                f"[cover][1:v]concat=n=2:v=1:a=0[outv]",
                "-map", "[outv]",
                "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                "-pix_fmt", "yuv420p", "-r", str(self.fps),
                covered,
            ]
            self._stream_run(cmd, label="prepend_cover", check=True, timeout=360000)
            logger.info(f"_prepend_cover 完成: {covered}")
            return covered
        except Exception as e:
            logger.error(f"ffmpeg 封面拼接失败: {e}", exc_info=True)
            return main_video

    # ═══════════════════════════════════════════════
    #  公共: ffmpeg 幻灯片合成
    # ═══════════════════════════════════════════════

    def _concat_slides(self, img_files: list, output_path: str) -> str:
        if self.comic_style and len(img_files) > 1:
            return self._concat_slides_kenburns(img_files, output_path)

        inputs = []
        filters = []
        for i, (img_path, t_start, t_end) in enumerate(img_files):
            seg_dur = max(t_end - t_start, 0.5)
            inputs.extend(["-loop", "1", "-t", f"{seg_dur:.3f}", "-i", img_path])
            filters.append(
                f"[{i}:v]scale={self.width}:{self.height}"
                f":force_original_aspect_ratio=decrease,"
                f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}]")

        filter_str = ";".join(filters) + ";"
        concat_inputs = "".join(f"[v{i}]" for i in range(len(img_files)))
        filter_str += f"{concat_inputs}concat=n={len(img_files)}:v=1:a=0[outv]"

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_str,
            "-map", "[outv]", "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", str(self.fps), output_path,
        ]
        logger.info(f"_concat_slides: {len(img_files)} 图片拼接中...")
        try:
            _stream_run_ffmpeg(cmd, label="concat_slides", check=True, timeout=360000)
            logger.info("_concat_slides 完成")
        except Exception as e:
            logger.error(f"ffmpeg 幻灯片拼接失败: {e}", exc_info=True)
        return output_path

    def _concat_slides_kenburns(self, img_files: list, output_path: str) -> str:
        """Ken Burns 运镜: 每张图确定性运镜, 生成动态片段后拼接, 带缓存"""
        import hashlib
        effects = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
        kb_cache = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                ".cache", "kb")
        os.makedirs(kb_cache, exist_ok=True)
        segments = []
        logger.info(f"Ken Burns 开始: {len(img_files)} 张图, fps={self.fps}, {self.width}x{self.height}")

        _kb_ver = "unknown"
        try:
            r = subprocess.run(["git", "-C", os.path.dirname(__file__),
                "rev-parse", "HEAD"], capture_output=True, text=True, timeout=360000)
            _kb_ver = r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
        except Exception:
            logger.debug("git rev-parse failed, cache key without version", exc_info=True)

        for i, (img_path, t_start, t_end) in enumerate(img_files):
            seg_dur = max(t_end - t_start, 1.0)
            total_frames = round(seg_dur * self.fps)

            effect = effects[i % len(effects)]
            cache_key = hashlib.md5(
                f"{_kb_ver}|{img_path}|{effect}|{seg_dur:.1f}|{self.width}|{self.height}".encode()
            ).hexdigest()[:12]
            seg_out = os.path.join(kb_cache, f"kb_{cache_key}.mp4")

            if os.path.isfile(seg_out) and os.path.getsize(seg_out) > 1024:
                logger.info(f"KB {i+1}/{len(img_files)} {effect} 缓存命中")
                segments.append(seg_out)
                continue

            if effect == "zoom_in":
                zoom_expr = "min(zoom+0.002,1.3)"
                x_expr = "iw/2-(iw/zoom/2)"
                y_expr = "ih/2-(ih/zoom/2)"
            elif effect == "zoom_out":
                zoom_expr = "max(zoom-0.002,1.0)"
                x_expr = "iw/2-(iw/zoom/2)"
                y_expr = "ih/2-(ih/zoom/2)"
            elif effect == "pan_left":
                zoom_expr = "1.05"
                x_expr = "clip(iw/2-(iw/zoom/2)+on*3, 0, iw-iw/zoom)"
                y_expr = "ih/2-(ih/zoom/2)"
            elif effect == "pan_right":
                zoom_expr = "1.05"
                x_expr = "clip(iw/2-(iw/zoom/2)-on*3, 0, iw-iw/zoom)"
                y_expr = "ih/2-(ih/zoom/2)"
            else:
                logger.warning(f"KB 未知效果: {effect}, fallback 到 pan_right")
                zoom_expr = "1.05"
                x_expr = "clip(iw/2-(iw/zoom/2)-on*3, 0, iw-iw/zoom)"
                y_expr = "ih/2-(ih/zoom/2)"

            zoompan = (
                f"zoompan="
                f"z='{zoom_expr}':"
                f"x='{x_expr}':"
                f"y='{y_expr}':"
                f"d={total_frames}:"
                f"s={self.width}x{self.height}"
            )

            try:
                prefix = f"KB {i+1}/{len(img_files)} "
                cmd = [
                    "ffmpeg", "-y",
                    "-framerate", "1", "-i", img_path,
                    "-vf", zoompan,
                    "-c:v", "libx264", "-crf", "28", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-r", str(self.fps),
                    "-frames:v", str(total_frames),
                    seg_out,
                ]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT,
                                            text=True, bufsize=1)
                def _stream():
                    for line in iter(process.stdout.readline, ""):
                        line = line.rstrip("\n")
                        if line:
                            logger.info(f"{prefix}{line}")
                t = threading.Thread(target=_stream, daemon=True)
                t.start()
                logger.info(f"{prefix}{effect}, {seg_dur:.1f}s, {total_frames}f, PID={process.pid}")
                process.wait(timeout=360000)
                t.join(timeout=10)
                if process.returncode != 0:
                    logger.warning(f"{prefix}ffmpeg 退出码 {process.returncode}")
                    continue
                if not os.path.isfile(seg_out):
                    logger.warning(f"{prefix}产出文件缺失")
                    continue
                segments.append(seg_out)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    logger.debug("process.kill() 失败", exc_info=True)
                logger.warning(f"KB {i+1}/{len(img_files)} {effect} 超时")
                continue
            except Exception as e:
                logger.error(f"KB {i+1}/{len(img_files)} {effect} 异常: {e}", exc_info=True)
                continue

        # 拼接所有片段 — 使用 concat FILTER (非 demuxer)，PTS 完全可控
        if not segments:
            logger.warning(f"Ken Burns 所有 {len(img_files)} 个片段均失败, 无法生成全景视频")
            return ""

        # concat 结果缓存: 段路径列表+参数哈希
        _kbc_ver = "unknown"
        try:
            r = subprocess.run(["git", "-C", os.path.dirname(__file__),
                "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
            _kbc_ver = r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
        except Exception:
            logger.debug("git rev-parse failed, concat cache key without version", exc_info=True)
        concat_cache_key = hashlib.md5(
            (_kbc_ver + "|" + "|".join(sorted(segments)) + f"|{self.fps}|{self.width}|{self.height}").encode()
        ).hexdigest()[:16]
        concat_cached = os.path.join(kb_cache, f"kb_concat_{concat_cache_key}.mp4")
        if os.path.isfile(concat_cached) and os.path.getsize(concat_cached) > 1024:
            logger.info(f"Ken Burns concat 缓存命中 ({len(segments)} 段)")
            return concat_cached

        if len(segments) == 1:
            logger.info(f"Ken Burns: 仅1个片段, 直接使用")
            try:
                shutil.copy2(segments[0], concat_cached)
            except Exception as e:
                logger.debug(f"KB concat 缓存写入失败(无影响): {e}")
            return concat_cached

        logger.info(f"Ken Burns concat FILTER: {len(segments)} 片段拼接中...")
        inputs = []
        filter_parts = []
        for i, seg in enumerate(segments):
            inputs.extend(["-i", seg])
            filter_parts.append(f"[{i}:v]")
        filter_str = "".join(filter_parts) + f"concat=n={len(segments)}:v=1:a=0[outv]"
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_str,
            "-map", "[outv]",
            "-c:v", "libx264", "-crf", "28", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", str(self.fps),
            concat_cached,
        ]
        try:
            _stream_run_ffmpeg(cmd, label="kenburns_concat", check=True, timeout=360000)
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg Ken Burns 拼接失败 (exit {e.returncode})")
            return ""
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg Ken Burns 拼接超时")
            return ""
        except Exception as e:
            logger.error(f"ffmpeg Ken Burns 拼接失败: {e}", exc_info=True)
            return ""
        if not os.path.isfile(concat_cached) or os.path.getsize(concat_cached) < 1024:
            logger.error(f"Ken Burns 产出验证失败: {concat_cached} 不存在或过小")
            return ""

        logger.info(f"Ken Burns 运镜完成: {len(segments)}/{len(img_files)} 片段成功")
        return concat_cached

    @staticmethod
    def _setup_chinese_font(font_manager, matplotlib):
        candidates = [
            "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    font_manager.fontManager.addfont(path)
                    prop = font_manager.FontProperties(fname=path)
                    matplotlib.rcParams["font.family"] = prop.get_name()
                    return
                except Exception:
                    logger.debug(f"字体加载失败: {path}")
                    continue
