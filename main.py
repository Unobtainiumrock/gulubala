"""Entry point: wire the full call center pipeline together."""

import argparse

from asr.transcribe import transcribe_file
from services.orchestrator import CallCenterService
from services.session_store import InMemorySessionStore


def _build_cli_service() -> CallCenterService:
    return CallCenterService(InMemorySessionStore())


def run_audio_session(audio_path: str):
    """Full pipeline: audio file → transcription → intent → dialogue loop."""
    print(f"[ASR] Transcribing {audio_path}...")
    transcript = transcribe_file(audio_path)
    print(f"[ASR] Transcript: {transcript}\n")
    _run_dialogue(transcript, channel="voice")


def run_text_session():
    """Text-only mode for testing without audio."""
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

    # Summary
    final_state = service.get_session(session.session_id)
    print("\n--- Session Summary ---")
    print(f"Intent: {final_state.intent}")
    print(f"Turns: {final_state.turn_count}")
    print(f"Fields validated: {final_state.validated_fields}")
    print(f"Resolved: {final_state.resolved}")
    print(f"Escalated: {final_state.escalate}")
    if final_state.escalation_reason:
        print(f"Escalation reason: {final_state.escalation_reason}")
    if final_state.action_result:
        print(f"Action result: {final_state.action_result}")


def main():
    parser = argparse.ArgumentParser(description="LLM-Driven Call Center Agent")
    parser.add_argument("audio", nargs="?", help="Path to audio file")
    parser.add_argument("--text", action="store_true", help="Run in text-only mode")
    args = parser.parse_args()

    if args.text or not args.audio:
        run_text_session()
    else:
        run_audio_session(args.audio)


if __name__ == "__main__":
    main()
