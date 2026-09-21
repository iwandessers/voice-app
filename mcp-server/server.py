"""MCP server for the voice-app stack.

Exposes the control panel's HTTP API as MCP tools so an MCP client
(Claude Code, Claude Desktop, ...) can start/stop the model containers
and generate audio. Generated audio is written to OUTPUT_DIR and the
file path is returned, since MCP responses are text.

Run (stdio transport):
    python server.py

Run (streamable HTTP transport, for remote MCP clients):
    MCP_TRANSPORT=streamable-http python server.py

Environment:
    PANEL_URL      control panel base URL (default http://localhost:8080)
    OUTPUT_DIR     where generated audio is saved (default ~/voice-app-outputs)
    MCP_TRANSPORT    'stdio' (default) or 'streamable-http'
    MCP_HOST         bind address for HTTP transport (default 127.0.0.1)
    MCP_PORT         port for HTTP transport (default 8600)
    PUBLIC_BASE_URL  external base URL of this server as clients reach it
                     (e.g. http://1.2.3.4:8091/voice-mcp); used to build
                     download links for generated audio in HTTP mode
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

PANEL_URL = os.environ.get("PANEL_URL", "http://localhost:8080").rstrip("/")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", str(Path.home() / "voice-app-outputs")))

TRANSPORT_STDIO = "stdio"
TRANSPORT_HTTP = "streamable-http"
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", TRANSPORT_STDIO)
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8600"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
FILES_ROUTE_PREFIX = "files"

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

# Ordered candidates: (executable, extra args before the file path).
# First one found on PATH wins. All exit after playback finishes.
AUDIO_PLAYERS = [
    ("afplay", []),                                            # macOS
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "error"]),
    ("mpv", ["--no-video", "--really-quiet"]),
    ("paplay", []),                                            # PulseAudio
    ("aplay", ["-q"]),                                         # ALSA, wav only
]
PLAYBACK_TIMEOUT_SECONDS = 1200

mcp = MCPServer("voice-app")


def _play_file(path: Path) -> str:
    """Play an audio file with the first available system player."""
    if not path.is_file():
        raise ToolError(f"audio file not found: {path}")
    if sys.platform == "win32":
        # SoundPlayer only handles WAV, which is what the models produce.
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(New-Object Media.SoundPlayer '{path}').PlaySync()"],
            check=True, timeout=PLAYBACK_TIMEOUT_SECONDS,
        )
        return "powershell SoundPlayer"
    for executable, extra_args in AUDIO_PLAYERS:
        if shutil.which(executable):
            subprocess.run(
                [executable, *extra_args, str(path)],
                check=True, timeout=PLAYBACK_TIMEOUT_SECONDS,
            )
            return executable
    raise ToolError(
        "No audio player found on this machine (tried: "
        + ", ".join(name for name, _ in AUDIO_PLAYERS)
        + "). Note: playback happens where the MCP server runs — on a "
        "headless server there is nothing to play through. Run the MCP "
        "server on your local machine with PANEL_URL pointing at the "
        "panel to hear audio locally."
    )


def _panel(method: str, path: str, **kwargs) -> httpx.Response:
    timeout = kwargs.pop("timeout", CONTROL_TIMEOUT_SECONDS)
    resp = httpx.request(method, f"{PANEL_URL}{path}", timeout=timeout, **kwargs)
    if resp.status_code >= 400:
        detail = resp.text[:500]
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise ToolError(f"Panel returned {resp.status_code}: {detail}")
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
    audio_prompt_url: str | None = None,
    output_name: str | None = None,
    play: bool = False,
) -> str:
    """Generate audio with a model and save it to a file; returns the path
    (and, when the server is reachable over HTTP, a download_url).

    'model' is a name from list_models. 'params' holds that model's fields,
    e.g. {"text": "Hello"} for TTS models,
    {"tags": "lofi hip hop", "duration": 30} for ace-step,
    {"prompt": "dog barking", "seconds_total": 5} for stable-audio.
    Check list_models for each model's exact fields, defaults and options.

    Voice cloning (chatterbox / chatterbox-turbo only): 'audio_prompt_path'
    is an audio file on the machine running this MCP server;
    'audio_prompt_url' fetches the sample over HTTP instead — use it when
    the MCP server runs remotely. Set 'play' to also play the result
    through the speakers of the machine running this MCP server.

    The model must be running (start_model) — a just-started container is
    retried automatically. CPU generation is slow: expect minutes, and a
    large one-time checkpoint download on a model's first ever request.
    """
    data = {k: str(v) for k, v in params.items()}
    files = None
    if audio_prompt_path:
        path = Path(audio_prompt_path).expanduser()
        if not path.is_file():
            raise ToolError(f"audio prompt not found: {path}")
        files = {"audio_prompt": (path.name, path.read_bytes())}
    elif audio_prompt_url:
        try:
            prompt_resp = httpx.get(
                audio_prompt_url, timeout=CONTROL_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            prompt_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolError(f"could not fetch audio prompt: {exc}")
        name = Path(httpx.URL(audio_prompt_url).path).name or "prompt.wav"
        files = {"audio_prompt": (name, prompt_resp.content)}

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
    result = {
        "path": str(out_path),
        "bytes": len(resp.content),
        "media_type": media_type or "audio/wav",
    }
    if PUBLIC_BASE_URL:
        result["download_url"] = (
            f"{PUBLIC_BASE_URL}/{FILES_ROUTE_PREFIX}/{out_path.name}"
        )
    if play:
        result["played_with"] = _play_file(out_path)
    return json.dumps(result)


@mcp.custom_route(f"/{FILES_ROUTE_PREFIX}/{{filename}}", methods=["GET"])
async def download_file(request):
    """Serve a generated audio file from OUTPUT_DIR (HTTP transport only)."""
    from starlette.responses import FileResponse, JSONResponse

    # Path(...).name strips any directory components, preventing traversal
    # out of OUTPUT_DIR.
    filename = Path(request.path_params["filename"]).name
    path = OUTPUT_DIR / filename
    if not path.is_file():
        return JSONResponse({"detail": f"no such file: {filename}"}, status_code=404)
    extension = path.suffix.lower()
    media_type = next(
        (mt for mt, ext in MEDIA_TYPE_EXTENSIONS.items() if ext == extension),
        "application/octet-stream",
    )
    return FileResponse(path, media_type=media_type, filename=filename)


@mcp.tool()
def play_audio(path: str) -> str:
    """Play an audio file through the speakers of the machine running this
    MCP server. Playback is synchronous; returns when the clip ends."""
    played_with = _play_file(Path(path).expanduser())
    return json.dumps({"played": path, "played_with": played_with})


if __name__ == "__main__":
    if MCP_TRANSPORT == TRANSPORT_HTTP:
        # Stateless: no per-session state, works behind a reverse proxy
        # and for any number of clients.
        mcp.run(
            transport=TRANSPORT_HTTP,
            host=MCP_HOST,
            port=MCP_PORT,
            stateless_http=True,
        )
    else:
        mcp.run()
