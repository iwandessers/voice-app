"""MeloTTS wrapper — multilingual narration with preset speakers.

One TTS instance per language, created lazily on first use.
"""

import io
import tempfile
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

DEVICE = "cpu"
DEFAULT_LANGUAGE = "EN"
DEFAULT_SPEED = 1.0

app = FastAPI(title="MeloTTS")
_models = {}
_lock = threading.Lock()


class SynthesizeRequest(BaseModel):
    text: str
    language: str = DEFAULT_LANGUAGE
    speaker_id: str = ""
    speed: float = DEFAULT_SPEED


def get_model(language: str):
    with _lock:
        if language not in _models:
            from melo.api import TTS
            _models[language] = TTS(language=language, device=DEVICE)
    return _models[language]


@app.get("/health")
def health():
    return {"status": "ok", "loaded_languages": list(_models)}


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    try:
        model = get_model(req.language.upper())
    except Exception as exc:
        raise HTTPException(500, f"Could not load language '{req.language}': {exc}")
    speakers = model.hps.data.spk2id
    speaker = req.speaker_id if req.speaker_id in speakers else list(speakers.keys())[0]
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            model.tts_to_file(req.text, speakers[speaker], tmp.name, speed=req.speed)
            tmp.seek(0)
            wav = tmp.read()
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")
    return Response(wav, media_type="audio/wav")
