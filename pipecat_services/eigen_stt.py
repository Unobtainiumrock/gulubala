"""Pipecat STT service wrapping Eigen's Higgs ASR 3 endpoint."""

from __future__ import annotations

import asyncio
import io
import wave
from typing import AsyncGenerator

from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601

from asr.transcribe import transcribe_bytes
from config.models import SAMPLE_RATE


class EigenSTTService(SegmentedSTTService):
    """VAD-segmented STT that sends complete utterances to Eigen ASR.

    Inherits from ``SegmentedSTTService`` so Pipecat's built-in Silero VAD
    buffers audio until a speech pause is detected, then calls ``run_stt``
    with the full utterance as raw PCM bytes.
    """

    def __init__(self, *, sample_rate: int = SAMPLE_RATE, **kwargs):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._sample_rate = sample_rate

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        try:
            wav_bytes = self._pcm_to_wav(audio)
            text = await asyncio.to_thread(
                transcribe_bytes,
                wav_bytes,
                filename="utterance.wav",
                content_type="audio/wav",
            )
            if text and text.strip():
                yield TranscriptionFrame(
                    text=text.strip(),
                    user_id="",
                    timestamp=time_now_iso8601(),
                )
        except Exception as exc:
            yield ErrorFrame(error=f"EigenSTT error: {exc}")

    def _pcm_to_wav(self, pcm_bytes: bytes) -> bytes:
        """Wrap raw PCM-16 LE mono bytes in a WAV header."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()
