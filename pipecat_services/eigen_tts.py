"""Pipecat TTS service wrapping Eigen's Higgs TTS generate endpoint."""

from __future__ import annotations

import asyncio
import io
import wave
from typing import AsyncGenerator

import numpy as np
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings, is_given
from pipecat.services.tts_service import TTSService

try:
    from pipecat.utils.tracing.service_decorators import traced_tts
except ImportError:  # pragma: no cover - older pipecat

    def traced_tts(fn):
        return fn

from audio.tts import synthesize_speech
from config.models import DEMO_TTS_VOICE, HIGGS_TTS_MODEL, SAMPLE_RATE


def _wav_bytes_to_pcm_mono(wav_bytes: bytes) -> tuple[bytes, int]:
    """Return raw PCM16 mono bytes and sample rate from WAV data."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        rate = wf.getframerate()
        nch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sampwidth != 2:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth}")
    arr = np.frombuffer(frames, dtype=np.int16)
    if nch > 1:
        arr = arr.reshape(-1, nch).mean(axis=1).astype(np.int16)
    if rate == SAMPLE_RATE:
        return arr.tobytes(), SAMPLE_RATE
    # Linear resample to pipeline / Twilio 8 kHz μ-law path (16 kHz PCM before serializer).
    x_old = np.linspace(0.0, 1.0, len(arr), endpoint=False)
    n_new = int(round(len(arr) * SAMPLE_RATE / rate))
    x_new = np.linspace(0.0, 1.0, n_new, endpoint=False)
    resampled = np.interp(x_new, x_old, arr.astype(np.float64))
    return resampled.astype(np.int16).tobytes(), SAMPLE_RATE


class EigenTTSService(TTSService):
    """Eigen generate-backed TTS for Pipecat pipelines."""

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        voice: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        settings = TTSSettings(
            model=model or HIGGS_TTS_MODEL,
            voice=voice or DEMO_TTS_VOICE,
            language=None,
        )
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            settings=settings,
            **kwargs,
        )

    def can_generate_metrics(self) -> bool:
        return False

    @traced_tts
    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        """Synthesize WAV via Eigen, then yield PCM16 frames at ``sample_rate``."""

        voice = DEMO_TTS_VOICE
        if is_given(self._settings.voice) and self._settings.voice:
            voice = str(self._settings.voice)

        try:
            wav_bytes = await asyncio.to_thread(
                synthesize_speech,
                text,
                voice,
            )
            pcm, rate = await asyncio.to_thread(_wav_bytes_to_pcm_mono, wav_bytes)
        except Exception as exc:
            yield ErrorFrame(error=f"Eigen TTS error: {exc}")
            return

        chunk_size = self.chunk_size
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i : i + chunk_size]
            if not chunk:
                continue
            yield TTSAudioRawFrame(chunk, rate, 1, context_id=context_id)
