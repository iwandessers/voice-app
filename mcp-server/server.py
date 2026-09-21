"""MCP server for the voice-app stack.

Exposes the control panel's HTTP API as MCP tools so an MCP client
(Claude Code, Claude Desktop, ...) can start/stop the model containers
and generate audio. Generated audio is written to OUTPUT_DIR and the
file path is returned, since MCP responses are text.

Run (stdio transport):
    python server.py

Environment:
    PANEL_URL   control panel base URL (default http://localhost:8080)
    OUTPUT_DIR  where generated audio is saved (default ~/voice-app-outputs)
"""

import json
import os
import time
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer

PANEL_URL = os.environ.get("PANEL_URL", "http://localhost:8080").rstrip("/")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(Path.home() / "voice-app-outputs")))

# CPU inference is slow and heavy models download checkpoints on first use.
GENERATION_TIMEOUT_SECONDS = 1800
CONTROL_TIMEOUT_SECONDS = 60

MEDIA_TYPE_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
}
DEFAULT_EXTENSION = ".wav"

mcp = MCPServer("voice-app")


def _panel(method: str, path: str, **kwargs) -> httpx.Response:
    timeout = kwargs.pop("timeout", CONTROL_TIMEOUT_SECONDS)
    resp = httpx.request(method, f"{PANEL_URL}{path}", timeout=timeout, **kwargs)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise RuntimeError(f"Panel returned {resp.status_code}: {detail}")
    return resp


@mcp.tool()
def list_models() -> str:
    """List all voice models: name, description, running status, and the
    input fields each model's generate call accepts (with defaults and
    allowed options for dropdown fields)."""
    return json.dumps(_panel("GET", "/api/models").json(), indent=2)


@mcp.tool()
def start_model(name: str) -> str:
    """Start a model's container. Use the 'name' from list_models
    (e.g. 'piper', 'kokoro', 'chatterbox', 'ace-step')."""
    _panel("POST", f"/api/models/{name}/start")
    return f"{name}: running"


@mcp.tool()
def stop_model(name: str) -> str:
    """Stop a model's container to free RAM."""
    _panel("POST", f"/api/models/{name}/stop")
    return f"{name}: stopped"


@mcp.tool()
def generate_audio(
    model: str,
    params: dict,
    audio_prompt_path: str | None = None,
    output_name: str | None = None,
) -> str:
    """Generate audio with a model and save it to a file; returns the path.

    'model' is a name from list_models. 'params' holds that model's fields,
    e.g. {"text": "Hello"} for TTS models,
    {"tags": "lofi hip hop", "duration": 30} for ace-step,
    {"prompt": "dog barking", "seconds_total": 5} for stable-audio.
    Check list_models for each model's exact fields, defaults and options.

    'audio_prompt_path' is a local audio file for voice cloning
    (chatterbox / chatterbox-turbo only).

    The model must be running (start_model) — a just-started container is
    retried automatically. CPU generation is slow: expect minutes, and a
    large one-time checkpoint download on a model's first ever request.
    """
    data = {k: str(v) for k, v in params.items()}
    files = None
    if audio_prompt_path:
        path = Path(audio_prompt_path).expanduser()
        if not path.is_file():
            raise RuntimeError(f"audio prompt not found: {path}")
        files = {"audio_prompt": (path.name, path.read_bytes())}

    resp = _panel(
        "POST",
        f"/api/generate/{model}",
        data=data,
        files=files,
        timeout=GENERATION_TIMEOUT_SECONDS,
    )

    media_type = resp.headers.get("content-type", "").split(";")[0].strip()
    extension = MEDIA_TYPE_EXTENSIONS.get(media_type, DEFAULT_EXTENSION)
    stem = output_name or f"{model}-{int(time.time())}"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{Path(stem).stem}{extension}"
    out_path.write_bytes(resp.content)
    return json.dumps({
        "path": str(out_path),
        "bytes": len(resp.content),
        "media_type": media_type or "audio/wav",
    })


if __name__ == "__main__":
    mcp.run()
