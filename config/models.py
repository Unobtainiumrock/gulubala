"""Model configuration and API constants."""

# Eigen AI model identifiers
HIGGS_ASR_MODEL = "higgs-audio-understanding-v3-Hackathon"
HIGGS_CHAT_MODEL = "higgs-2.5"
GPT_OSS_MODEL = "gpt-oss-120b"

# Non-modifiable API parameters (from hackathon spec)
STOP_SEQUENCES = ["<|eot_id|>", "<|endoftext|>", "<|audio_eos|>", "<|im_end|>"]
EXTRA_BODY = {"skip_special_tokens": False}

# Audio processing constants
MAX_CHUNK_SECONDS = 4
SAMPLE_RATE = 16000

# Intent detection
INTENT_CONFIDENCE_THRESHOLD = 0.7
DISAMBIGUATION_THRESHOLD = 0.5

# Validation
MAX_VALIDATION_RETRIES = 3
