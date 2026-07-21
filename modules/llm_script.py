"""
LLM 口播稿生成模块
支持 DeepSeek API (首选) 和 Ollama 本地模型 (备选)

输入: 股票相关文本段落
输出: 结构化口播稿 JSON (title, script, segments)

Provider:
  - deepseek:  DeepSeek API (openai 兼容), 速度快质量高
  - ollama:    Ollama 本地模型
"""

import json
import logging
import os
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─── Prompt 模板 ───────────────────────────────────────
SYSTEM_PROMPT = """你是资深财经主播。根据用户输入生成自然流畅的口播稿。

核心规则：
1. 用户输入短 → 围绕主题扩展成完整口播
2. 用户输入长 → 提取核心要点，去掉冗余
3. 每段 20~40 字，口语化，适合 TTS 朗读
4. 每段附带该时刻的关键行情数据（可视化用）
5. 像真人主播说话，不要模板化开头，每段开头自然不同⚠️重要：所有数字保持原始阿拉伯数字格式（如"150.25"、"-3.2%"、"¥150.25"），绝对禁止转换为中文数字（如"一百五十点二五"）。数据格式必须与原格式一致。

"""

USER_PROMPT_TEMPLATE = """{stock_text}

请严格按照上述【口播要求】的指示，参考【参考素材】中的数据，创作一篇口播稿。

核心规则：
- 严格遵循【口播要求】中描述的格式、风格、分段方式
- **只使用【参考素材】中已有数据，绝不编造任何数字、价格、涨跌幅、成交量**
- 仅重新组织语言使其更口语化，素材不够时可用衔接词、过渡句、语气词等扩充
- 生成 8~15 段，全文总字数 600~900 字。每段 40~80 字
- 素材中没有的数字，对应 data 字段写 "--"，不要自己填数字
- 每段开头句式各不相同，像专业主播自然讲述
- 每段附带结构化数据：price(数字，无则"--")、change_pct(数字，无则"--")、volume(字符串，无则"--")、time_label(字符串，无则"")
- ⚠️数字保持阿拉伯数字格式（如"150.25"、"-3.2%"），绝对禁止转换为中文数字（如"一百五十点二五"）

请输出标准 JSON 格式（不要 Markdown 代码块）：
{{
    "title": "口播标题",
    "script": "完整连续口播文本",
    "segments": [
      {{
        "text": "这段文字内容...",
        "data": {{"time_label": "09:30", "price": 150.25, "change_pct": -3.2, "volume": "8500 万股"}}
      }}
    ]
  }}"""


class LLMScriptGenerator:
    """多 Provider LLM 口播稿生成器"""

    def __init__(self, config: dict):
        cfg = config.get("llm", {})
        self.provider = cfg.get("provider", "deepseek")
        self.model = cfg.get("model", "deepseek-v4-pro")
        self.temperature = cfg.get("temperature", 0.7)
        self.max_tokens = cfg.get("max_tokens", 2048)
        self.system_prompt = cfg.get("system_prompt", "") or SYSTEM_PROMPT
        self.timeout = 600   # 本地大模型首次推理可能很慢

        # DeepSeek 配置
        self.deepseek_api_key = cfg.get("deepseek_api_key", "") or os.environ.get(
            "DEEPSEEK_API_KEY", ""
        )
        self.deepseek_api_base = cfg.get("deepseek_api_base", "https://api.deepseek.com")

        # Ollama 配置
        self.ollama_api_base = cfg.get("ollama_api_base", "http://localhost:11434")

    # ─── 可用性检查 ────────────────────────────────────

    def check_availability(self) -> bool:
        """检查 LLM provider 是否可用"""
        if self.provider == "deepseek":
            return self._check_deepseek()
        elif self.provider == "ollama":
            return self._check_ollama()
        else:
            logger.warning(f"未知 provider: {self.provider}")
            return False

    def _check_deepseek(self) -> bool:
        """检查 DeepSeek API key 是否配置"""
        if not self.deepseek_api_key:
            logger.warning("DeepSeek API key 未配置 (设置 DEEPSEEK_API_KEY 环境变量)")
            return False
        # 轻量验证：列出模型
        try:
            resp = requests.get(
                f"{self.deepseek_api_base}/v1/models",
                headers={"Authorization": f"Bearer {self.deepseek_api_key}"},
                timeout=360000,
            )
            if resp.status_code == 200:
                models = [m.get("id", "") for m in resp.json().get("data", [])]
                logger.info(f"DeepSeek API 可用，模型: {[m for m in models if 'deepseek' in m.lower()]}")
                return True
            logger.warning(f"DeepSeek API 响应异常: {resp.status_code}")
            return False
        except requests.ConnectionError:
            logger.error(f"无法连接 DeepSeek API ({self.deepseek_api_base})")
            return False
        except Exception as e:
            logger.warning(f"DeepSeek API 检查异常: {e}")
            return False

    def _check_ollama(self) -> bool:
        """检查 Ollama 服务是否可用"""
        try:
            resp = requests.get(f"{self.ollama_api_base}/api/tags", timeout=360000)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                logger.info(f"Ollama 可用，已安装模型: {models}")
                model_short = self.model.split(":")[0]
                for m in models:
                    if m.startswith(model_short):
                        return True
                logger.warning(f"模型 {self.model} 未找到，将尝试自动拉取")
                return True
            return False
        except requests.ConnectionError:
            logger.error(f"无法连接 Ollama ({self.ollama_api_base})")
            return False
        except Exception as e:
            logger.warning(f"检查 Ollama 状态异常: {e}")
            return False

    # ─── 生成入口 ──────────────────────────────────────

    def generate(self, stock_text: str = "", topic: str = "",
                 content: str = "", retry: int = 2) -> dict:
        """
        根据主题描述和参考内容生成口播稿
        topic: 用户的要求/风格描述
        content: 参考信息/素材
        stock_text: 兼容旧版 (topic + content 合一)
        """
        if topic or content:
            user_prompt = USER_PROMPT_TEMPLATE.format(
                stock_text=f"【口播要求】\n{topic}\n\n【参考素材】\n{content}")
        else:
            # CLI 兼容：自动包装
            user_prompt = USER_PROMPT_TEMPLATE.format(
                stock_text=f"【口播要求】\n根据以下信息创作一篇口播稿，按内容自然分段，每段带数据。\n\n【参考素材】\n{stock_text}")

        last_error = None
        for attempt in range(retry + 1):
            try:
                result = self._call_provider(user_prompt)
                parsed = self._parse_response(result)
                self._validate_script(parsed)
                logger.info(f"口播稿生成成功 ({self.provider}): {parsed.get('title', '')}")
                return parsed
            except Exception as e:
                last_error = e
                logger.warning(f"LLM 生成尝试 {attempt + 1}/{retry + 1} 失败 ({self.provider}): {e}")
                if attempt < retry:
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"LLM 口播稿生成失败 (已重试 {retry} 次): {last_error}")

    def _call_provider(self, user_prompt: str) -> str:
        """根据 provider 调用对应的 API"""
        if self.provider == "deepseek":
            return self._call_deepseek(user_prompt)
        elif self.provider == "ollama":
            return self._call_ollama(user_prompt)
        else:
            raise ValueError(f"不支持的 provider: {self.provider}")

    # ─── DeepSeek API 调用 ─────────────────────────────

    def _call_deepseek(self, user_prompt: str) -> str:
        """调用 DeepSeek API (OpenAI 兼容 /v1/chat/completions)"""
        if not self.deepseek_api_key:
            raise ValueError("DeepSeek API key 未设置")

        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        logger.info(f"DeepSeek API 调用中 ({self.model}, 约30-60s)...")
        # 心跳线程：每5秒打一次，防止误以为卡住
        import threading
        heartbeat = [True]
        def _beat():
            for i in range(1, 24):  # 最多等120s
                time.sleep(5)
                if not heartbeat[0]:
                    return
                logger.info(f"DeepSeek 等待中... ({i*5}s)")
        t = threading.Thread(target=_beat, daemon=True)
        t.start()
        try:
            resp = requests.post(
                f"{self.deepseek_api_base}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        finally:
            heartbeat[0] = False
        resp.raise_for_status()
        data = resp.json()
        logger.info("DeepSeek API 响应成功")

        # OpenAI 兼容格式: choices[0].message.content
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("DeepSeek API 返回空 choices")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError("DeepSeek API 返回空内容")

        # 记录 token 使用
        usage = data.get("usage", {})
        if usage:
            logger.debug(
                f"DeepSeek tokens: prompt={usage.get('prompt_tokens')}, "
                f"completion={usage.get('completion_tokens')}"
            )

        return content

    # ─── Ollama API 调用 ───────────────────────────────

    def _call_ollama(self, user_prompt: str) -> str:
        """调用 Ollama chat API"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        resp = requests.post(
            f"{self.ollama_api_base}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise ValueError("Ollama 返回空内容")
        return content

    # ─── 响应解析 ──────────────────────────────────────

    @staticmethod
    def _parse_response(content: str) -> dict:
        """从 LLM 响应中提取 JSON, 支持截断修复"""
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if code_match:
            try:
                return json.loads(code_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... } 最外层 JSON
        brace_match = re.search(r"\{[\s\S]*\}", content)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # 截断修复: 尝试补全未闭合的括号
        content = content.strip()
        last_good = content.rfind('"}')
        if last_good > 0:
            # Close segments array and object
            fixed = content[:last_good + 2] + '\n    ]\n  }'
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
            # Try without closing
            fixed2 = content[:last_good + 2] + ']}'
            try:
                return json.loads(fixed2)
            except json.JSONDecodeError:
                pass

        raise ValueError(f"无法从 LLM 响应中解析 JSON: {content[:200]}...")

    @staticmethod
    def _validate_script(script: dict):
        """验证口播稿结构"""
        required = ["title", "script", "segments"]
        for field in required:
            if field not in script:
                raise ValueError(f"口播稿缺少必要字段: {field}")

        if not isinstance(script["segments"], list) or len(script["segments"]) < 5:
            raise ValueError("segments 必须是包含至少 5 个元素的数组")

        for i, seg in enumerate(script["segments"]):
            if "text" not in seg:
                raise ValueError(f"segment[{i}] 缺少 text 字段")
            if "data" not in seg:
                seg["data"] = {}
