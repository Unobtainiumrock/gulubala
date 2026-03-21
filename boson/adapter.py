"""Thin Boson adapter that normalizes external voice events."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedVoiceEvent(BaseModel):
    session_id: str
    channel: Literal["voice"] = "voice"
    event_type: Literal["transcript", "dtmf", "interrupt", "assistant_output"]
    utterance: str | None = None
    digits: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BosonAdapter:
    """Convert provider-specific Boson payloads into internal event contracts."""

    def normalize_event(self, event: dict[str, Any]) -> NormalizedVoiceEvent:
        event_type = event.get("type")
        session_id = event.get("session_id") or event.get("call_id")
        if not session_id:
            raise ValueError("Boson event missing session_id/call_id")

        if event_type in {"transcript", "user_transcript"}:
            return NormalizedVoiceEvent(
                session_id=session_id,
                event_type="transcript",
                utterance=event.get("text") or event.get("utterance") or "",
                metadata={k: v for k, v in event.items() if k not in {"type", "session_id", "call_id", "text", "utterance"}},
            )
        if event_type == "dtmf":
            return NormalizedVoiceEvent(
                session_id=session_id,
                event_type="dtmf",
                digits=event.get("digits") or "",
                metadata={k: v for k, v in event.items() if k not in {"type", "session_id", "call_id", "digits"}},
            )
        if event_type in {"interrupt", "barge_in"}:
            return NormalizedVoiceEvent(
                session_id=session_id,
                event_type="interrupt",
                metadata={k: v for k, v in event.items() if k not in {"type", "session_id", "call_id"}},
            )
        if event_type in {"assistant_output", "tts"}:
            return NormalizedVoiceEvent(
                session_id=session_id,
                event_type="assistant_output",
                utterance=event.get("text") or "",
                metadata={k: v for k, v in event.items() if k not in {"type", "session_id", "call_id", "text"}},
            )
        raise ValueError(f"Unsupported Boson event type: {event_type}")

    def build_assistant_output(self, session_id: str, text: str, **metadata: Any) -> NormalizedVoiceEvent:
        return NormalizedVoiceEvent(
            session_id=session_id,
            event_type="assistant_output",
            utterance=text,
            metadata=metadata,
        )
