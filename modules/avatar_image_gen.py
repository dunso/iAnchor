"""
主播形象图生成模块
文案/主题 → LLM 设计人设 → 文生图生成高清主播肖像 (供 MuseTalk 唇形驱动)

Provider:
  - mflux: 本地 MLX 推理 (Z-Image-Turbo 等), 需 uv tool install mflux
  - api:   OpenAI images/generations 兼容接口 (SiliconFlow / 智谱 等)

按项目规则: 两个 provider 之间绝不自动回退, 失败直接报错。
"""

import base64
import logging
import os
import random
import shutil
import subprocess
import threading
import time

import requests

logger = logging.getLogger(__name__)

# 硬约束: MuseTalk 唇形驱动要求正面、单人、嘴部清晰
PROMPT_SUFFIX = (
    "头顶上方留出充足空间, 画面顶部留白约20%, 人物面部位于画面中下区域, "
    "正面面对镜头, 眼神直视镜头, 嘴唇自然闭合, 单人上半身肖像, "
    "面部无遮挡, 演播室纯色渐变背景, 柔和专业灯光, "
    "超写实摄影, 皮肤纹理细腻真实, 电视台主播形象照风格, 高清细节"
)

DEFAULT_PERSONA = "30岁左右专业新闻女主播, 黑色齐肩发, 深色西装, 妆容干练, 气质亲和"

PERSONA_SYSTEM_PROMPT = """你是电视台选角导演。根据口播文案的题材和语气,用一句话设计最合适的主播形象。
只输出一行中文描述,不超过50字,依次包含:性别与大致年龄、发型、服装、气质。
不要输出解释、引号、标点结尾或其他任何内容。示例输出:
35岁左右男性财经主播, 短发, 藏蓝色西装配领带, 沉稳权威"""


class AvatarImageGenerator:
    """主播形象文生图, mflux(本地) / api(云端) 双 provider, 无降级"""

    def __init__(self, config: dict):
        self._config = config
        cfg = config.get("avatar_gen", {})
        self.provider = cfg.get("provider", "mflux")

        # mflux 本地推理
        self.mflux_command = cfg.get("mflux_command", "mflux-generate-z-image-turbo")
        self.mflux_model = cfg.get("mflux_model", "filipstrand/Z-Image-Turbo-mflux-4bit")
        self.mflux_quantize = cfg.get("mflux_quantize", None)
        self.mflux_steps = cfg.get("mflux_steps", 9)

        # 云端 API (OpenAI images/generations 兼容)
        self.api_base = cfg.get("api_base", "https://api.siliconflow.cn/v1")
        self.api_key = (
            cfg.get("api_key", "")
            or os.environ.get("IMAGE_API_KEY", "")
            or os.environ.get("SILICONFLOW_API_KEY", "")
        )
        self.api_model = cfg.get("api_model", "black-forest-labs/FLUX.1-schnell")

        # 通用
        self.width = cfg.get("width", 720)
        self.height = cfg.get("height", 1280)
        self.timeout = cfg.get("timeout", 900)
        self.prompt_llm = cfg.get("prompt_llm", True)

    # ─── 可用性检查 ────────────────────────────────────

    def preflight(self) -> tuple:
        """返回 (是否就绪, 原因)。不就绪时由调用方弹窗提示, 不降级"""
        if self.provider == "mflux":
            if not self._resolve_mflux_bin():
                return False, (f"未找到 mflux 命令 `{self.mflux_command}`。"
                               "请安装: brew install uv && uv tool install mflux")
            return self._mflux_model_ready()
        if self.provider == "api":
            if not self.api_key:
                return False, ("云端图片 API key 未配置: 请在 config.yaml 设置 "
                               "avatar_gen.api_key, 或 export IMAGE_API_KEY=sk-xxx")
            return True, ""
        return False, f"未知 avatar_gen provider: {self.provider}"

    def _mflux_model_ready(self) -> tuple:
        model = self.mflux_model
        expanded = os.path.expanduser(model)
        if os.path.isdir(expanded):
            return True, ""
        if "/" in model and not model.startswith((".", "/", "~")):
            hf_home = os.environ.get("HF_HOME",
                                     os.path.expanduser("~/.cache/huggingface"))
            cache_dir = os.path.join(hf_home, "hub",
                                     "models--" + model.replace("/", "--"))
            if os.path.isdir(cache_dir):
                return True, ""
            return False, (f"本地模型未下载: {model} (~7GB)。请执行: "
                           f".venv/bin/huggingface-cli download {model}")
        return False, f"mflux 模型路径不存在: {model}"

    def check_availability(self) -> bool:
        ok, reason = self.preflight()
        if not ok:
            logger.warning(f"avatar_gen 不可用: {reason}")
        return ok

    def unavailable_reason(self) -> str:
        return self.preflight()[1]

    def _resolve_mflux_bin(self):
        cand = os.path.expanduser(self.mflux_command)
        if os.path.sep in cand:
            return cand if os.path.isfile(cand) else None
        found = shutil.which(cand)
        if found:
            return found
        local_bin = os.path.expanduser(f"~/.local/bin/{cand}")
        if os.path.isfile(local_bin):
            return local_bin
        logger.warning(f"mflux 命令未找到: {cand} (PATH 与 ~/.local/bin 均无)")
        return None

    # ─── 生成入口 ──────────────────────────────────────

    def generate(self, output_path: str, script: str = "", topic: str = "",
                 persona: str = "") -> str:
        logger.info(f"AvatarImageGenerator.generate() 开始: provider={self.provider}")
        """
        生成主播形象图
        persona: 用户手填的形象描述, 填了则不调 LLM
        script/topic: 用于 LLM 推断人设
        返回生成图片路径, 失败抛异常 (不降级)
        """
        persona = (persona or "").strip()
        if not persona:
            persona = self._build_persona(script, topic)
        prompt = f"{persona}, {PROMPT_SUFFIX}"
        logger.info(f"形象 prompt: {prompt[:80]}...")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if self.provider == "mflux":
            return self._gen_mflux(prompt, output_path)
        elif self.provider == "api":
            return self._gen_api(prompt, output_path)
        raise ValueError(f"不支持的 avatar_gen provider: {self.provider}")

    # ─── 人设生成 ──────────────────────────────────────

    def _build_persona(self, script: str, topic: str) -> str:
        material = (script or "").strip() or (topic or "").strip()
        if not material:
            logger.info(f"无文案与描述, 使用默认人设: {DEFAULT_PERSONA}")
            return DEFAULT_PERSONA
        if not self.prompt_llm:
            logger.info("prompt_llm=false, 使用默认人设模板")
            return DEFAULT_PERSONA

        from modules.llm_script import LLMScriptGenerator
        llm = LLMScriptGenerator(self._config)
        llm.system_prompt = PERSONA_SYSTEM_PROMPT
        user_prompt = f"【口播文案】\n{material[:500]}"
        last_error = None
        for attempt in range(3):
            try:
                text = llm._call_provider(user_prompt)
                persona = text.strip().splitlines()[0].strip().strip('"“”')[:60]
                if len(persona) < 4:
                    raise ValueError(f"LLM 人设输出过短: {persona!r}")
                logger.info(f"LLM 人设: {persona}")
                return persona
            except Exception as e:
                last_error = e
                logger.warning(f"LLM 人设生成尝试 {attempt + 1}/3 失败: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(
            f"LLM 人设生成失败 (已重试 3 次): {last_error}。"
            "可在界面手填形象描述, 或配置 avatar_gen.prompt_llm: false 使用固定模板"
        )

    # ─── Provider: mflux 本地 ──────────────────────────

    def _gen_mflux(self, prompt: str, output_path: str) -> str:
        bin_path = self._resolve_mflux_bin()
        if not bin_path:
            raise RuntimeError(self.unavailable_reason())

        seed = random.randint(0, 2**31 - 1)
        cmd = [
            bin_path,
            "--prompt", prompt,
            "--model", self.mflux_model,
            "--width", str(self.width),
            "--height", str(self.height),
            "--steps", str(self.mflux_steps),
            "--seed", str(seed),
            "--output", output_path,
        ]
        if self.mflux_quantize:
            cmd += ["-q", str(self.mflux_quantize)]

        env = os.environ.copy()
        for k in ("VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)

        logger.info(f"mflux 生成中 (model={self.mflux_model}, "
                    f"{self.width}x{self.height}, steps={self.mflux_steps}, seed={seed}, "
                    f"约 1-3 分钟)...")
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
            def _stream():
                for line in iter(process.stdout.readline, ""):
                    line = line.rstrip("\n")
                    if line:
                        logger.info(f"[avatar_mflux] {line}")
            t = threading.Thread(target=_stream, daemon=True)
            t.start()
            logger.info(f"[avatar_mflux] PID={process.pid}, 等待完成 (timeout={self.timeout}s)...")
            process.wait(timeout=self.timeout)
            t.join(timeout=10)
            if process.returncode != 0:
                raise RuntimeError(f"mflux 生成失败 (exit {process.returncode})")
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except Exception:
                pass
            raise RuntimeError(f"mflux 生成超时 (>{self.timeout}s), 可调大 avatar_gen.timeout")
        if not os.path.isfile(output_path):
            raise RuntimeError(f"mflux 执行成功但未产出图片: {output_path}")
        logger.info(f"形象图已生成 (mflux): {output_path}")
        return output_path

    # ─── Provider: 云端 API ────────────────────────────

    def _gen_api(self, prompt: str, output_path: str) -> str:
        if not self.api_key:
            raise RuntimeError(self.unavailable_reason())

        url = f"{self.api_base.rstrip('/')}/images/generations"
        size = f"{self.width}x{self.height}"
        payload = {
            "model": self.api_model,
            "prompt": prompt,
            "n": 1,
            "size": size,        # OpenAI / 智谱 风格
            "image_size": size,  # SiliconFlow 风格, 多余字段服务端会忽略
            "batch_size": 1,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(3):
            try:
                logger.info(f"图片 API 调用中 ({self.api_model} @ {self.api_base})...")
                resp = requests.post(url, json=payload, headers=headers, timeout=360000)
                if 400 <= resp.status_code < 500:
                    raise RuntimeError(
                        f"图片 API 返回 {resp.status_code} (配置或额度问题, 不重试): "
                        f"{resp.text[:300]}")
                resp.raise_for_status()
                return self._save_api_image(resp.json(), output_path)
            except RuntimeError:
                raise
            except Exception as e:
                last_error = e
                logger.warning(f"图片 API 尝试 {attempt + 1}/3 失败: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"图片 API 生成失败 (已重试 3 次): {last_error}")

    def _save_api_image(self, data: dict, output_path: str) -> str:
        item = None
        if isinstance(data.get("data"), list) and data["data"]:
            item = data["data"][0]
        elif isinstance(data.get("images"), list) and data["images"]:
            item = data["images"][0]
        if not item:
            raise RuntimeError(f"图片 API 响应无图片数据: {str(data)[:300]}")

        if item.get("b64_json"):
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            img = requests.get(item["url"], timeout=360000)
            img.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(img.content)
        else:
            raise RuntimeError(f"图片 API 响应格式无法识别: {str(item)[:300]}")

        if not os.path.isfile(output_path) or os.path.getsize(output_path) < 1024:
            raise RuntimeError(f"图片 API 产出文件异常: {output_path}")
        logger.info(f"形象图已生成 (api): {output_path}")
        return output_path
