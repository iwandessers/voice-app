"""Kitten TTS wrapper — English narration with preset voices.

The model is loaded lazily on the first request so the container
starts instantly regardless of download state.
"""

import io
import threading

import soundfile as sf
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

SAMPLE_RATE = 24000
DEFAULT_VOICE = "expr-voice-2-f"

app = FastAPI(title="Kitten TTS")
_model = None
_lock = threading.Lock()


class TtsRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE


def get_model():
    global _model
    with _lock:
        if _model is None:
            from kittentts import KittenTTS
            _model = KittenTTS()  # downloads the nano checkpoint from Hugging Face
    return _model


@app.get("/health")
def health():
    return {"status": "ok", "loaded": _model is not None}


@app.get("/voices")
def voices():
    return get_model().available_voices


@app.post("/tts")
def tts(req: TtsRequest):
    model = get_model()
    voice = req.voice if req.voice != "default" else DEFAULT_VOICE
    try:
        audio = model.generate(req.text, voice=voice)
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")
    buf = io.BytesIO()
    sf.write(buf, audio, SAMPLE_RATE, format="WAV")
    return Response(buf.getvalue(), media_type="audio/wav")
