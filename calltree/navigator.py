"""Pipecat processor that navigates an IVR call tree on behalf of a caller.

Sits in the pipeline between STT and TTS.  Receives ``TranscriptionFrame``
from the STT service (what the IVR just said), uses the LLM to classify the
prompt and decide the next action (DTMF or speech), then pushes the
appropriate frame downstream (``OutputDTMFFrame`` or ``TextFrame``).

Also tracks the agent's position in the call tree and emits dashboard
events so the visual frontend can display real-time progress.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    OutputDTMFFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from calltree.models import CallTreeNode, CallTreeSchema
from calltree.registry import get_call_tree
from client.eigen import chat_completion
from config.models import GPT_OSS_MODEL
from contracts.events import (
    CompletedEvent,
    EscalationEvent,
    NodeEnteredEvent,
    TranscriptEvent,
)
from contracts.prompts import (
    IvrActionResponse,
    IvrClassificationResponse,
    build_ivr_action_prompt,
    build_ivr_classification_prompt,
    parse_contract,
)
from dashboard.ws import get_manager

logger = logging.getLogger("call_center.navigator")

_DIGIT_TO_KEYPAD: dict[str, KeypadEntry] = {entry.value: entry for entry in KeypadEntry}

IVR_CLASSIFICATION_SYSTEM = build_ivr_classification_prompt()


class NavigatorState:
    """Mutable per-session state for the navigator."""

    def __init__(
        self,
        session_id: str,
        tree: CallTreeSchema,
        task_description: str,
        available_fields: dict[str, str],
    ):
        self.session_id = session_id
        self.tree = tree
        self.current_node_id = tree.root_node_id
        self.task_description = task_description
        self.available_fields = dict(available_fields)
        self.transcript: list[dict[str, str]] = []
        self.resolved = False
        self.escalated = False

    @property
    def current_node(self) -> CallTreeNode | None:
        return self.tree.get_node(self.current_node_id)

    def move_to(self, node_id: str) -> CallTreeNode | None:
        node = self.tree.get_node(node_id)
        if node is not None:
            self.current_node_id = node_id
        return node


class IvrNavigatorProcessor(FrameProcessor):
    """Pipeline processor that drives an outbound agent through an IVR.

    Constructor args:
        session_id: Unique session identifier (used for dashboard events).
        tree_id: Call tree schema to load (default ``acme_corp``).
        task_description: Human-readable description of what the agent
            is trying to accomplish (e.g. "Reset password for account
            12345678 using verification code 654321").
        available_fields: Pre-collected field values the agent can
            provide when the IVR asks for information.
        model: LLM model identifier for classification / action prompts.
    """

    def __init__(
        self,
        *,
        session_id: str,
        tree_id: str = "acme_corp",
        task_description: str = "",
        available_fields: dict[str, str] | None = None,
        model: str = GPT_OSS_MODEL,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        tree = get_call_tree(tree_id)
        if tree is None:
            raise ValueError(f"Unknown call tree '{tree_id}'")
        self._state = NavigatorState(
            session_id=session_id,
            tree=tree,
            task_description=task_description,
            available_fields=available_fields or {},
        )
        self._model = model
        self._dashboard = get_manager()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        transcript_text = frame.text.strip()
        if not transcript_text:
            return

        self._state.transcript.append({"role": "ivr", "content": transcript_text})
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="user",
            content=transcript_text,
        ))

        logger.info("IVR said: %s", transcript_text)

        classification = await self._classify(transcript_text)
        action = await self._decide(classification)

        await self._execute(action)

    async def _classify(self, transcript: str) -> IvrClassificationResponse:
        raw = await asyncio.to_thread(
            chat_completion,
            model=self._model,
            messages=[
                {"role": "system", "content": IVR_CLASSIFICATION_SYSTEM},
                {"role": "user", "content": transcript},
            ],
            temperature=0.1,
            max_tokens=256,
        )
        try:
            return parse_contract(raw, IvrClassificationResponse)
        except Exception:
            return IvrClassificationResponse(
                category="error",
                confidence=0.0,
                transcript_snippet=transcript[:100],
            )

    async def _decide(self, classification: IvrClassificationResponse) -> IvrActionResponse:
        menu_options: dict[str, str] | None = None
        node = self._state.current_node
        if node and node.transitions:
            menu_options = {
                t.input: t.label or t.next_node_id for t in node.transitions
            }
        if classification.options:
            menu_options = classification.options

        prompt = build_ivr_action_prompt(
            task_description=self._state.task_description,
            current_node_id=self._state.current_node_id,
            classification_category=classification.category,
            available_fields=self._state.available_fields,
            menu_options=menu_options,
            recent_transcript=self._state.transcript[-6:],
        )
        raw = await asyncio.to_thread(
            chat_completion,
            model=self._model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "What should I do next?"},
            ],
            temperature=0.1,
            max_tokens=256,
        )
        try:
            return parse_contract(raw, IvrActionResponse)
        except Exception:
            return IvrActionResponse(
                action="wait",
                reasoning="Failed to parse LLM action response",
            )

    async def _execute(self, action: IvrActionResponse) -> None:
        logger.info("Navigator action: %s (reason: %s)", action.action, action.reasoning)

        if action.action == "send_dtmf" and action.dtmf_digits:
            await self._send_dtmf(action.dtmf_digits)
        elif action.action == "speak" and action.speech_text:
            await self._speak(action.speech_text)
        elif action.action == "escalate":
            await self._escalate(action.escalation_reason or "Agent requested help")
        # "wait" → do nothing, let the next IVR prompt come in

    async def _send_dtmf(self, digits: str) -> None:
        self._state.transcript.append({"role": "agent", "content": f"[DTMF: {digits}]"})
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="assistant",
            content=f"[DTMF: {digits}]",
        ))

        node = self._state.current_node
        if node:
            for transition in node.transitions:
                if transition.input == digits:
                    next_node = self._state.move_to(transition.next_node_id)
                    if next_node:
                        self._emit_event(NodeEnteredEvent(
                            session_id=self._state.session_id,
                            node_fields=[next_node.id],
                            intent=next_node.intent,
                        ))
                    break

        for digit in digits:
            keypad = _DIGIT_TO_KEYPAD.get(digit)
            if keypad:
                await self.push_frame(OutputDTMFFrame(button=keypad))

    async def _speak(self, text: str) -> None:
        self._state.transcript.append({"role": "agent", "content": text})
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="assistant",
            content=text,
        ))
        await self.push_frame(TextFrame(text=text))

    async def _escalate(self, reason: str) -> None:
        self._state.escalated = True
        self._emit_event(EscalationEvent(
            session_id=self._state.session_id,
            reason=reason,
            intent=self._state.current_node.intent if self._state.current_node else None,
            validated_fields=self._state.available_fields,
        ))
        logger.warning("Navigator escalating: %s", reason)
        await self.push_frame(
            TextFrame(text=f"I need help from a human. {reason}")
        )

    def mark_completed(self, action_result: str | None = None) -> None:
        """Called externally when the task finishes (action dispatched)."""
        self._state.resolved = True
        self._emit_event(CompletedEvent(
            session_id=self._state.session_id,
            intent=self._state.current_node.intent if self._state.current_node else None,
            action_result=action_result,
            validated_fields=self._state.available_fields,
        ))

    def _emit_event(self, event: Any) -> None:
        self._dashboard.publish_sync(event)
