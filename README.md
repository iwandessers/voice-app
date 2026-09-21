# Voice App — AI Audio Models

Local inference stack for speech synthesis, sound effects, music, and full-song generation.

---

## Models at a glance

| Model | Output | Languages | Voices |
|---|---|---|---|
| Piper | Narration / announcements | Many | Preset |
| Kitten TTS | Narration | English | Preset |
| Kokoro | Natural narration | Several | 54 preset |
| MeloTTS | Narration | Multilingual | Preset |
| Chatterbox | Speech + emotion | Any (voice clone) | Any short sample |
| Chatterbox Turbo | Speech + non-verbals | Any (voice clone) | Any short sample |
| Stable Audio 3 Small — SFX | Sound effects (≤120 s) | — | — |
| Stable Audio 3 Small — Music | Instrumental music (≤120 s) | — | — |
| ACE-Step 1.5 | Full songs w/ vocals (10 s–10 min) | 50+ | — |

---

## Prerequisites

- Docker ≥ 24 and Docker Compose v2
- CPU-only setup — no GPU required. All services run on CPU.
- ~35 GB free RAM to run every model at once (heaviest: ACE-Step and the two Chatterbox variants). Fewer models need less.
- Expect slow inference on CPU, especially ACE-Step and Stable Audio (minutes, not seconds).

---

## Quick start — all models

All models can run at the same time; `up -d` starts every service concurrently.

```bash
docker compose up -d
```

## Control panel

A web UI at **http://localhost:8080** (service `control-panel`, source in `webapp/`) that can:

- Show live status of every model container
- Start / stop each model individually
- Send generation requests to any model via a form and play or download the resulting audio

It talks to Docker via the mounted `/var/run/docker.sock` and proxies inference requests to the model containers over the compose network, so no other ports need to be open to the browser.

```bash
docker compose up -d --build control-panel
```

### External access on this host

The host's external firewall only allows a handful of ports, so the panel is additionally reachable through the `allthingsworn` nginx on port 8091 at **http://\<server-ip\>:8091/voice/**. That setup consists of:

- a `location /voice/` reverse-proxy block in that project's `docker/default.conf` (with `absolute_redirect off` so redirects keep the external port),
- the nginx container joined to this project's network: `docker network connect voice-app_default nginx-allthingsworn` — note this is a runtime setting and must be re-run if either container is recreated.

The panel frontend uses relative API paths, so it works both at the root (port 8080) and under the `/voice/` prefix.

### Shut everything down

```bash
docker compose down
```

### Shut down and remove model caches

```bash
docker compose down -v
```

---

## docker-compose.yml

The full stack is defined in [`docker-compose.yml`](docker-compose.yml) — CPU-only, all nine models plus the `control-panel` service.

- **Piper** and **Kokoro** use official published images (`rhasspy/wyoming-piper`, `ghcr.io/remsky/kokoro-fastapi-cpu`).
- The remaining models have no official Docker images, so they are built locally from [`model-servers/`](model-servers/): a shared CPU torch base image plus a small FastAPI wrapper per model. Models load lazily on the first generation request, so containers start instantly; the first request triggers the checkpoint download from Hugging Face.
- **Stable Audio** requires a Hugging Face token (gated repo): `export HF_TOKEN=...` before `docker compose up`, and accept the licence at huggingface.co/stabilityai/stable-audio-open-small.
- Build the base image once before the first `docker compose build`: `docker build -t voice-app-torch-base:latest model-servers/base/`

## Tests

Playwright E2E suite in [`tests/`](tests/) — verifies the panel renders all model cards, starts and stops every model container through the UI, and runs a real Kokoro generation through the form.

```bash
cd tests && npm install && npx playwright install chromium-headless-shell
npx playwright test
```

---

## MCP server

[`mcp-server/`](mcp-server/) exposes the stack to MCP clients (Claude Code,
Claude Desktop, ...) over stdio. It wraps the control panel API, so the panel
must be running (`docker compose up -d control-panel`).

Tools:

| Tool | Purpose |
|---|---|
| `list_models` | All models with status and per-model input fields |
| `start_model` / `stop_model` | Start or stop a model container |
| `generate_audio` | Generate audio; saves the file and returns its path |
| `play_audio` | Play a saved file through the local speakers |

`generate_audio` takes the model name, a `params` object matching the fields
from `list_models` (e.g. `{"text": "Hi"}`, or `{"tags": "lofi", "duration": 30}`
for ACE-Step), optionally `audio_prompt_path` — a local audio file for
Chatterbox voice cloning — and `play: true` to play the result immediately.
Output lands in `~/voice-app-outputs/` (override with `OUTPUT_DIR`; panel
location with `PANEL_URL`, default `http://localhost:8080`).

Playback happens on the machine running the MCP server (first of `afplay`,
`ffplay`, `mpv`, `paplay`, `aplay` found; `SoundPlayer` on Windows). A headless
server has no audio output — to hear audio, install the MCP server on your own
computer and point it at the panel with `PANEL_URL`. Everything else works the
same remotely: the server only speaks HTTP to the panel, and voice-cloning
prompt files are read from the machine the MCP server runs on.

### Install on the server (same host as the panel)

```bash
cd mcp-server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
claude mcp add voice-app -- "$(pwd)/.venv/bin/python" "$(pwd)/server.py"
```

### Install on your own computer (recommended — enables playback)

Requires Python 3.10+ and network access to the panel
(e.g. `http://<server-ip>:8091/voice`).

macOS / Linux:

```bash
git clone git@github.com:iwandessers/voice-app.git
cd voice-app/mcp-server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Claude Code
claude mcp add voice-app --env PANEL_URL=http://<server-ip>:8091/voice \
  -- "$(pwd)/.venv/bin/python" "$(pwd)/server.py"
```

Windows (PowerShell):

```powershell
git clone git@github.com:iwandessers/voice-app.git
cd voice-app\mcp-server
py -m venv .venv; .venv\Scripts\pip install -r requirements.txt

claude mcp add voice-app --env PANEL_URL=http://<server-ip>:8091/voice `
  -- "$PWD\.venv\Scripts\python.exe" "$PWD\server.py"
```

For Claude Desktop instead, add to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "voice-app": {
      "command": "/absolute/path/to/voice-app/mcp-server/.venv/bin/python",
      "args": ["/absolute/path/to/voice-app/mcp-server/server.py"],
      "env": { "PANEL_URL": "http://<server-ip>:8091/voice" }
    }
  }
}
```

macOS plays out of the box (`afplay`); on Linux install one of the listed
players if none is present (e.g. `sudo apt install ffmpeg` for `ffplay`).

### Smoke test

Needs the panel and Kokoro running; add `PANEL_URL=...` when remote:

```bash
.venv/bin/python test_client.py
```

---

## Per-model usage

### Piper — port 10200 (Wyoming protocol)

```bash
# Synthesise via Wyoming protocol (e.g. Home Assistant integration)
echo "Hello world" | nc localhost 10200 > output.wav

# Or use the wyoming-cli helper
pip install wyoming
wyoming-tts --host localhost --port 10200 --text "Hello world" --output output.wav
```

**Available voices:** pass `--voice <name>` in the compose command.
List voices: `docker exec <container> ls /data/`

---

### Kitten TTS — port 8100

```bash
curl -X POST http://localhost:8100/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "voice": "default"}' \
  --output output.wav
```

**List voices:**
```bash
curl http://localhost:8100/voices
```

---

### Kokoro — port 8880

REST API (OpenAI-compatible `/v1/audio/speech`):

```bash
curl -X POST http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kokoro",
    "input": "Hello world",
    "voice": "af_bella",
    "response_format": "wav"
  }' \
  --output output.wav
```

**List voices:**
```bash
curl http://localhost:8880/v1/audio/voices
```

---

### MeloTTS — port 8200

```bash
curl -X POST http://localhost:8200/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "language": "EN",
    "speaker_id": "EN-Default",
    "speed": 1.0
  }' \
  --output output.wav
```

**Supported languages:** `EN`, `FR`, `ES`, `ZH`, `JP`, `KR`

---

### Chatterbox — port 8300

Speech from a voice clone sample:

```bash
curl -X POST http://localhost:8300/synthesize \
  -F "text=Hello world" \
  -F "audio_prompt=@sample.wav" \
  -F "exaggeration=0.5" \
  -F "cfg_weight=0.5" \
  --output output.wav
```

**Parameters:**
- `exaggeration` — emotion intensity `0.0–1.0` (default `0.5`)
- `cfg_weight` — pacing/stability `0.0–1.0` (higher = slower, more stable)
- `audio_prompt` — WAV/MP3, 5–30 s recommended

---

### Chatterbox Turbo — port 8301

Same API as Chatterbox. Adds non-verbal sounds (laughs, coughs, sighs):

```bash
curl -X POST http://localhost:8301/synthesize \
  -F "text=Hello world, [laughs]" \
  -F "audio_prompt=@sample.wav" \
  -F "exaggeration=0.7" \
  --output output.wav
```

Non-verbal tokens: `[laughs]`, `[coughs]`, `[sighs]`, `[clears throat]`

---

### Stable Audio 3 Small — SFX — port 8400

```bash
curl -X POST http://localhost:8400/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Glass breaking on a hard floor, single impact, close mic",
    "duration": 3.0,
    "steps": 100
  }' \
  --output sfx.wav
```

- `duration` — seconds, max `120`
- `steps` — diffusion steps, `50`–`200` (higher = better quality, slower)

---

### Stable Audio 3 Small — Music — port 8401

```bash
curl -X POST http://localhost:8401/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Upbeat lo-fi hip hop, 90 BPM, jazzy chords, no vocals",
    "duration": 30.0,
    "steps": 150
  }' \
  --output music.wav
```

---

### ACE-Step 1.5 — port 8500

**Full song with lyrics:**

```bash
curl -X POST http://localhost:8500/generate \
  -H "Content-Type: application/json" \
  -d '{
    "task": "text2song",
    "lyrics": "[verse]\nWalking down the road\nSun is shining bright\n[chorus]\nEverything is fine",
    "tags": "pop, upbeat, female vocal, guitar",
    "duration": 60,
    "language": "en"
  }' \
  --output song.mp3
```

**Instrumental only:**

```bash
curl -X POST http://localhost:8500/generate \
  -H "Content-Type: application/json" \
  -d '{
    "task": "text2song",
    "lyrics": "",
    "tags": "cinematic, orchestral, epic, no vocals",
    "duration": 90
  }' \
  --output instrumental.mp3
```

**Cover (vocal-to-backing-track):**

```bash
curl -X POST http://localhost:8500/generate \
  -F "task=retransfer" \
  -F "audio=@original.mp3" \
  -F "tags=jazz arrangement, piano, double bass" \
  --output cover.mp3
```

**Duration range:** 10–600 seconds. **Supported languages:** 50+, pass ISO code in `language`.

---

## Service ports summary

| Service | Port | Protocol |
|---|---|---|
| Control panel | 8080 | HTTP (web UI) |
| Piper | 10200 | Wyoming (TCP) |
| Kitten TTS | 8100 | HTTP REST |
| Kokoro | 8880 | HTTP REST (OpenAI-compat) |
| MeloTTS | 8200 | HTTP REST |
| Chatterbox | 8300 | HTTP multipart |
| Chatterbox Turbo | 8301 | HTTP multipart |
| Stable Audio SFX | 8400 | HTTP REST |
| Stable Audio Music | 8401 | HTTP REST |
| ACE-Step | 8500 | HTTP REST / Gradio |

---

## Individual service control

```bash
# Start one service
docker compose up -d kokoro

# Stop one service
docker compose stop kokoro

# View logs
docker compose logs -f kokoro

# Restart after config change
docker compose up -d --force-recreate kokoro
```
