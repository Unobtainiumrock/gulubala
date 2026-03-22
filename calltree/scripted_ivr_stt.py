"""STT stand-in: pushes scripted IVR transcripts on a timer (demo / rehearsal)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pipecat.frames.frames import AudioRawFrame, Frame, StartFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.time import time_now_iso8601

logger = logging.getLogger(__name__)


class ScriptedIvrSttProcessor(FrameProcessor):
    """Swallows inbound audio and emits ``TranscriptionFrame`` lines from a script.

    Use instead of ``EigenSTTService`` when the callee does not supply usable IVR
    audio (common with outbound ``<Connect><Stream>`` calls).
    """

    def __init__(
        self,
        lines: list[tuple[float, str]],
        *,
        ready_event: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._lines = lines
        self._script_task: asyncio.Task[None] | None = None
        self._script_started = False
        self._ready_for_next = ready_event or asyncio.Event()
        self._ready_for_next.set()  # first line fires immediately

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, StartFrame):
            await self.push_frame(frame, direction)
            if not self._script_started:
                self._script_started = True
                self._script_task = self.create_task(self._play_script(), name="demo_ivr_script")
            return

        if isinstance(frame, AudioRawFrame):
            return

        await self.push_frame(frame, direction)

    async def _play_script(self) -> None:
        try:
            for delay, text in self._lines:
                await self._ready_for_next.wait()
                self._ready_for_next.clear()
                await asyncio.sleep(delay)
                logger.info("Scripted IVR: %s", text[:80] + ("..." if len(text) > 80 else ""))
                await self.push_frame(
                    TranscriptionFrame(
                        text=text,
                        user_id="",
                        timestamp=time_now_iso8601(),
                    ),
                    FrameDirection.DOWNSTREAM,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scripted IVR task failed")
