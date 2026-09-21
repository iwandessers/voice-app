"""Chatterbox wrapper — voice cloning from a short sample with emotion control.

Model loads lazily on first request (several GB download from Hugging Face).
"""

import io
import tempfile
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

DEVICE = "cpu"
DEFAULT_EXAGGERATION = 0.5
DEFAULT_CFG_WEIGHT = 0.5

app = FastAPI(title="Chatterbox")
_model = None
_lock = threading.Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            from chatterbox.tts import ChatterboxTTS
            _model = ChatterboxTTS.from_pretrained(device=DEVICE)
    return _model


@app.get("/health")
def health():
    return {"status": "ok", "loaded": _model is not None}


# Sync endpoint on purpose: FastAPI runs it in a worker thread, so the
# event loop stays responsive while the model downloads or generates.
@app.post("/synthesize")
def synthesize(
    text: str = Form(...),
    audio_prompt: UploadFile | None = File(None),
    exaggeration: float = Form(DEFAULT_EXAGGERATION),
    cfg_weight: float = Form(DEFAULT_CFG_WEIGHT),
):
    import os

    import torchaudio

    model = get_model()
    kwargs = {"exaggeration": exaggeration, "cfg_weight": cfg_weight}
    prompt_tmp = None
    try:
        if audio_prompt is not None and audio_prompt.filename:
            suffix = os.path.splitext(audio_prompt.filename)[1] or ".wav"
            prompt_tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            prompt_tmp.write(audio_prompt.file.read())
            prompt_tmp.close()
            kwargs["audio_prompt_path"] = prompt_tmp.name
        wav = model.generate(text, **kwargs)
    except Exception as exc:
        raise HTTPException(500, f"Generation failed: {exc}")

    buf = io.BytesIO()
    torchaudio.save(buf, wav, model.sr, format="wav")
    return Response(buf.getvalue(), media_type="audio/wav")
