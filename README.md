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
- NVIDIA GPU + drivers ≥ 525 (CPU fallback noted per model)
- `nvidia-container-toolkit` installed and Docker configured to use it

---

## Quick start — all models

```bash
docker compose up -d
```

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

```yaml
services:

  piper:
    image: rhasspy/wyoming-piper:latest
    ports:
      - "10200:10200"
    volumes:
      - piper-voices:/data
    command: --voice en_US-lessac-medium

  kitten-tts:
    image: ghcr.io/kitten-tts/server:latest
    ports:
      - "8100:8000"
    volumes:
      - kitten-models:/models

  kokoro:
    image: ghcr.io/remsky/kokoro-fastapi-gpu:latest   # swap :cpu for CPU-only
    ports:
      - "8880:8880"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  melotts:
    image: ghcr.io/myshell-ai/melotts:latest
    ports:
      - "8200:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  chatterbox:
    image: ghcr.io/resemble-ai/chatterbox:latest
    ports:
      - "8300:8000"
    volumes:
      - chatterbox-models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  chatterbox-turbo:
    image: ghcr.io/resemble-ai/chatterbox-turbo:latest
    ports:
      - "8301:8000"
    volumes:
      - chatterbox-models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  stable-audio-sfx:
    image: ghcr.io/stability-ai/stable-audio-open-small:latest
    ports:
      - "8400:8000"
    environment:
      - MODE=sfx
    volumes:
      - stable-audio-models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  stable-audio-music:
    image: ghcr.io/stability-ai/stable-audio-open-small:latest
    ports:
      - "8401:8000"
    environment:
      - MODE=music
    volumes:
      - stable-audio-models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  ace-step:
    image: ghcr.io/ace-step/ace-step:latest
    ports:
      - "8500:7860"
    volumes:
      - ace-step-models:/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  piper-voices:
  kitten-models:
  chatterbox-models:
  stable-audio-models:
  ace-step-models:
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
