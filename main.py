"""Entry point: wire the full call center pipeline together."""

import argparse
import sys

from asr.transcribe import transcribe_file
from intents.router import classify_intent
from workflows.registry import get_workflow
from dialogue.manager import DialogueState


def run_audio_session(audio_path: str):
    """Full pipeline: audio file → transcription → intent → dialogue loop."""
    print(f"[ASR] Transcribing {audio_path}...")
    transcript = transcribe_file(audio_path)
    print(f"[ASR] Transcript: {transcript}\n")
    _run_dialogue(transcript)


def run_text_session():
    """Text-only mode for testing without audio."""
    print("Call Center Agent (text mode)")
    print("Type your issue to begin. Type 'quit' to exit.\n")

    initial = input("Caller: ").strip()
    if not initial:
        return
    _run_dialogue(initial)


def _run_dialogue(initial_utterance: str):
    """Core dialogue loop shared by audio and text modes."""
    # Step 1: Classify intent
    print("[Intent] Classifying...")
    intent_result = classify_intent(initial_utterance)
    intent = intent_result["intent"]
    confidence = intent_result.get("confidence", 0)
    print(f"[Intent] {intent} (confidence: {confidence:.2f})")

    if intent_result.get("escalate"):
        print(f"[Escalate] {intent_result.get('reason', 'Low confidence or unsupported intent')}")
        print("Transferring to human agent...")
        return

    # Step 2: Load workflow
    workflow = get_workflow(intent)
    if not workflow:
        print(f"[Error] No workflow found for intent '{intent}'")
        return

    # Step 3: Initialize dialogue state
    state = DialogueState(intent, workflow)
    print(f"[Workflow] Loaded: {intent} — {len(workflow['required_fields'])} required fields\n")

    # First turn: process the initial utterance (may contain field values)
    response = state.next_turn(initial_utterance)
    print(f"Agent: {response}\n")

    # Step 4: Dialogue loop
    while not state.resolved and not state.escalated:
        try:
            user_input = input("Caller: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Session ended]")
            break

        if user_input.lower() in ("quit", "exit"):
            print("[Session ended by caller]")
            break

        response = state.next_turn(user_input)
        print(f"Agent: {response}\n")

    # Summary
    print("\n--- Session Summary ---")
    print(f"Intent: {state.intent}")
    print(f"Turns: {state.turn_count}")
    print(f"Fields collected: {state.collected_fields}")
    print(f"Resolved: {state.resolved}")
    print(f"Escalated: {state.escalated}")
    if state.escalation_reason:
        print(f"Escalation reason: {state.escalation_reason}")


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
