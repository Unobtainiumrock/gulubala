"""Pipecat TTS service wrapping Eigen's Higgs Audio V2.5 endpoint."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from pipecat.frames.frames import Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.services.tts_service import TTSService

from audio.tts import synthesize_speech
from config.models import DEMO_TTS_VOICE, SAMPLE_RATE


class EigenTTSService(TTSService):
    """TTS service that delegates to Eigen Higgs Audio V2.5.

    Calls the existing ``synthesize_speech()`` helper from ``audio/tts.py``
    in a thread so it doesn't block the async pipeline.
    """

    def __init__(
        self,
        *,
        voice: str = DEMO_TTS_VOICE,
        sample_rate: int = SAMPLE_RATE,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._voice = voice
        self._sample_rate = sample_rate

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        yield TTSStartedFrame()
        try:
            audio_bytes: bytes = await asyncio.to_thread(
                synthesize_speech, text, self._voice,
            )
            yield TTSAudioRawFrame(
                audio=audio_bytes,
                sample_rate=self._sample_rate,
                num_channels=1,
            )
        except Exception:
            pass
        yield TTSStoppedFrame()
