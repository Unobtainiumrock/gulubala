"""Stage 1: Audio → text transcription via Higgs ASR 3."""

from client.eigen import chat_completion
from config.models import HIGGS_ASR_MODEL


def _build_audio_messages(chunks: list[str], system_prompt: str) -> list:
    """Build OpenAI-compatible messages with indexed audio chunks."""
    content_parts = []
    for i, chunk in enumerate(chunks):
        content_parts.append({
            "type": "input_audio",
            "input_audio": {
                "data": chunk,
                "format": f"audio/wav_{i}",
            },
        })

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_parts},
    ]


ASR_SYSTEM_PROMPT = (
    "You are a speech-to-text transcription engine. "
    "Transcribe the caller's speech exactly as spoken. "
    "Output only the transcription text, nothing else."
)


def transcribe(chunks: list[str]) -> str:
    """Transcribe audio chunks to text using Higgs ASR 3.

    Args:
        chunks: List of base64-encoded WAV strings from audio.ingest.

    Returns:
        Plain text transcription.
    """
    messages = _build_audio_messages(chunks, ASR_SYSTEM_PROMPT)
    return chat_completion(
        model=HIGGS_ASR_MODEL,
        messages=messages,
        temperature=0.2,
        top_p=0.9,
        max_tokens=2048,
    )


def transcribe_file(path: str) -> str:
    """Convenience: transcribe directly from an audio file path."""
    from audio.ingest import chunk_audio_file
    chunks = chunk_audio_file(path)
    return transcribe(chunks)
