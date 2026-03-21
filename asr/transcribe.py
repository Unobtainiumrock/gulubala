"""Stage 1: Audio -> text transcription via Higgs ASR 3.

Uses the Eigen multipart ``/generate`` endpoint (not chat completions).
"""

from __future__ import annotations

from client.eigen import asr_generate, decode_b64_audio


def transcribe(chunks: list[str]) -> str:
    """Transcribe audio chunks to text using Higgs ASR 3.

    Each chunk is sent as a separate multipart request; the results are
    concatenated with spaces.

    Args:
        chunks: List of base64-encoded WAV strings from audio.ingest.

    Returns:
        Plain text transcription.
    """
    parts: list[str] = []
    for i, b64_chunk in enumerate(chunks):
        audio_bytes = decode_b64_audio(b64_chunk)
        text = asr_generate(audio_bytes, filename=f"chunk_{i}.wav")
        if text and text.strip():
            parts.append(text.strip())
    return " ".join(parts)


def transcribe_file(path: str) -> str:
    """Convenience: transcribe directly from an audio file path."""
    from audio.ingest import chunk_audio_file
    chunks = chunk_audio_file(path)
    return transcribe(chunks)
