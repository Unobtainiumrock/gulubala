"""Pipecat processor: conversational retention agent for demo escalation.

Replaces the static conference bridge with an LLM-driven voice agent that
role-plays as "Alex from Acme retention" and has a natural conversation
with the presenter (human) using full call context.
"""

from __future__ import annotations

import asyncio
import logging

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from client.eigen import chat_completion
from config.models import GPT_OSS_MODEL

logger = logging.getLogger("call_center.retention_agent")

_SYSTEM_PROMPT_TEMPLATE = """\
You are Alex, a friendly retention specialist at Acme Corp.  A customer is \
trying to cancel their subscription and your job is to have a natural \
conversation to understand their concerns and try to retain them.

CONTEXT (from the automated call so far):
- Account number: {account_number}
- Cancellation reason: {cancellation_reason}
- Validated fields: {validated_fields}

GUIDELINES:
- Be warm, conversational, and empathetic — not pushy or scripted.
- Acknowledge the customer's reason for canceling.
- Offer concrete retention incentives (discount, upgrade, pause, etc.).
- If the customer insists, accept gracefully and confirm the cancellation.
- Keep responses SHORT (1-3 sentences max) — this is a phone call, not an essay.
- Do NOT use markdown, bullet points, or special formatting.
- Speak naturally as if on a phone call.

Start by greeting the customer and acknowledging their situation.\
"""


class RetentionAgentProcessor(FrameProcessor):
    """LLM-driven conversational agent for the retention demo beat.

    Receives ``TranscriptionFrame`` from ASR (what the presenter said),
    sends the text to the LLM, and pushes a ``TextFrame`` for TTS.
    """

    def __init__(
        self,
        *,
        account_number: str = "unknown",
        cancellation_reason: str = "not provided",
        validated_fields: dict[str, str] | None = None,
        model: str = GPT_OSS_MODEL,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._model = model
        self._fields = validated_fields or {}

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            account_number=account_number,
            cancellation_reason=cancellation_reason,
            validated_fields=self._fields,
        )
        self._messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        self._greeting_sent = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if not text:
                return

            logger.info("Presenter said: %s", text)
            self._messages.append({"role": "user", "content": text})

            reply = await self._get_reply()
            logger.info("Alex replies: %s", reply)
            self._messages.append({"role": "assistant", "content": reply})

            await self.push_frame(TextFrame(text=reply))
        else:
            # Pass through all other frames (audio, control, etc.)
            await self.push_frame(frame, direction)

    async def send_greeting(self) -> None:
        """Generate and push the opening greeting."""
        if self._greeting_sent:
            return
        self._greeting_sent = True

        self._messages.append({
            "role": "user",
            "content": "(The customer has just been connected to you. Greet them.)",
        })
        reply = await self._get_reply()
        logger.info("Alex greeting: %s", reply)
        self._messages.append({"role": "assistant", "content": reply})
        await self.push_frame(TextFrame(text=reply))

    async def _get_reply(self) -> str:
        try:
            return await asyncio.to_thread(
                chat_completion,
                model=self._model,
                messages=self._messages,
                temperature=0.7,
                max_tokens=256,
            )
        except Exception:
            logger.exception("Retention LLM call failed")
            return "I'm sorry, could you repeat that?"
