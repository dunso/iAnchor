#!/usr/bin/env python3
"""iAnchor Web UI - Topic+Info -> LLM Script -> Preview Voice -> Generate Video"""
import sys
import os
import threading
import logging
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging.handlers

import gradio as gr
import numpy as np
import yaml
from PIL import Image

from pipeline import DigitalHumanPipeline
from modules.llm_script import LLMScriptGenerator
from modules.tts_generator import TTSGenerator
from modules.avatar_image_gen import AvatarImageGenerator

VOICES = [
    "zh-CN-YunyangNeural (M News)",
    "zh-CN-YunxiNeural (M Sunny)",
    "zh-CN-XiaoxiaoNeural (F News)",
    "zh-CN-YunjianNeural (M Sports)",
    "zh-CN-YunxiaNeural (M Cartoon)",
    "zh-CN-XiaoyiNeural (F Cartoon)",
    "v2/zh_speaker_0 (Bark M0)",
    "v2/zh_speaker_1 (Bark M1)",
    "v2/zh_speaker_2 (Bark M2)",
    "v2/zh_speaker_3 (Bark F3)",
    "v2/zh_speaker_4 (Bark F4)",
    "v2/zh_speaker_5 (Bark M5)",
    "v2/zh_speaker_6 (Bark F6)",
    "v2/zh_speaker_7 (Bark F7)",
    "v2/zh_speaker_8 (Bark M8)",
    "v2/zh_speaker_9 (Bark F9)",
]

_logs: list[str] = []
_log_lock = threading.Lock()
_script_generated = False  # 标记文案是否已由LLM生成过
_script_data = None  # 保存 LLM 返回的完整数据 (title + script + segments)
logger = logging.getLogger("iAnchor")


class _UIHandler(logging.Handler):
    def emit(self, record):
        with _log_lock:
            _logs.append(self.format(record))


def _setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    # UI 日志
    h = _UIHandler()
    h.setFormatter(fmt)
    root.addHandler(h)
    # 终端日志
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    # ERROR 日志写文件 (按天切割，保留 7 天)
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        when="midnight", interval=1, backupCount=7, encoding="utf-8")
    fh.setLevel(logging.ERROR)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    for lib in ("matplotlib", "matplotlib.font_manager", "PIL", "moviepy",
                "urllib3", "httpcore", "httpx", "bark.generation",
                "huggingface_hub", "torch", "huggingface_hub.utils"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def _pop_logs() -> str:
    with _log_lock:
        if not _logs:
            return ""
        t = "\n".join(_logs)
        _logs.clear()
        return t


LLM_CLOUD = "云端 API"
LLM_LOCAL = "本地 Ollama"
AV_LOCAL = "本地 mflux"
AV_CLOUD = "云端 API"


def _apply_llm_choice(config: dict, choice: str) -> str:
    """UI 选择 → llm.provider, 本地时可用 llm.ollama_model 覆盖模型名"""
    provider = "ollama" if str(choice).startswith("本地") else "deepseek"
    llm_cfg = config.setdefault("llm", {})
    llm_cfg["provider"] = provider
    if provider == "ollama" and llm_cfg.get("ollama_model"):
        llm_cfg["model"] = llm_cfg["ollama_model"]
    return provider


def _llm_unavailable_msg(config: dict) -> str:
    llm_cfg = config.get("llm", {})
    if llm_cfg.get("provider") == "ollama":
        base = llm_cfg.get("ollama_api_base", "http://localhost:11434")
        model = llm_cfg.get("model", "qwen2.5:7b")
        return (f"本地 Ollama 不可用 ({base})。请先启动: ollama serve, "
                f"并拉取模型: ollama pull {model}")
    return ("云端 LLM 未配置或不可用。请在 config.yaml 设置 llm.deepseek_api_key, "
            "或 export DEEPSEEK_API_KEY=sk-xxx")


def generate_script(topic: str, extra_info: str, use_llm: bool, current_script: str = "", llm_provider: str = LLM_CLOUD) -> str:
    _logs.clear()
    # 主题和附加都空，但文案已有 → 不重新生成
    if not topic.strip() and not extra_info.strip() and current_script.strip():
        return current_script.strip()
    # 清旧数据，以免视频生成时用到旧 segments
    global _script_generated, _script_data
    _script_generated = False
    _script_data = None
    if not use_llm:
        if not extra_info.strip():
            raise gr.Error("请填写附加信息")
        return extra_info.strip()
    if not topic.strip() and not extra_info.strip():
        raise gr.Error("请至少填写主题或附加信息")
    config = _load_config()
    _apply_llm_choice(config, llm_provider)
    try:
        llm = LLMScriptGenerator(config)
        if not llm.check_availability():
            raise gr.Error(_llm_unavailable_msg(config))
        result = llm.generate(topic=topic.strip(), content=extra_info.strip())
        _script_generated = True
        _script_data = result  # 保存完整数据给视频生成用
        return result.get("script", result.get("title", "文案生成失败"))
    except gr.Error:
        raise
    except Exception as e:
        raise gr.Error(f"文案生成失败: {e}")


def _resolve_tts(voice_display: str):
    """Resolve TTS provider from voice selection. No fallback."""
    voice_id = voice_display.split(" ")[0]
    config = _load_config()
    if voice_id.startswith("v2/"):
        config.setdefault("tts", {})["provider"] = "bark"
        config.setdefault("tts", {})["bark_voice"] = voice_id
    else:
        config.setdefault("tts", {})["provider"] = "edge_tts"
        config.setdefault("tts", {})["edge_voice"] = voice_id
    return TTSGenerator(config), config


def preview_audio(script_text: str, voice_display: str) -> str:
    _logs.clear()
    if not script_text.strip():
        raise gr.Error("请先生成或输入口播文案")
    tts, _ = _resolve_tts(voice_display)
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        tts.generate(script_text[:200], tmp.name)
        from scipy.io.wavfile import read as wav_read
        sr, data = wav_read(tmp.name)
        return (sr, data.astype(float) / 32768.0)
    except Exception as e:
        raise gr.Error(f"Preview failed: {e}")


def generate_video(script_text: str, voice_display: str, image, use_llm: bool, viz_choice: str, topic: str, extra: str, llm_provider: str = LLM_CLOUD, progress=gr.Progress()):
    _logs.clear()
    full_log: list[str] = []
    if not script_text.strip():
        raise gr.Error("请先生成或输入口播文案")
    if image is None:
        raise gr.Error("请上传或 AI 生成口播人像")
    _, config = _resolve_tts(voice_display)
    _apply_llm_choice(config, llm_provider)
    # 将调用 LLM 时, 先检查可用性, 未配置直接弹窗
    _will_reuse = (_script_generated and _script_data
                   and _script_data.get("segments")
                   and _script_data.get("script") == script_text)
    if use_llm and (topic.strip() or extra.strip()) and not _will_reuse:
        if not LLMScriptGenerator(config).check_availability():
            raise gr.Error(_llm_unavailable_msg(config))
    # 设置动画模式
    if viz_choice.startswith("sd (flux"):
        viz_mode_val = "sd"
        config.setdefault("visualization", {})["sd_provider"] = "flux"
    elif viz_choice.startswith("sd"):
        viz_mode_val = "sd"
        config.setdefault("visualization", {})["sd_provider"] = "mflux"
    elif viz_choice.startswith("manim_comic"):
        viz_mode_val = "manim_comic"
    elif viz_choice.startswith("manim"):
        viz_mode_val = "manim"
    elif viz_choice.startswith("bailian"):
        viz_mode_val = "bailian"
    elif viz_choice.startswith("wan_api"):
        viz_mode_val = "wan_api"
    elif viz_choice.startswith("wan"):
        viz_mode_val = "wan"
    elif viz_choice.startswith("remotion"):
        viz_mode_val = "remotion"
    else:
        viz_mode_val = "card"
    config.setdefault("visualization", {})["mode"] = viz_mode_val
    tmp_img = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_img.close()
    img_path = image if isinstance(image, str) else tmp_img.name
    if not isinstance(image, str):
        Image.fromarray(image).save(tmp_img.name)
    progress(0, desc="初始化...")
    yield "\n".join(full_log), None, gr.Gallery(visible=False)
    result = {"path": None, "error": None, "session_dir": None}
    _latest_wan = None  # wan 模式最新完成的片段路径
    def _run():
        try:
            pipeline = DigitalHumanPipeline(config)
            result["session_dir"] = str(pipeline.session_dir)  # 提前暴露路径
            # 文案已由LLM生成过 → 直接用保存的 segments，跳过 LLM
            global _script_generated, _script_data
            skip_llm = (not topic.strip() and not extra.strip()) or not use_llm
            # 文案未改动 → 复用 LLM 数据；改过了 → 清掉旧数据
            if (_script_generated and _script_data
                    and _script_data.get("segments")
                    and _script_data.get("script") == script_text):
                skip_llm = True
                script_data = _script_data
            else:
                script_data = None
                _script_generated = False
                _script_data = None
            result["path"] = pipeline.run(image_path=img_path, stock_text=script_text, skip_llm=skip_llm, script_data=script_data)
            result["session_dir"] = str(pipeline.session_dir)
        except Exception as e:
            logging.getLogger("iAnchor").error(f"生成失败: {e}")
            result["error"] = str(e)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    while t.is_alive():
        time.sleep(0.5)
        new = _pop_logs()
        if new:
            full_log.append(new)
        # wan 模式: 实时展示最新完成的片段
        video_update = gr.update()
        gallery_update = gr.Gallery(visible=False)
        if viz_mode_val in ("wan", "wan_api", "bailian") and result["session_dir"]:
            clip_dir = os.path.join(result["session_dir"], "wan_clips")
            if os.path.isdir(clip_dir):
                import glob as _g2
                clips = sorted(_g2.glob(os.path.join(clip_dir, "wan_*.mp4")))
                if clips:
                    if clips[-1] != _latest_wan:
                        _latest_wan = clips[-1]
                        video_update = gr.Video(value=_latest_wan, label="🎬 最新片段")
                    gallery_update = gr.Gallery(
                        value=[(f, os.path.basename(f)) for f in clips],
                        visible=True
                    )
        yield "\n".join(full_log), video_update, gallery_update
    t.join(timeout=2)
    new = _pop_logs()
    if new:
        full_log.append(new)
    progress(1.0, desc="完成")
    try:
        if tmp_img.name != image:
            os.unlink(tmp_img.name)
    except Exception:
        logger.debug("临时图片清理失败")
    if result["error"]:
        full_log.append(f"❌ {result['error']}")
        yield "\n".join(full_log), None, gr.Gallery(visible=False)
        raise gr.Error(f"生成失败: {result['error']}")
    elif result["path"]:
        yield "\n".join(full_log), gr.Video(value=result["path"], label="生成结果"), gr.Gallery(visible=False)
    else:
        full_log.append("⚠️ 未生成视频，请查看日志")
        yield "\n".join(full_log), None, gr.Gallery(visible=False)
        raise gr.Error("未生成视频, 请查看运行日志")


def generate_avatar_image(script_text: str, topic: str, desc: str,
                          avatar_provider: str = AV_LOCAL, llm_provider: str = LLM_CLOUD):
    """AI 生成主播形象图 → 填入人像组件"""
    _logs.clear()
    if not desc.strip() and not script_text.strip() and not topic.strip():
        raise gr.Error("请先生成文案, 或填写形象描述")
    config = _load_config()
    config.setdefault("avatar_gen", {})["provider"] = (
        "api" if str(avatar_provider).startswith("云端") else "mflux")
    _apply_llm_choice(config, llm_provider)
    gen = AvatarImageGenerator(config)
    ok, reason = gen.preflight()
    if not ok:
        raise gr.Error(reason)
    # 人设需要 LLM 时, 先检查文案引擎可用
    if not desc.strip() and gen.prompt_llm:
        llm = LLMScriptGenerator(config)
        if not llm.check_availability():
            raise gr.Error(f"形象人设需要 LLM: {_llm_unavailable_msg(config)}。"
                           "或手动填写形象描述跳过 LLM")
    out_dir = os.path.join(
        config.get("paths", {}).get("output_dir", "./output"), "avatar_gen")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"avatar_{time.strftime('%Y%m%d_%H%M%S')}.png")
    gr.Info(f"形象生成中 ({gen.provider}), 本地模式约需 1-3 分钟...")
    try:
        path = gen.generate(out_path, script=script_text, topic=topic, persona=desc)
    except Exception as e:
        logger.error(f"形象生成失败: {e}")
        raise gr.Error(f"形象生成失败: {e}")
    return np.array(Image.open(path).convert("RGB"))


def _load_config() -> dict:
    path = "config.yaml"
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {"paths": {"output_dir": "./output"}}


def create_ui():
    css = """
    #img-upload .wrap { white-space: nowrap !important; flex-direction: row !important; flex-wrap: nowrap !important; gap: 4px !important; font-size: 12px !important; }
    #img-upload .wrap .icon-wrap { width: 18px !important; height: 18px !important; flex: 0 0 auto !important; }
    #audio-preview { min-height: 200px; }
    .output-col { border-left: 1px solid #e8e8e8; padding-left: 20px; display: flex !important; flex-direction: column !important; }
    .output-col > *, .output-col .form { flex: 1 1 auto !important; }
    .output-col .block { height: 100% !important; display: flex !important; flex-direction: column !important; }
    .output-col .block label { display: flex !important; flex-direction: column !important; flex: 1 1 auto !important; height: 100% !important; }
    .output-col textarea { flex: 1 1 auto !important; height: 810px !important; }
    #gen-btn { margin-top: 24px; }
    #video-preview { margin-top: 16px !important; }
    #gen-btn button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; border: none !important; border-radius: 8px !important; }
    #script-btn { flex: 0 0 auto !important; width: auto !important; min-width: unset !important; white-space: nowrap !important; margin-left: auto !important; }
    button.grad-btn, .grad-btn button { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; border: none !important; border-radius: 8px !important; color: #fff !important; white-space: nowrap !important; }
    .soft-radio .wrap { gap: 6px !important; flex-wrap: nowrap !important; }
    .llm-card .soft-radio label { width: 9.5em !important; }
    .gradio-container textarea::placeholder, .gradio-container input::placeholder { font-size: 12px !important; }
    .avatar-gen-col { gap: 6px !important; }
    .llm-card label { white-space: nowrap !important; }
    .nice-drop .wrap-inner, .nice-drop .secondary-wrap { border: none !important; box-shadow: none !important; }
    .nice-drop .wrap { border: 1px solid #e8e8e8 !important; border-radius: 8px !important; box-shadow: none !important; background: #f7f8fa !important; }
    .nice-drop .wrap:focus-within { border-color: #667eea !important; background: #fff !important; box-shadow: 0 0 0 3px rgba(102,126,234,.12) !important; }
    .nice-drop input { font-size: 13px !important; }
    ul.options { border: 1px solid #e8e8e8 !important; border-radius: 8px !important; box-shadow: 0 8px 24px rgba(0,0,0,.08) !important; padding: 4px !important; max-height: 260px !important; overflow-y: auto !important; overscroll-behavior: contain !important; }
    ul.options li.item { border-radius: 6px !important; padding: 6px 10px !important; font-size: 13px !important; }
    ul.options li.item:hover, ul.options li.item.selected { background: #eef1ff !important; color: #4c5fd5 !important; }
    .llm-card .soft-radio { padding: 0 !important; }
    .llm-card .soft-radio .wrap { justify-content: flex-end !important; }
    .llm-card { background: #fff !important; border: none !important; padding: 10px 12px !important; }
    .llm-card .form, .llm-card .row, .llm-card .block, .llm-card div.svelte-1p9262q { background: transparent !important; border: none !important; box-shadow: none !important; }
    .side-panel { background: #fff; border: none; }
    .side-panel > div { gap: 0 !important; }
    .soft-radio label {
        background: #f7f8fa !important;
        border: 1px solid #e8e8e8 !important;
        color: #666 !important;
        border-radius: 13px !important;
        box-shadow: none !important;
        height: 26px !important;
        width: 8em !important;
        padding: 0 !important;
        white-space: nowrap !important;
        justify-content: center !important;
        align-items: center !important;
        font-size: 13px !important;
    }
    .soft-radio label:hover { background: #eef0f4 !important; }
    .soft-radio label.selected {
        background: #eef1ff !important;
        border-color: #667eea !important;
        color: #4c5fd5 !important;
    }
    .soft-radio input[type='radio']:checked {
        background-color: #667eea !important;
        border-color: #667eea !important;
    }
"""

    with gr.Blocks(title="iAnchor Video Generation", theme=gr.themes.Soft(), css=css) as demo:
        gr.Markdown("# 🎬 iAnchor — AI 口播视频生成")

        cfg0 = _load_config()
        llm_default = LLM_LOCAL if cfg0.get("llm", {}).get("provider") == "ollama" else LLM_CLOUD
        av_default = AV_CLOUD if cfg0.get("avatar_gen", {}).get("provider") == "api" else AV_LOCAL

        with gr.Row():
            # 左侧: 输入区 (再分两栏)
            with gr.Column(scale=3):
                with gr.Row():
                    with gr.Column(scale=2):
                        topic_input = gr.Textbox(label="📌 主题描述", placeholder="如：今日股市行情解读", lines=1, max_lines=1)
                        extra_input = gr.Textbox(label="📋 附加信息", placeholder="如：沪指收涨1.5%报3350点", lines=3, max_lines=3)
                        with gr.Group(elem_classes="llm-card"):
                            with gr.Row():
                                llm_toggle = gr.Checkbox(label="🤖 调用 AI 生成文案", value=True, scale=1, min_width=185)
                                llm_provider = gr.Radio(show_label=False, choices=[LLM_CLOUD, LLM_LOCAL], value=llm_default, scale=2, elem_classes="soft-radio")
                            with gr.Row():
                                script_btn = gr.Button("✍️ 生成文案", variant="secondary", elem_id="script-btn", elem_classes="grad-btn")
                        script_output = gr.Textbox(label="📄 口播文案", placeholder="点击上方按钮生成，或直接粘贴...", lines=6, max_lines=6)
                        with gr.Row():
                            avatar_source = gr.Radio(label="🧑 主播形象", choices=["上传图片", "AI 生成"], value="上传图片", scale=1, elem_classes="soft-radio")
                            avatar_provider = gr.Radio(label="⚙️ 生成方式", choices=[AV_LOCAL, AV_CLOUD], value=av_default, visible=False, scale=1, elem_classes="soft-radio")
                        with gr.Row(equal_height=True):
                            image_input = gr.Image(label="🖼 口播人像", type="numpy", height=180, elem_id="img-upload", scale=1, min_width=160)
                            with gr.Column(scale=1, min_width=160, visible=False, elem_classes="avatar-gen-col") as avatar_gen_col:
                                avatar_desc = gr.Textbox(label="🎭 形象描述", placeholder="留空由 AI 根据文案设计，如：年轻男性财经主播，深色西装", lines=3, max_lines=3)
                                avatar_gen_btn = gr.Button("🎨 生成形象", variant="secondary", elem_classes="grad-btn")

                    with gr.Column(scale=1):
                        with gr.Group(elem_classes="side-panel"):
                            voice_select = gr.Dropdown(label="🎤 音色选择", choices=VOICES, value="zh-CN-YunyangNeural (M News)", filterable=True, elem_classes="nice-drop")
                        preview_btn = gr.Button("🔊 试听", variant="secondary")
                        audio_preview = gr.Audio(label="🔊 试听音频", scale=1, elem_id="audio-preview")
                        viz_mode = gr.Dropdown(label="🎨 动画模式", choices=["card (PPT卡片)", "sd (mflux文生图)", "sd (flux文生图)", "manim (数字动画)", "manim_comic (漫画分镜)", "wan (本地AI视频)", "wan_api (Replicate)", "bailian (阿里百炼)", "remotion (React动画)"], value="card (PPT卡片)", filterable=True, elem_classes="nice-drop")
                        video_btn = gr.Button("🚀 一键生成视频", variant="primary", size="lg", elem_id="gen-btn", elem_classes="grad-btn")
                        video_output = gr.Video(label="🎬 视频预览", height=280, elem_id="video-preview")
                        wan_gallery = gr.Gallery(label="📺 Wan 片段", columns=4, rows=1, height=120, allow_preview=True, object_fit="contain", visible=False)

            with gr.Column(scale=1, elem_classes="output-col"):
                log_output = gr.Textbox(label="📋 运行日志", lines=30, max_lines=30, autoscroll=True)

        def _toggle_avatar_source(choice):
            auto = choice == "AI 生成"
            return (gr.update(visible=auto),
                    gr.update(visible=auto),
                    gr.update(interactive=not auto,
                              label="🖼 形象预览" if auto else "🖼 口播人像"))

        script_btn.click(fn=generate_script, inputs=[topic_input, extra_input, llm_toggle, script_output, llm_provider], outputs=[script_output])
        avatar_source.change(fn=_toggle_avatar_source,
                             inputs=[avatar_source], outputs=[avatar_provider, avatar_gen_col, image_input])
        avatar_gen_btn.click(fn=generate_avatar_image, inputs=[script_output, topic_input, avatar_desc, avatar_provider, llm_provider], outputs=[image_input])
        preview_btn.click(fn=preview_audio, inputs=[script_output, voice_select], outputs=[audio_preview])
        video_btn.click(fn=generate_video, inputs=[script_output, voice_select, image_input, llm_toggle, viz_mode, topic_input, extra_input, llm_provider], outputs=[log_output, video_output, wan_gallery])

    return demo


if __name__ == "__main__":
    _setup_logging()
    port = int(os.environ.get("IANCHOR_PORT", "7860"))
    demo = create_ui()
    print(f"iAnchor WebUI: http://127.0.0.1:{port}")
    demo.launch(server_name="0.0.0.0", server_port=port, share=False)
