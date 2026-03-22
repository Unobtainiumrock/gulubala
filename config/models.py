"""Model configuration and API constants."""

import os

# Eigen API endpoints
EIGEN_BASE_URL = os.environ.get("EIGEN_BASE_URL", "https://api-web.eigenai.com/api/v1")
EIGEN_GENERATE_URL = os.environ.get("EIGEN_GENERATE_URL", f"{EIGEN_BASE_URL.rstrip('/')}/generate")

# Eigen AI model identifiers
HIGGS_ASR_MODEL = os.environ.get("HIGGS_ASR_MODEL", "higgs_asr_3")
GPT_OSS_MODEL = os.environ.get("GPT_OSS_MODEL", "gpt-oss-120b")
HIGGS_TTS_MODEL = os.environ.get("HIGGS_TTS_MODEL", "higgs2p5")
HIGGS_CHAT_MODEL = os.environ.get("HIGGS_CHAT_MODEL", GPT_OSS_MODEL)

# Non-modifiable API parameters
STOP_SEQUENCES = ["<|eot_id|>", "<|endoftext|>", "<|audio_eos|>", "<|im_end|>"]
REASONING_EFFORT = "medium"
EXTRA_BODY = {"skip_special_tokens": False, "reasoning_effort": REASONING_EFFORT}

# Audio processing constants
MAX_CHUNK_SECONDS = 4
SAMPLE_RATE = 16000
ASR_LANGUAGE = os.environ.get("ASR_LANGUAGE", "English")

# Intent detection
INTENT_CONFIDENCE_THRESHOLD = 0.7
DISAMBIGUATION_THRESHOLD = 0.5

# Validation
MAX_VALIDATION_RETRIES = 3
MAX_TURNS_BEFORE_STALL = 8
MULTI_FIELD_BATCH_SIZE = 3

# Session and privacy settings
SESSION_DB_PATH = os.environ.get("SESSION_DB_PATH", "call_center_sessions.sqlite3")
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(24 * 60 * 60)))  # default 24h
TRANSCRIPT_RETENTION_ENABLED = os.environ.get("TRANSCRIPT_RETENTION_ENABLED", "false").lower() == "true"
TRANSCRIPT_CONTEXT_TURNS = int(os.environ.get("TRANSCRIPT_CONTEXT_TURNS", "6"))
REDACT_FIELD_HINTS = (
    "account",
    "verification",
    "phone",
    "email",
    "order",
    "zip",
)

# Demo branding
DEMO_BRAND_NAME = os.environ.get("DEMO_BRAND_NAME", "Callit-Dev")
DEMO_TTS_VOICE = os.environ.get("DEMO_TTS_VOICE", "Linda")

# Twilio integration
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_IVR_NUMBER = os.environ.get("TWILIO_IVR_NUMBER", "")
TWILIO_AGENT_NUMBER = os.environ.get("TWILIO_AGENT_NUMBER", "")
PRESENTER_PHONE_NUMBER = os.environ.get("PRESENTER_PHONE_NUMBER", "")

# Scripted cancel_service demo: force presenter gather + retention bridge (default on).
DEMO_FORCE_HUMAN_FLOWS = os.environ.get("DEMO_FORCE_HUMAN_FLOWS", "1").lower() in (
    "1",
    "true",
    "yes",
)

# Public base URL for transcript links in SMS (e.g. ngrok). Falls back to NGROK_URL.
_NGROK = os.environ.get("NGROK_URL", "").strip().rstrip("/")
_PUBLIC = os.environ.get("PUBLIC_API_BASE_URL", "").strip().rstrip("/")
PUBLIC_API_BASE_URL = _PUBLIC or _NGROK
