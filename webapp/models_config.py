"""Central registry of managed voice-model services.

Single source of truth for service names, upstream endpoints and the
input fields each model accepts. The frontend renders its forms from
this config; the proxy builds upstream requests from it.
"""

# Request kinds — how /api/generate talks to the upstream service.
KIND_JSON = "json"            # POST JSON body, audio bytes back
KIND_MULTIPART = "multipart"  # POST multipart form (supports file upload)
KIND_WYOMING = "wyoming"      # Wyoming TCP protocol (Piper)

# Field types for form rendering.
FIELD_TEXT = "text"
FIELD_TEXTAREA = "textarea"
FIELD_NUMBER = "number"
FIELD_FILE = "file"
FIELD_SELECT = "select"

MODELS = {
    "piper": {
        "label": "Piper",
        "description": "Narration and announcements, preset voices, many languages",
        "kind": KIND_WYOMING,
        "host": "piper",
        "port": 10200,
        "fields": [
            {"name": "text", "type": FIELD_TEXTAREA, "label": "Text", "required": True},
        ],
    },
    "kitten-tts": {
        "label": "Kitten TTS",
        "description": "English narration, preset voices",
        "kind": KIND_JSON,
        "host": "kitten-tts",
        "port": 8000,
        "path": "/tts",
        "fields": [
            {"name": "text", "type": FIELD_TEXTAREA, "label": "Text", "required": True},
            {"name": "voice", "type": FIELD_SELECT, "label": "Voice",
             "options": [
                 "expr-voice-2-f", "expr-voice-2-m", "expr-voice-3-f", "expr-voice-3-m",
                 "expr-voice-4-f", "expr-voice-4-m", "expr-voice-5-f", "expr-voice-5-m",
             ],
             "default": "expr-voice-2-f"},
        ],
    },
    "kokoro": {
        "label": "Kokoro",
        "description": "Natural narration, 54 preset voices, several languages",
        "kind": KIND_JSON,
        "host": "kokoro",
        "port": 8880,
        "path": "/v1/audio/speech",
        "static_body": {"model": "kokoro", "response_format": "wav"},
        # Voice list is fetched live from the service when it is running;
        # these options are the fallback when it is not.
        "voices_path": "/v1/audio/voices",
        "fields": [
            {"name": "input", "type": FIELD_TEXTAREA, "label": "Text", "required": True},
            {"name": "voice", "type": FIELD_SELECT, "label": "Voice",
             "options": [
                 "af_bella", "af_heart", "af_nicole", "af_sarah", "af_sky",
                 "am_adam", "am_michael",
                 "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
             ],
             "default": "af_bella"},
        ],
    },
    "melotts": {
        "label": "MeloTTS",
        "description": "Multilingual narration, preset voices",
        "kind": KIND_JSON,
        "host": "melotts",
        "port": 8000,
        "path": "/synthesize",
        "fields": [
            {"name": "text", "type": FIELD_TEXTAREA, "label": "Text", "required": True},
            {"name": "language", "type": FIELD_SELECT, "label": "Language",
             "options": ["EN", "FR", "ES", "ZH", "JP", "KR"], "default": "EN"},
            {"name": "speaker_id", "type": FIELD_SELECT, "label": "Speaker",
             "options": [
                 "EN-Default", "EN-US", "EN-BR", "EN_INDIA", "EN-AU",
                 "FR", "ES", "ZH", "JP", "KR",
             ],
             "default": "EN-Default"},
            {"name": "speed", "type": FIELD_NUMBER, "label": "Speed", "default": 1.0},
        ],
    },
    "chatterbox": {
        "label": "Chatterbox",
        "description": "Voice cloning from a short sample, emotion control",
        "kind": KIND_MULTIPART,
        "host": "chatterbox",
        "port": 8000,
        "path": "/synthesize",
        "fields": [
            {"name": "text", "type": FIELD_TEXTAREA, "label": "Text", "required": True},
            {"name": "audio_prompt", "type": FIELD_FILE, "label": "Voice sample (5–30 s)"},
            {"name": "exaggeration", "type": FIELD_NUMBER, "label": "Emotion 0–1", "default": 0.5},
            {"name": "cfg_weight", "type": FIELD_NUMBER, "label": "Stability 0–1", "default": 0.5},
        ],
    },
    "chatterbox-turbo": {
        "label": "Chatterbox Turbo",
        "description": "Voice cloning plus non-verbals: [laughs], [coughs], [sighs]",
        "kind": KIND_MULTIPART,
        "host": "chatterbox-turbo",
        "port": 8000,
        "path": "/synthesize",
        "fields": [
            {"name": "text", "type": FIELD_TEXTAREA, "label": "Text", "required": True},
            {"name": "audio_prompt", "type": FIELD_FILE, "label": "Voice sample (5–30 s)"},
            {"name": "exaggeration", "type": FIELD_NUMBER, "label": "Emotion 0–1", "default": 0.7},
        ],
    },
    "stable-audio-sfx": {
        "label": "Stable Audio — SFX",
        "description": "One-shots, UI sounds, foley, ambience, up to 120 s",
        "kind": KIND_JSON,
        "host": "stable-audio-sfx",
        "port": 8000,
        "path": "/generate",
        "fields": [
            {"name": "prompt", "type": FIELD_TEXTAREA, "label": "Prompt", "required": True},
            {"name": "duration", "type": FIELD_NUMBER, "label": "Duration (s, max 120)", "default": 3.0},
            {"name": "steps", "type": FIELD_NUMBER, "label": "Steps", "default": 100},
        ],
    },
    "stable-audio-music": {
        "label": "Stable Audio — Music",
        "description": "Instrumental loops and background tracks, up to 120 s",
        "kind": KIND_JSON,
        "host": "stable-audio-music",
        "port": 8000,
        "path": "/generate",
        "fields": [
            {"name": "prompt", "type": FIELD_TEXTAREA, "label": "Prompt", "required": True},
            {"name": "duration", "type": FIELD_NUMBER, "label": "Duration (s, max 120)", "default": 30.0},
            {"name": "steps", "type": FIELD_NUMBER, "label": "Steps", "default": 150},
        ],
    },
    "ace-step": {
        "label": "ACE-Step 1.5",
        "description": "Full songs with sung vocals in 50+ languages, 10 s–10 min",
        "kind": KIND_JSON,
        "host": "ace-step",
        "port": 7860,
        "path": "/generate",
        "static_body": {"task": "text2song"},
        "fields": [
            {"name": "lyrics", "type": FIELD_TEXTAREA, "label": "Lyrics (empty = instrumental)"},
            {"name": "tags", "type": FIELD_TEXT, "label": "Style tags", "required": True},
            {"name": "duration", "type": FIELD_NUMBER, "label": "Duration (s)", "default": 60},
            {"name": "language", "type": FIELD_TEXT, "label": "Language", "default": "en"},
        ],
    },
}
