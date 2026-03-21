"""Model configuration and API constants."""

import os

# Eigen AI model identifiers
HIGGS_ASR_MODEL = "higgs_asr_3"
HIGGS_CHAT_MODEL = "gpt-oss-120b"
GPT_OSS_MODEL = "gpt-oss-120b"

# Non-modifiable API parameters
STOP_SEQUENCES = ["<|eot_id|>", "<|endoftext|>", "<|audio_eos|>", "<|im_end|>"]
REASONING_EFFORT = "medium"
EXTRA_BODY = {"skip_special_tokens": False, "reasoning_effort": REASONING_EFFORT}

# Audio processing constants
MAX_CHUNK_SECONDS = 4
SAMPLE_RATE = 16000

# Intent detection
INTENT_CONFIDENCE_THRESHOLD = 0.7
DISAMBIGUATION_THRESHOLD = 0.5

# Validation
MAX_VALIDATION_RETRIES = 3
MAX_TURNS_BEFORE_STALL = 8
MULTI_FIELD_BATCH_SIZE = 3

# Session and privacy settings
SESSION_DB_PATH = os.environ.get("SESSION_DB_PATH", "call_center_sessions.sqlite3")
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
