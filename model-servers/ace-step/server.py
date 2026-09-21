"""ACE-Step wrapper — full songs with sung vocals, or instrumentals.

The 3.5B checkpoint downloads on first request (slow). CPU inference of a
full song takes a long time; the endpoint streams no progress, be patient.
"""

import glob
import os
import tempfile
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

DEVICE = "cpu"
MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 600
DEFAULT_DURATION = 60
TASK_TEXT2SONG = "text2song"

app = FastAPI(title="ACE-Step")
_state = {}
_lock = threading.Lock()


class GenerateRequest(BaseModel):
    task: str = TASK_TEXT2SONG
    lyrics: str = ""
    tags: str
    duration: float = DEFAULT_DURATION
    language: str = "en"


def get_pipeline():
    with _lock:
        if "pipe" not in _state:
            from acestep.pipeline_ace_step import ACEStepPipeline
            _state["pipe"] = ACEStepPipeline(
                dtype="float32",
                torch_compile=False,
                device_id=0,
                cpu_offload=False,
            )
    return _state["pipe"]


@app.get("/health")
def health():
    return {"status": "ok", "loaded": "pipe" in _state}


@app.post("/generate")
def generate(req: GenerateRequest):
    if req.task != TASK_TEXT2SONG:
        raise HTTPException(422, f"Only task '{TASK_TEXT2SONG}' is supported")
    duration = max(MIN_DURATION_SECONDS, min(req.duration, MAX_DURATION_SECONDS))
    pipe = get_pipeline()
    outdir = tempfile.mkdtemp()
    save_path = os.path.join(outdir, "song.wav")
    try:
        pipe(
            audio_duration=duration,
            prompt=req.tags,
            lyrics=req.lyrics or "[instrumental]",
            infer_step=27,
            guidance_scale=15.0,
            scheduler_type="euler",
            cfg_type="apg",
            omega_scale=10.0,
            save_path=save_path,
        )
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")

    # The pipeline writes an input-params JSON next to the audio; pick audio only.
    outputs = glob.glob(os.path.join(outdir, "*.wav")) or glob.glob(
        os.path.join(outdir, "*.mp3")
    )
    if not outputs:
        raise HTTPException(500, "Pipeline produced no output file")
    with open(outputs[0], "rb") as f:
        data = f.read()
    media = "audio/wav" if outputs[0].endswith(".wav") else "audio/mpeg"
    return Response(data, media_type=media)
