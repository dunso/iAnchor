"""
TTS 音频生成模块 — Edge TTS / Bark / CosyVoice

输入: 口播文本
输出: WAV 音频文件 + 时间戳
"""

import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class TTSGenerator:
    """TTS 语音合成 — 支持 Edge TTS、Bark、CosyVoice"""

    def __init__(self, config: dict):
        cfg = config.get("tts", {})
        self.provider = cfg.get("provider", "edge_tts")
        # Edge TTS 配置
        self.edge_voice = cfg.get("edge_voice", "zh-CN-YunyangNeural")
        self.edge_speed = cfg.get("edge_speed", "+10%")  # 语速调整
        # Bark 配置
        self.bark_voice = cfg.get("bark_voice", "v2/zh_speaker_8")
        self.speed = cfg.get("speed", 1.3)
        # CosyVoice 配置
        self.cosyvoice_dir = os.path.expanduser(
            config.get("paths", {}).get("cosyvoice_dir", "~/CosyVoice-mps")
        )

    def check_edge_tts(self) -> bool:
        """检查 Edge TTS 是否可用"""
        try:
            import edge_tts  # noqa: F401
            logger.info("Edge TTS 可用")
            return True
        except ImportError:
            return False

    def check_bark(self) -> bool:
        """检查 Bark TTS 是否可用"""
        try:
            import bark  # noqa: F401
            logger.info("Bark TTS 可用")
            return True
        except ImportError:
            return False

    def check_cosyvoice(self) -> bool:
        """检查 CosyVoice 是否可用"""
        cosyvoice_python = os.path.join(self.cosyvoice_dir, ".venv", "bin", "python3")
        if not os.path.isfile(cosyvoice_python):
            return False
        logger.info(f"CosyVoice 可用: {self.cosyvoice_dir}")
        return True

    def generate(self, text: str, output_path: str) -> dict:
        logger.info(f"TTSGenerator.generate() 开始: provider={self.provider}, text={text[:30]}...")
        """
        生成 TTS 音频。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._clean_text(text)

        if self.provider == "edge_tts":
            return self._generate_edge_tts(text, str(output_path))
        elif self.provider == "cosyvoice":
            return self._generate_cosyvoice(text, str(output_path))
        else:  # bark
            return self._generate_bark(text, str(output_path))

    # ─── Edge TTS 核心 ──────────────────────────────

    def _generate_edge_tts(self, text: str, output_path: str) -> dict:
        """微软 Edge TTS 在线生成"""
        import edge_tts, hashlib
        import asyncio

        # 缓存
        # 用 git HEAD 作版本号，代码变了缓存自动失效
        _ver = "unknown"
        try:
            r = subprocess.run(["git", "-C", os.path.dirname(__file__),
                "rev-parse", "HEAD"], capture_output=True, text=True, timeout=360000)
            _ver = r.stdout.strip()[:8] if r.returncode == 0 else "unknown"
        except Exception as e:
            logger.debug(f"git版本获取失败: {e}")
        cache_key = hashlib.md5(f"{_ver}|".encode() +
            f"{text}|{self.edge_voice}|{self.edge_speed}".encode()).hexdigest()[:12]
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache", "tts")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, f"{cache_key}.wav")
        if os.path.exists(cache_path):
            logger.info(f"TTS 命中缓存: {text[:30]}...")
            shutil.copy(cache_path, output_path)
            duration = self.get_audio_duration(output_path)
            return {"audio_path": output_path, "duration": duration,
                    "timestamps": self._estimate_timestamps(text, duration)}

        async def _gen():
            communicate = edge_tts.Communicate(text, self.edge_voice,
                                               rate=self.edge_speed)
            await communicate.save(output_path)

        logger.info(f"TTS: {text[:30]}...")
        asyncio.run(_gen())

        # Edge TTS 输出 MP3，用 ffmpeg 转 WAV
        tmp_mp3 = output_path + ".mp3"
        os.rename(output_path, tmp_mp3)
        logger.info("Edge TTS ffmpeg MP3->WAV 转换...")
        process = subprocess.Popen(
            ["ffmpeg", "-y", "-i", tmp_mp3, "-ar", "16000", "-ac", "1",
             output_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        def _stream():
            for line in iter(process.stdout.readline, ""):
                line = line.rstrip("\n")
                if line:
                    logger.info(f"[tts_ffmpeg] {line}")
        t = threading.Thread(target=_stream, daemon=True)
        t.start()
        process.wait(timeout=360000)
        t.join(timeout=10)
        if process.returncode != 0:
            logger.error(f"[tts_ffmpeg] 退出码={process.returncode}")
        os.remove(tmp_mp3)
        # 存入缓存
        try:
            shutil.copy(output_path, cache_path)
        except Exception as e:
            logger.debug(f"TTS缓存写入失败(无影响): {e}")

        duration = self.get_audio_duration(output_path)
        timestamps = self._estimate_timestamps(text, duration)

        logger.info(f"Edge TTS 完成: {output_path} ({duration:.1f}s)")
        return {
            "audio_path": output_path,
            "duration": duration,
            "timestamps": timestamps,
        }

    # ─── CosyVoice 核心 ──────────────────────────────

    def _generate_cosyvoice(self, text: str, output_path: str) -> dict:
        """CosyVoice 本地生成"""
        cosyvoice_python = os.path.join(self.cosyvoice_dir, ".venv", "bin", "python3")
        infer_script = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "modules", "cosyvoice_infer.py"
        )

        logger.info(f"CosyVoice 生成中: {text[:30]}...")

        cmd = [cosyvoice_python, infer_script, text, output_path]
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PIP_REQUIRE_VIRTUALENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)

        logger.info(f"CosyVoice subprocess 启动: {cmd[0]} {cmd[1]} ...")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, env=env)
        def _stream():
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip("\n")
                if line:
                    logger.info(f"[CosyVoice] {line}")
        t = threading.Thread(target=_stream, daemon=True)
        t.start()
        logger.info(f"[CosyVoice] PID={proc.pid}, 等待完成...")
        proc.wait(timeout=360000)
        t.join(timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(f"CosyVoice 失败: exit={proc.returncode}")

        duration = self.get_audio_duration(output_path)
        timestamps = self._estimate_timestamps(text, duration)

        logger.info(f"CosyVoice 完成: {output_path} ({duration:.1f}s)")
        return {
            "audio_path": output_path,
            "duration": duration,
            "timestamps": timestamps,
        }

    # ─── Bark 核心 ──────────────────────────────────

    def _generate_bark(self, text: str, output_path: str) -> dict:
        """Bark TTS 本地生成"""
        import numpy as np
        from bark import SAMPLE_RATE, generate_audio, preload_models
        from scipy.io.wavfile import write as write_wav

        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

        import torch
        torch.serialization.add_safe_globals([np.core.multiarray.scalar])
        _orig_load = torch.load
        torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, 'weights_only': False})
        try:
            preload_models()
        finally:
            torch.load = _orig_load

        logger.info(f"Bark 生成中: {text[:30]}...")
        audio_array = generate_audio(text, history_prompt=self.bark_voice)

        tmp_path = output_path.replace(".wav", "_24k.wav")
        write_wav(tmp_path, SAMPLE_RATE, audio_array.astype(np.float32))
        speed_filter = f"atempo={self.speed}" if self.speed != 1.0 else "anull"
        logger.info("Bark ffmpeg 24k->16k 转换...")
        process2 = subprocess.Popen(
            ["ffmpeg", "-y", "-i", tmp_path, "-af", speed_filter,
             "-ar", "16000", "-ac", "1", output_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        def _stream2():
            for line in iter(process2.stdout.readline, ""):
                line = line.rstrip("\n")
                if line:
                    logger.info(f"[bark_ffmpeg] {line}")
        t2 = threading.Thread(target=_stream2, daemon=True)
        t2.start()
        process2.wait(timeout=360000)
        t2.join(timeout=10)
        if process2.returncode != 0:
            logger.error(f"[bark_ffmpeg] 退出码={process2.returncode}")
        os.remove(tmp_path)

        duration = self.get_audio_duration(output_path)
        timestamps = self._estimate_timestamps(text, duration)

        logger.info(f"Bark TTS 完成: {output_path} ({duration:.1f}s, 16kHz)")
        return {
            "audio_path": output_path,
            "duration": duration,
            "timestamps": timestamps,
        }

    # ─── 工具 ──────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        text = re.sub(r"[{}\[\]]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True, timeout=360000,
            )
            return float(result.stdout.strip())
        except Exception:
            logger.debug("ffprobe 失败, 默认2s")
            return 2.0

    @staticmethod
    def _estimate_timestamps(text: str, total_duration: float) -> list[dict]:
        # 按标点拆短句，逐句展示
        parts = re.split(r"(?<=[。！？；\n])\s*", text)
        phrases = []
        for part in parts:
            sub = re.split(r"(?<=[，、：,])\s*", part)
            for s in sub:
                s = s.strip()
                if s:
                    s = re.sub(r"[，。！？；：、,\.\!\?\;\:\n]+$", "", s).strip()
                    if s:
                        phrases.append(s)

        if len(phrases) <= 1:
            clean = re.sub(r"[，。！？；：、,\.\!\?\;\:\n]+$", "", text.strip())
            return [{"start": 0, "end": total_duration, "text": clean or text.strip()}]

        total_chars = sum(len(p) for p in phrases)
        if total_chars == 0:
            return [{"start": 0, "end": total_duration, "text": text}]

        timestamps = []
        current = 0.0
        for phrase in phrases:
            seg_duration = (len(phrase) / total_chars) * total_duration
            timestamps.append({
                "start": round(current, 2),
                "end": round(current + seg_duration, 2),
                "text": phrase,
            })
            current += seg_duration

        return timestamps
