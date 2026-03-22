"""Entry point: wire the full call center pipeline together."""

import argparse
import logging

from asr.transcribe import transcribe_file
from services.orchestrator import CallCenterService
from services.session_store import InMemorySessionStore


def _build_cli_service() -> CallCenterService:
    return CallCenterService(InMemorySessionStore())


def _quiet_logs() -> None:
    """Suppress structured JSON log lines during interactive CLI sessions."""
    logging.getLogger("call_center").setLevel(logging.WARNING)


def _print_summary(session) -> None:
    fields = dict(session.validated_fields)
    border = "-" * 40

    print(f"\n{border}")
    print("  Session Summary")
    print(border)
    print(f"  Intent:     {session.intent or 'unclassified'}")
    print(f"  Turns:      {session.turn_count}")
    print(f"  Resolved:   {session.resolved}")
    print(f"  Escalated:  {session.escalate}")

    if session.escalation_reason:
        print(f"  Reason:     {session.escalation_reason}")

    if fields:
        print(f"\n  Validated fields:")
        for name, value in fields.items():
            print(f"    {name:20s}  {value}")

    if session.action_result:
        print(f"\n  Action result:")
        print(f"    {session.action_result}")

    print(border)


def run_audio_session(audio_path: str):
    """Full pipeline: audio file -> transcription -> intent -> dialogue loop."""
    _quiet_logs()
    print(f"[ASR] Transcribing {audio_path}...")
    transcript = transcribe_file(audio_path)
    print(f"[ASR] Transcript: {transcript}\n")
    _run_dialogue(transcript, channel="voice")


def run_text_session():
    """Text-only mode for testing without audio."""
    _quiet_logs()
    print("Call Center Agent (text mode)")
    print("Type your issue to begin. Type 'quit' to exit.\n")

    initial = input("Caller: ").strip()
    if not initial:
        return
    _run_dialogue(initial, channel="text")


def _run_dialogue(initial_utterance: str, channel: str):
    """Core dialogue loop shared by audio and text modes."""
    service = _build_cli_service()
    session = service.create_session(channel=channel)
    result = service.handle_user_turn(session.session_id, initial_utterance)
    print(f"Session: {session.session_id}")
    print(f"Agent: {result['message']}\n")

    while not result["resolved"] and not result["escalated"]:
        try:
            user_input = input("Caller: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Session ended]")
            break

        if user_input.lower() in ("quit", "exit"):
            print("[Session ended by caller]")
            break

        result = service.handle_user_turn(session.session_id, user_input)
        print(f"Agent: {result['message']}\n")

    _print_summary(service.get_session(session.session_id))


def run_api_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Start the FastAPI HTTP server via uvicorn."""
    import uvicorn
    uvicorn.run("api.app:app", host=host, port=port, reload=reload)


def main():
    parser = argparse.ArgumentParser(description="LLM-Driven Call Center Agent")
    parser.add_argument("audio", nargs="?", help="Path to audio file")
    parser.add_argument("--text", action="store_true", help="Run in text-only mode")
    parser.add_argument("--api", action="store_true", help="Start the HTTP API server")
    parser.add_argument("--host", default="0.0.0.0", help="API server bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    if args.api:
        run_api_server(host=args.host, port=args.port, reload=args.reload)
    elif args.text or not args.audio:
        run_text_session()
    else:
        run_audio_session(args.audio)


if __name__ == "__main__":
    main()
