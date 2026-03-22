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
import threading
from typing import Any

from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import (
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
from calltree.transcript_store import record_transcript_turn
from contracts.events import (
    BridgeActiveEvent,
    CompletedEvent,
    EscalationEvent,
    InfoGatheredEvent,
    InfoRequestedEvent,
    IvrCallTreePositionEvent,
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
from telephony.presenter_gather import cancel_gather, create_gather_future
from telephony.presenter_notify import (
    call_presenter_for_info,
    notify_completion,
    notify_escalation,
    transcript_url_for_session,
)

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
        self.transcript_turn_seq = 0

    def next_transcript_turn(self) -> int:
        self.transcript_turn_seq += 1
        return self.transcript_turn_seq

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
        twilio_call_sid: str | None = None,
        model: str = GPT_OSS_MODEL,
        ready_event: asyncio.Event | None = None,
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
        self._twilio_call_sid = twilio_call_sid
        self._dashboard = get_manager()
        self._ready_event = ready_event
        self._initial_position_sent = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not self._initial_position_sent:
            self._initial_position_sent = True
            self._emit_calltree_position()

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        # ScriptedIvrSttProcessor waits on this event after each line; always set
        # on any TranscriptionFrame outcome (empty text, already resolved, errors).
        ready = self._ready_event
        try:
            transcript_text = frame.text.strip()
            if not transcript_text:
                return

            if self._state.resolved or self._state.escalated:
                logger.debug(
                    "Ignoring IVR frame — session already %s",
                    "resolved" if self._state.resolved else "escalated",
                )
                return

            self._state.transcript.append({"role": "ivr", "content": transcript_text})
            record_transcript_turn(self._state.session_id, "ivr", transcript_text)
            self._emit_event(TranscriptEvent(
                session_id=self._state.session_id,
                role="user",
                content=transcript_text,
                turn_count=self._state.next_transcript_turn(),
            ))

            logger.info("IVR said: %s", transcript_text)

            classification = await self._classify(transcript_text)
            action = await self._decide(classification)

            await self._execute(action)
            self._emit_calltree_position()
        finally:
            if ready is not None:
                ready.set()

    async def _classify(self, transcript: str) -> IvrClassificationResponse:
        raw = ""
        try:
            raw = await asyncio.to_thread(
                chat_completion,
                model=self._model,
                messages=[
                    {"role": "system", "content": IVR_CLASSIFICATION_SYSTEM},
                    {"role": "user", "content": transcript},
                ],
                temperature=0,
                max_tokens=512,
            )
            return parse_contract(raw, IvrClassificationResponse)
        except Exception:
            logger.exception("LLM classification failed (raw=%s); falling back to 'error'", raw[:200] if raw else "N/A")
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
        raw = ""
        try:
            raw = await asyncio.to_thread(
                chat_completion,
                model=self._model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "What should I do next?"},
                ],
                temperature=0,
                max_tokens=512,
            )
            return parse_contract(raw, IvrActionResponse)
        except Exception:
            logger.exception("LLM action decision failed (raw=%s); falling back to 'wait'", raw[:200] if raw else "N/A")
            return IvrActionResponse(
                action="wait",
                reasoning="Failed to get LLM action response",
            )

    async def _execute(self, action: IvrActionResponse) -> None:
        logger.info("Navigator action: %s (reason: %s)", action.action, action.reasoning)

        if action.action == "send_dtmf" and action.dtmf_digits:
            await self._send_dtmf(action.dtmf_digits)
        elif action.action == "speak" and action.speech_text:
            await self._speak(action.speech_text)
        elif action.action == "request_info" and action.requested_field:
            await self._request_info(
                action.requested_field,
                action.field_prompt or f"What is your {action.requested_field}?",
            )
        elif action.action == "escalate":
            await self._escalate(action.escalation_reason or "Agent requested help")
        elif action.action == "complete":
            self.mark_completed(action.completion_summary)
        # "wait" → do nothing, let the next IVR prompt come in

    async def _send_dtmf(self, digits: str) -> None:
        dtmf_line = f"[DTMF: {digits}]"
        self._state.transcript.append({"role": "agent", "content": dtmf_line})
        record_transcript_turn(self._state.session_id, "agent", dtmf_line)
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="assistant",
            content=dtmf_line,
            turn_count=self._state.next_transcript_turn(),
        ))

        node = self._state.current_node
        if node:
            for transition in node.transitions:
                if transition.input == digits:
                    self._state.move_to(transition.next_node_id)
                    break

        for digit in digits:
            keypad = _DIGIT_TO_KEYPAD.get(digit)
            if keypad:
                await self.push_frame(OutputDTMFFrame(button=keypad))

    async def _speak(self, text: str) -> None:
        self._state.transcript.append({"role": "agent", "content": text})
        record_transcript_turn(self._state.session_id, "agent", text)
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="assistant",
            content=text,
            turn_count=self._state.next_transcript_turn(),
        ))
        await self.push_frame(TextFrame(text=text))

    async def _request_info(self, field_name: str, field_prompt: str) -> None:
        """Soft escalation: call the presenter to gather a missing field value.

        The IVR call stays on hold (navigator pauses) while we place a
        side-call to the presenter with ``<Gather input="speech">``.
        When the Twilio webhook fires, the future resolves and we resume.
        """
        from config.models import PUBLIC_API_BASE_URL

        callback_base = PUBLIC_API_BASE_URL
        if not callback_base:
            logger.error("PUBLIC_API_BASE_URL not set; cannot call presenter for info")
            return

        self._emit_event(InfoRequestedEvent(
            session_id=self._state.session_id,
            field_name=field_name,
            field_prompt=field_prompt,
        ))
        note = f"[INFO REQUEST: asking presenter for '{field_name}']"
        self._state.transcript.append({"role": "agent", "content": note})
        record_transcript_turn(self._state.session_id, "agent", note)
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="assistant",
            content=note,
            turn_count=self._state.next_transcript_turn(),
        ))

        logger.info("Requesting info field=%s from presenter", field_name)

        loop = asyncio.get_running_loop()
        future = create_gather_future(self._state.session_id, field_name, loop)

        # Resolve the workflow intent for a contextual presenter prompt.
        node = self._state.current_node
        intent = node.intent if node and node.intent else None

        await asyncio.to_thread(
            call_presenter_for_info,
            session_id=self._state.session_id,
            field_name=field_name,
            field_prompt=field_prompt,
            callback_base_url=callback_base,
            intent=intent,
        )

        try:
            value = await asyncio.wait_for(future, timeout=60.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            logger.warning("Presenter did not provide '%s' in time", field_name)
            cancel_gather(self._state.session_id, field_name)
            return

        self._state.available_fields[field_name] = value
        logger.info("Received field=%s value=%s from presenter", field_name, value[:40])

        self._emit_event(InfoGatheredEvent(
            session_id=self._state.session_id,
            field_name=field_name,
            value=value,
        ))
        gathered = f"[INFO GATHERED: {field_name} = {value}]"
        self._state.transcript.append({"role": "agent", "content": gathered})
        record_transcript_turn(self._state.session_id, "agent", gathered)
        self._emit_event(TranscriptEvent(
            session_id=self._state.session_id,
            role="assistant",
            content=gathered,
            turn_count=self._state.next_transcript_turn(),
        ))

        await self._speak(value)

    async def _escalate(self, reason: str) -> None:
        self._state.escalated = True
        self._emit_event(EscalationEvent(
            session_id=self._state.session_id,
            reason=reason,
            intent=self._state.current_node.intent if self._state.current_node else None,
            validated_fields=self._state.available_fields,
        ))
        logger.warning("Navigator escalating: %s", reason)

        bridge = await asyncio.to_thread(
            notify_escalation,
            session_id=self._state.session_id,
            reason=reason,
            validated_fields=dict(self._state.available_fields),
            twilio_call_sid=self._twilio_call_sid,
        )
        if bridge is not None:
            # Conference bridge is active — the IVR call has been moved out
            # of the Pipecat media stream, so TTS would go nowhere.
            self._emit_event(BridgeActiveEvent(
                session_id=self._state.session_id,
                conference_name=bridge.conference_name,
                presenter_call_sid=bridge.presenter_call_sid,
            ))
        else:
            # No bridge (no active call SID) — pipeline is still live,
            # so speak into the IVR to buy time while the presenter is notified.
            await self.push_frame(
                TextFrame(text=f"I need help from a human. {reason}")
            )

    def mark_completed(
        self,
        action_result: str | None = None,
        *,
        notify_presenter: bool = True,
    ) -> None:
        """Called externally when the task finishes (action dispatched)."""
        self._state.resolved = True
        url = transcript_url_for_session(self._state.session_id)
        self._emit_event(CompletedEvent(
            session_id=self._state.session_id,
            intent=self._state.current_node.intent if self._state.current_node else None,
            action_result=action_result,
            validated_fields=self._state.available_fields,
            transcript_url=url,
        ))
        if notify_presenter:
            sid = self._state.session_id
            fields = dict(self._state.available_fields)

            def _notify() -> None:
                notify_completion(
                    session_id=sid,
                    summary=action_result,
                    validated_fields=fields,
                )

            threading.Thread(target=_notify, daemon=True).start()

    def _emit_calltree_position(self) -> None:
        node = self._state.current_node
        self._emit_event(
            IvrCallTreePositionEvent(
                session_id=self._state.session_id,
                node_id=self._state.current_node_id,
                label=node.label if node else None,
            )
        )

    def _emit_event(self, event: Any) -> None:
        self._dashboard.publish_sync(event)
