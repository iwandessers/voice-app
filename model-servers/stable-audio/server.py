"""Stable Audio Open Small wrapper — SFX or music from a text prompt.

MODE env selects the flavour label only; both use the same checkpoint.
The Hugging Face repo is gated: set HF_TOKEN and accept the licence at
https://huggingface.co/stabilityai/stable-audio-open-small first.
Model loads lazily on first request.
"""

import io
import os
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

MODEL_ID = "stabilityai/stable-audio-open-small"
DEVICE = "cpu"
MAX_DURATION_SECONDS = 120.0
DEFAULT_DURATION = 10.0
DEFAULT_STEPS = 100

app = FastAPI(title=f"Stable Audio ({os.environ.get('MODE', 'sfx')})")
_state = {}
_lock = threading.Lock()


class GenerateRequest(BaseModel):
    prompt: str
    duration: float = DEFAULT_DURATION
    steps: int = DEFAULT_STEPS


def get_model():
    with _lock:
        if "model" not in _state:
            if not os.environ.get("HF_TOKEN"):
                raise HTTPException(
                    500,
                    f"{MODEL_ID} is a gated Hugging Face repo. Set HF_TOKEN in the "
                    "environment and accept the licence on huggingface.co first.",
                )
            from stable_audio_tools import get_pretrained_model
            model, config = get_pretrained_model(MODEL_ID)
            _state["model"] = model.to(DEVICE)
            _state["config"] = config
    return _state["model"], _state["config"]


@app.get("/health")
def health():
    return {"status": "ok", "loaded": "model" in _state}


@app.post("/generate")
def generate(req: GenerateRequest):
    import torch
    import torchaudio
    from stable_audio_tools.inference.generation import generate_diffusion_cond

    model, config = get_model()
    duration = min(req.duration, MAX_DURATION_SECONDS)
    sample_rate = config["sample_rate"]
    sample_size = int(duration * sample_rate)

    conditioning = [{
        "prompt": req.prompt,
        "seconds_start": 0,
        "seconds_total": duration,
    }]
    try:
        with torch.no_grad():
            audio = generate_diffusion_cond(
                model,
                steps=req.steps,
                conditioning=conditioning,
                sample_size=sample_size,
                device=DEVICE,
            )
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")

    audio = audio.squeeze(0).to(torch.float32)
    audio = audio / max(audio.abs().max().item(), 1e-8)
    buf = io.BytesIO()
    torchaudio.save(buf, audio.cpu(), sample_rate, format="wav")
    return Response(buf.getvalue(), media_type="audio/wav")
