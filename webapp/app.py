"""Control panel for the voice-model stack.

Start/stop model containers over the Docker socket, proxy generation
requests to the model services and stream audio back to the browser.
"""

import asyncio
import io
import json
import struct

import docker
import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from models_config import (
    KIND_JSON,
    KIND_MULTIPART,
    KIND_WYOMING,
    MODELS,
)

COMPOSE_SERVICE_LABEL = "com.docker.compose.service"
GENERATION_TIMEOUT_SECONDS = 1800  # CPU inference is slow; ACE-Step songs take a while
CONNECT_RETRY_SECONDS = 30  # a freshly started container needs a moment to listen
CONNECT_RETRY_INTERVAL_SECONDS = 2
WYOMING_SAMPLE_RATE = 22050
WYOMING_SAMPLE_WIDTH = 2
WYOMING_CHANNELS = 1

STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"
STATUS_NOT_CREATED = "not_created"

VOICES_FETCH_TIMEOUT_SECONDS = 3

app = FastAPI(title="Voice App Control Panel")
docker_client = docker.from_env()
_voices_cache: dict[str, list[str]] = {}


def fetch_live_voices(service: str, cfg: dict) -> list[str] | None:
    """Fetch the current voice list from a running service, with caching."""
    if service in _voices_cache:
        return _voices_cache[service]
    url = f"http://{cfg['host']}:{cfg['port']}{cfg['voices_path']}"
    try:
        resp = httpx.get(url, timeout=VOICES_FETCH_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        voices = data.get("voices") if isinstance(data, dict) else data
        if isinstance(voices, list):
            names = [
                v if isinstance(v, str) else v.get("id") or v.get("name")
                for v in voices
            ]
            names = [n for n in names if isinstance(n, str)]
            if names:
                _voices_cache[service] = sorted(names)
                return _voices_cache[service]
    except Exception:
        pass
    return None


def resolve_fields(service: str, cfg: dict, status: str) -> list[dict]:
    """Return field definitions, swapping in live voice options when available."""
    if "voices_path" not in cfg or status != STATUS_RUNNING:
        return cfg["fields"]
    voices = fetch_live_voices(service, cfg)
    if not voices:
        return cfg["fields"]
    fields = []
    for field in cfg["fields"]:
        if field["name"] == "voice":
            field = {**field, "options": voices}
        fields.append(field)
    return fields


def find_container(service: str):
    containers = docker_client.containers.list(
        all=True, filters={"label": f"{COMPOSE_SERVICE_LABEL}={service}"}
    )
    return containers[0] if containers else None


@app.get("/api/models")
def list_models():
    result = []
    for name, cfg in MODELS.items():
        container = find_container(name)
        if container is None:
            status = STATUS_NOT_CREATED
        elif container.status == STATUS_RUNNING:
            status = STATUS_RUNNING
        else:
            status = STATUS_STOPPED
        result.append({
            "name": name,
            "label": cfg["label"],
            "description": cfg["description"],
            "status": status,
            "fields": resolve_fields(name, cfg, status),
        })
    return result


@app.post("/api/models/{service}/start")
def start_model(service: str):
    if service not in MODELS:
        raise HTTPException(404, f"Unknown service: {service}")
    container = find_container(service)
    if container is None:
        raise HTTPException(
            409,
            f"Container for '{service}' does not exist yet. "
            f"Run 'docker compose up -d {service}' once to create it.",
        )
    container.start()
    return {"status": STATUS_RUNNING}


@app.post("/api/models/{service}/stop")
def stop_model(service: str):
    if service not in MODELS:
        raise HTTPException(404, f"Unknown service: {service}")
    container = find_container(service)
    if container is None:
        raise HTTPException(409, f"Container for '{service}' does not exist.")
    container.stop()
    return {"status": STATUS_STOPPED}


def pcm_to_wav(pcm: bytes, rate: int, width: int, channels: int) -> bytes:
    """Wrap raw PCM chunks from Wyoming in a WAV header."""
    byte_rate = rate * channels * width
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, channels, rate, byte_rate, channels * width, width * 8,
        b"data", len(pcm),
    )
    return header + pcm


async def synthesize_wyoming(host: str, port: int, text: str) -> bytes:
    """Minimal Wyoming client: send a synthesize event, collect audio chunks."""
    reader, writer = await asyncio.open_connection(host, port)
    event = {"type": "synthesize", "data": {"text": text}}
    payload = json.dumps(event["data"]).encode()
    header = {"type": event["type"], "data_length": len(payload), "payload_length": 0}
    writer.write(json.dumps(header).encode() + b"\n" + payload)
    await writer.drain()

    pcm = io.BytesIO()
    rate, width, channels = WYOMING_SAMPLE_RATE, WYOMING_SAMPLE_WIDTH, WYOMING_CHANNELS
    while True:
        line = await reader.readline()
        if not line:
            break
        head = json.loads(line)
        data = b""
        if head.get("data_length"):
            data = await reader.readexactly(head["data_length"])
        chunk = b""
        if head.get("payload_length"):
            chunk = await reader.readexactly(head["payload_length"])
        if head["type"] in ("audio-start", "audio-chunk") and data:
            meta = json.loads(data)
            rate = meta.get("rate", rate)
            width = meta.get("width", width)
            channels = meta.get("channels", channels)
        if head["type"] == "audio-chunk":
            pcm.write(chunk)
        if head["type"] == "audio-stop":
            break
    writer.close()
    return pcm_to_wav(pcm.getvalue(), rate, width, channels)


@app.post("/api/generate/{service}")
async def generate(service: str, request: Request):
    cfg = MODELS.get(service)
    if cfg is None:
        raise HTTPException(404, f"Unknown service: {service}")

    form = await request.form()
    values = {}
    upload: UploadFile | None = None
    upload_field = None
    for field in cfg["fields"]:
        raw = form.get(field["name"])
        if isinstance(raw, UploadFile):
            if raw.filename:
                upload = raw
                upload_field = field["name"]
            continue
        if raw is None or raw == "":
            if "default" in field:
                values[field["name"]] = field["default"]
            elif field.get("required"):
                raise HTTPException(422, f"Missing required field: {field['name']}")
            elif field["name"] == "lyrics":
                values[field["name"]] = ""
            continue
        values[field["name"]] = float(raw) if field["type"] == "number" else raw

    if cfg["kind"] == KIND_WYOMING:
        wav = await synthesize_wyoming(cfg["host"], cfg["port"], values["text"])
        return Response(wav, media_type="audio/wav")

    url = f"http://{cfg['host']}:{cfg['port']}{cfg['path']}"
    timeout = httpx.Timeout(GENERATION_TIMEOUT_SECONDS, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:

        async def post_upstream():
            if cfg["kind"] == KIND_JSON:
                body = {**cfg.get("static_body", {}), **values}
                return await client.post(url, json=body)
            if cfg["kind"] == KIND_MULTIPART:
                files = {}
                if upload is not None:
                    files[upload_field] = (
                        upload.filename, await upload.read(), upload.content_type
                    )
                data = {k: str(v) for k, v in values.items()}
                return await client.post(url, data=data, files=files)
            raise HTTPException(500, f"Unknown request kind: {cfg['kind']}")

        # A container that was just started may not be listening yet;
        # retry connection failures for a bounded window before giving up.
        deadline = asyncio.get_event_loop().time() + CONNECT_RETRY_SECONDS
        while True:
            try:
                upstream = await post_upstream()
                break
            except httpx.ConnectError:
                if asyncio.get_event_loop().time() >= deadline:
                    raise HTTPException(
                        502,
                        f"'{cfg['label']}' is not reachable — is the container running?",
                    )
                await asyncio.sleep(CONNECT_RETRY_INTERVAL_SECONDS)

    if upstream.status_code >= 400:
        return JSONResponse(
            status_code=502,
            content={"detail": f"{cfg['label']} returned {upstream.status_code}: "
                               f"{upstream.text[:500]}"},
        )
    media_type = upstream.headers.get("content-type", "audio/wav")
    return Response(upstream.content, media_type=media_type)


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
