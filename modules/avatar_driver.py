"""
数字人驱动模块
使用 MuseTalk 将图片和音频合成为口播视频

输入: 数字人图片 + 音频文件
输出: 口播视频 (数字人根据音频说话)
"""

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AvatarDriver:
    """数字人驱动 — 图片+音频→口播视频 (MuseTalk)"""

    def __init__(self, config: dict):
        cfg = config.get("avatar", {})
        self.provider = cfg.get("provider", "musetalk")
        self.fallback_image_mode = cfg.get("fallback_image_mode", True)

        paths_cfg = config.get("paths", {})
        self.musetalk_dir = os.path.expanduser(
            paths_cfg.get("musetalk_dir", "~/code/git-hub/dunso/musetalk-mac")
        )

    def check_availability(self) -> bool:
        """检查 MuseTalk 是否已安装"""
        if not os.path.isdir(self.musetalk_dir):
            logger.warning(f"MuseTalk 目录不存在: {self.musetalk_dir}")
            return False

        musetalk_python = os.path.join(self.musetalk_dir, ".venv", "bin", "python3")
        upstream = os.path.join(self.musetalk_dir, "upstream")
        models = os.path.join(upstream, "models")

        if not os.path.isfile(musetalk_python):
            logger.warning(f"MuseTalk Python 不存在: {musetalk_python}")
            return False

        if not os.path.isdir(models):
            logger.warning(f"MuseTalk 模型目录不存在: {models}")
            return False

        logger.info(f"MuseTalk 可用: {self.musetalk_dir}")
        return True

    def generate(self, src_image: str, dri_audio: str, output_path: str) -> str:
        """生成数字人视频"""
        logger.info(f"AvatarDriver.generate() 开始: provider={self.provider}, image={os.path.basename(src_image)}")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.check_availability():
            if self.fallback_image_mode:
                logger.warning("MuseTalk 不可用，使用静态图片回退模式")
                return self._generate_fallback(src_image, dri_audio, str(output_path))
            raise RuntimeError(
                "MuseTalk 不可用。\n"
                f"请安装到 {self.musetalk_dir}\n"
                "  或设置 avatar.fallback_image_mode: true"
            )

        return self._generate_musetalk(src_image, dri_audio, str(output_path))

    def _generate_musetalk(self, src_image: str, dri_audio: str, output_path: str) -> str:
        """MuseTalk 音频驱动唇形同步"""
        logger.info(f"_generate_musetalk 开始: image={os.path.basename(src_image)}")
        import yaml

        # 生成 MuseTalk 配置文件
        config = {
            "task_0": {
                "video_path": os.path.abspath(src_image),
                "audio_path": os.path.abspath(dri_audio),
            }
        }
        cfg_path = os.path.join(tempfile.gettempdir(), "musetalk_cfg.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(config, f)

        # 运行推理
        musetalk_python = os.path.join(self.musetalk_dir, ".venv", "bin", "python3")
        result_dir = os.path.join(tempfile.gettempdir(), "musetalk_results")
        os.makedirs(result_dir, exist_ok=True)
        upstream = os.path.join(self.musetalk_dir, "upstream")
        models = os.path.join(upstream, "models")

        cmd = [
            musetalk_python, "-m", "scripts.inference",
            "--inference_config", cfg_path,
            "--result_dir", result_dir,
            "--unet_model_path", os.path.join(models, "musetalkV15", "unet.pth"),
            "--unet_config", os.path.join(models, "musetalkV15", "musetalk.json"),
            "--whisper_dir", os.path.join(models, "whisper"),
            "--version", "v15",
            "--batch_size", "4",
            "--fps", "25",
        ]
        env = os.environ.copy()
        env["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
        env["GLOG_minloglevel"] = "2"
        env["PYTHONPATH"] = upstream

        import threading, hashlib
        # 缓存: 图片内容 + 音频内容 hash，相同内容复用
        img_abs = os.path.abspath(src_image)
        try:
            img_size = os.path.getsize(img_abs)
            with open(img_abs, "rb") as imf:
                img_head = imf.read(65536)
            img_hash = hashlib.md5(img_head + str(img_size).encode()).hexdigest()[:12]
        except Exception as e:
            logger.debug(f"图片hash失败, fallback: {e}")
            img_hash = os.path.basename(img_abs)
        try:
            aud_size = os.path.getsize(dri_audio)
            with open(dri_audio, "rb") as af:
                aud_head = af.read(65536)
            aud_hash = hashlib.md5(aud_head + str(aud_size).encode()).hexdigest()[:12]
        except Exception as e:
            logger.debug(f"音频hash失败, fallback: {e}")
            aud_hash = os.path.basename(dri_audio)
        # 用 git HEAD 作版本号，代码变了缓存自动失效
        _ver = "unknown"
        try:
            r = subprocess.run(["git", "-C", os.path.dirname(__file__),
                "rev-parse", "HEAD"], capture_output=True, text=True, timeout=360000)
            _ver = r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
        except Exception as e:
            logger.debug(f"git版本获取失败: {e}")
        cache_key = hashlib.md5(f"{_ver}|{img_hash}|{aud_hash}".encode()).hexdigest()[:12]
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "musetalk")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{cache_key}.mp4")
        if os.path.exists(cache_path):
            logger.info(f"MuseTalk 命中缓存, 跳过推理: {cache_key}")
            shutil.copy(cache_path, output_path)
            return str(output_path)

        logger.info(f"MuseTalk 推理: {os.path.basename(src_image)} + audio")

        # 获取音频时长, 超时设为时长×20 (保守)
        try:
            dur_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", dri_audio],
                capture_output=True, text=True, timeout=360000)
            audio_dur = float(dur_result.stdout.strip())
        except Exception:
            logger.debug("ffprobe 失败, 默认音频10s")
            audio_dur = 10
        mt_timeout = max(int(audio_dur * 20), 120)
        logger.info(f"MuseTalk 开始 (音频 {audio_dur:.0f}s, 超时 {mt_timeout}s)...")

        # 用 Popen 流式输出, 实时打到日志
        process = subprocess.Popen(cmd, cwd=upstream, env=env,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
        last_log = [0.0]
        def _stream():
            for line in iter(process.stdout.readline, ""):
                line = line.strip()
                if line:
                    # 每秒最多打一行, 避免刷屏
                    now = time.time()
                    if "frame" in line.lower():
                        if now - last_log[0] >= 2.0:
                            logger.info(f"[MuseTalk 渲染] {line}")
                            last_log[0] = now
                    elif "%" in line or "it/s" in line or "it]" in line:
                        if now - last_log[0] >= 2.0:
                            logger.info(f"[MuseTalk 分析] {line}")
                            last_log[0] = now
                    else:
                        logger.warning(f"[MuseTalk] {line}")
        t = threading.Thread(target=_stream, daemon=True)
        t.start()

        try:
            process.wait(timeout=mt_timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            logger.error(f"MuseTalk 超时 ({mt_timeout}s)")
            try:
                os.unlink(cfg_path)
            except Exception:
                pass
            try:
                shutil.rmtree(result_dir, ignore_errors=True)
            except Exception:
                pass
            raise RuntimeError(f"MuseTalk 超时 ({mt_timeout}s)")
        t.join(timeout=360000)

        if process.returncode != 0:
            logger.error(f"MuseTalk 失败 (exit {process.returncode})")
            try:
                os.unlink(cfg_path)
            except Exception:
                pass
            try:
                shutil.rmtree(result_dir, ignore_errors=True)
            except Exception:
                pass
            raise RuntimeError(f"MuseTalk 失败 (exit {process.returncode})")

        # 找输出文件
        import glob
        candidates = glob.glob(os.path.join(result_dir, "**", "*.mp4"), recursive=True)
        if candidates:
            latest = max(candidates, key=os.path.getmtime)
            shutil.copy(latest, output_path)
            try:
                shutil.copy(latest, cache_path)
            except Exception as e:
                logger.debug(f"缓存写入失败 (无影响): {e}")
            logger.info(f"_generate_musetalk 完成: {output_path}")
            try:
                os.unlink(cfg_path)
            except Exception:
                pass
            try:
                shutil.rmtree(result_dir, ignore_errors=True)
            except Exception:
                pass
            return str(output_path)
        try:
            os.unlink(cfg_path)
        except Exception:
            pass
        try:
            shutil.rmtree(result_dir, ignore_errors=True)
        except Exception:
            pass
        raise RuntimeError("MuseTalk 输出文件未找到")

    def _generate_fallback(self, src_image: str, dri_audio: str, output_path: str) -> str:
        """
        回退模式：使用 ffmpeg 将静态图片和音频合成视频
        没有数字人动画，但可以保证 pipeline 完整运行
        """
        logger.info(f"_generate_fallback 开始: image={os.path.basename(src_image)}")
        output_path = Path(output_path)

        # 获取音频时长
        duration = None
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", dri_audio],
                capture_output=True, text=True, timeout=360000,
            )
            duration = float(result.stdout.strip())
        except Exception:
            logger.debug("ffprobe 失败, 默认10s")
            duration = 10.0

        logger.info(f"回退模式：静态图片 + 音频, 时长={duration:.1f}s")

        # 使用 ffmpeg 合成 (简化版，不依赖 drawtext)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", src_image,
            "-i", dri_audio,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            str(output_path),
        ]

        logger.info(f"回退 ffmpeg 启动: {src_image} + {dri_audio} -> {output_path}")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        def _stream():
            for line in iter(process.stdout.readline, ""):
                line = line.rstrip("\n")
                if line:
                    logger.debug(f"[avatar_fallback] {line}")
        t = threading.Thread(target=_stream, daemon=True)
        t.start()
        logger.info(f"[avatar_fallback] ffmpeg PID={process.pid}, 等待完成...")
        try:
            process.wait(timeout=360000)
        except subprocess.TimeoutExpired:
            logger.error("[avatar_fallback] ffmpeg 超时")
            process.kill()
        t.join(timeout=10)
        if process.returncode != 0:
            logger.error(f"[avatar_fallback] ffmpeg 退出码={process.returncode}")
        logger.info(f"回退视频生成完成: {output_path}")
        return str(output_path)
