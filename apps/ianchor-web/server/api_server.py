import sys, os, uuid, json, queue, threading, logging, io, time
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

# Add iAnchor root to path
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import DigitalHumanPipeline
from modules.llm_script import LLMScriptGenerator
import yaml

app = FastAPI(title="iAnchor API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

jobs: dict[str, dict] = {}

def load_config():
    path = ROOT / "config.yaml"
    if path.is_file():
        with open(path) as f: return yaml.safe_load(f)
    return {"paths": {"output_dir": "./output"}}

class GenerateRequest(BaseModel):
    topic: str = ""
    extra: str = ""
    script_text: str = ""
    use_llm: bool = True
    voice: str = "zh-CN-YunyangNeural"
    viz_mode: str = "card"
    sd_provider: str = "mflux"
    image_path: str = ""
    animation_only: bool = False

@app.post("/api/generate")
def generate(req: GenerateRequest):
    job_id = uuid.uuid4().hex[:12]
    log_queue = queue.Queue()
    jobs[job_id] = {"status": "running", "log_queue": log_queue, "output_path": ""}

    class QueueHandler(logging.Handler):
        def emit(self, record):
            log_queue.put(self.format(record))

    def run():
        config = load_config()
        config.setdefault("paths", {})["output_dir"] = f"./output/api_{job_id}"
        if req.viz_mode:
            config.setdefault("visualization", {})["mode"] = req.viz_mode
        if req.sd_provider:
            config.setdefault("visualization", {})["sd_provider"] = req.sd_provider
        config.setdefault("tts", {})["edge_voice"] = req.voice or "zh-CN-YunyangNeural"

        handler = QueueHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        try:
            pipeline = DigitalHumanPipeline(config)
            script_text = req.script_text or req.topic or req.extra or ""
            script_data = None
            if not req.use_llm and script_text:
                script_data = pipeline._step_llm(script_text, skip=True)

            image = req.image_path
            if not image or not os.path.isfile(image):
                image = ""
                if exists := sorted(Path("output/avatar_gen").glob("*.png")):
                    image = str(exists[-1])

            pipeline.run(
                image_path=image or ".gitkeep",
                stock_text=script_text,
                skip_llm=not req.use_llm,
                script_data=script_data,
                animation_only=req.animation_only,
            )
            jobs[job_id]["output_path"] = str(pipeline.final_path)
            jobs[job_id]["status"] = "done"
        except Exception as e:
            log_queue.put(f"ERROR: {e}")
            jobs[job_id]["status"] = "error"
        finally:
            root_logger.removeHandler(handler)

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}

@app.get("/api/logs/{job_id}")
def logs(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    def stream():
        q = job["log_queue"]
        yield "data: " + json.dumps({"text": f"Job {job_id} started\n"}) + "\n\n"
        while True:
            try:
                msg = q.get(timeout=1)
                yield "data: " + json.dumps({"text": msg + "\n"}) + "\n\n"
            except queue.Empty:
                if job["status"] != "running":
                    yield "data: " + json.dumps({"text": f"=== {job['status']} ===\n"}) + "\n\n"
                    break
                yield "data: " + json.dumps({"text": ""}) + "\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.get("/api/video/{job_id}")
def video(job_id: str):
    job = jobs.get(job_id)
    if not job or not job.get("output_path"):
        raise HTTPException(404)
    path = job["output_path"]
    if not os.path.isfile(path):
        raise HTTPException(404, "Video not found")
    return FileResponse(path, media_type="video/mp4")

@app.post("/api/script")
def generate_script(topic: str = "", extra: str = "", use_llm: bool = True):
    if not topic and not extra:
        raise HTTPException(400, "need topic or extra")
    config = load_config()
    gen = LLMScriptGenerator(config)
    if not use_llm or not gen.check_availability():
        text = (topic + "\n" + extra).strip()
        import re
        parts = re.split(r"(?<=[。！？；\n])", text)
        return {"script": text, "title": "口播视频", "segments": [{"text": p.strip(), "data": {}} for p in parts if p.strip()]}
    result = gen.generate(stock_text=(topic + "\n" + extra).strip())
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
