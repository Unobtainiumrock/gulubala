"""Entry point: wire the full call center pipeline together."""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
import uuid
import webbrowser
from typing import Any

from asr.transcribe import transcribe_file
from services.orchestrator import CallCenterService
from services.session_store import InMemorySessionStore


def _build_cli_service() -> CallCenterService:
    return CallCenterService(InMemorySessionStore())


def _quiet_logs() -> None:
    """Suppress structured JSON log lines during interactive CLI sessions."""
    logging.getLogger("call_center").setLevel(logging.WARNING)


def _print_summary(session: Any) -> None:
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


def run_audio_session(audio_path: str) -> None:
    """Full pipeline: audio file -> transcription -> intent -> dialogue loop."""
    _quiet_logs()
    print(f"[ASR] Transcribing {audio_path}...")
    transcript = transcribe_file(audio_path)
    print(f"[ASR] Transcript: {transcript}\n")
    _run_dialogue(transcript, channel="voice")


def run_text_session() -> None:
    """Text-only mode for testing without audio."""
    _quiet_logs()
    print("Call Center Agent (text mode)")
    print("Type your issue to begin. Type 'quit' to exit.\n")

    initial = input("Caller: ").strip()
    if not initial:
        return
    _run_dialogue(initial, channel="text")


def _run_dialogue(initial_utterance: str, channel: str) -> None:
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


def run_api_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False) -> None:
    """Start the FastAPI HTTP server via uvicorn."""
    import uvicorn
    uvicorn.run("api.app:app", host=host, port=port, reload=reload)


# ---------------------------------------------------------------------------
# Demo mode
# ---------------------------------------------------------------------------

_DEMO_FIELD_DEFAULTS: dict[str, dict[str, str]] = {
    "password_reset": {
        "account_number": "12345678",
        "verification_code": "123456",
    },
    "cancel_service": {
        "account_number": "12345678",
        "cancellation_reason": "consolidating vendors",
        "confirm_cancel": "yes",
    },
}


def _wait_for_server(base: str, *, timeout: float = 30.0) -> bool:
    """Poll /health until the API is up or *timeout* seconds elapse."""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base}/health", timeout=2)
            if r.status_code == 200:
                return True
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(0.5)
    return False


def _subscribe_ws_events(ws_url: str) -> None:
    """Connect to the global dashboard WS and print events to the terminal."""
    try:
        from websockets.sync.client import connect
    except ImportError:
        return

    def _listen() -> None:
        try:
            with connect(ws_url) as ws:
                for raw in ws:
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    _print_ws_event(evt)
        except Exception:
            pass

    t = threading.Thread(target=_listen, daemon=True)
    t.start()


def _print_ws_event(evt: dict[str, Any]) -> None:
    etype = evt.get("event_type", "")
    sid = evt.get("session_id", "")[:12]
    if etype == "transcript":
        role = evt.get("role", "?")
        text = evt.get("content", "")
        tag = "IVR" if role == "user" else "Agent"
        print(f"  [{tag}] {text}")
    elif etype == "escalation":
        print(f"  [ESCALATION] {evt.get('reason', '')}  (session {sid})")
    elif etype == "completed":
        print(f"  [COMPLETED] {evt.get('action_result', 'done')}  (session {sid})")
    elif etype == "bridge_active":
        print(f"  [BRIDGE] Conference {evt.get('conference_name', '')} active")


def run_demo(
    host: str = "0.0.0.0",
    port: int = 8000,
    scenario: str = "password_reset",
    tree_id: str = "acme_corp",
) -> None:
    """Launch the full demo stack: API + dashboard + outbound call."""
    import uvicorn

    from config.models import (
        PIPELINE_STREAM_URL,
        TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN,
        TWILIO_IVR_NUMBER,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
    logger = logging.getLogger("demo")

    base_url = f"http://127.0.0.1:{port}"
    dashboard_url = f"{base_url}/dashboard"

    # 1. Start uvicorn in a background thread
    uvi_cfg = uvicorn.Config("api.app:app", host=host, port=port, log_level="warning")
    server = uvicorn.Server(uvi_cfg)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # 2. Wait for the API to be ready
    logger.info("Waiting for API server on port %d ...", port)
    if not _wait_for_server(base_url):
        logger.error("API server did not start within 30 s. Aborting.")
        return

    logger.info("API server ready.")

    # 3. Open the dashboard
    webbrowser.open(dashboard_url)
    logger.info("Dashboard: %s", dashboard_url)

    # 4. Subscribe to WS events for terminal output
    ws_proto = "ws"
    _subscribe_ws_events(f"{ws_proto}://127.0.0.1:{port}/ws")

    # 5. Check Twilio + pipeline stream prerequisites
    twilio_ready = all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_IVR_NUMBER])
    stream_ready = bool(PIPELINE_STREAM_URL)

    if not twilio_ready:
        logger.warning(
            "Twilio not configured (TWILIO_ACCOUNT_SID / AUTH_TOKEN / IVR_NUMBER). "
            "Dashboard is live -- trigger calls manually or set credentials and restart."
        )
    elif not stream_ready:
        logger.warning(
            "PIPELINE_STREAM_URL not set. Start a second ngrok tunnel for port 8765 "
            "and set PIPELINE_STREAM_URL=wss://<tunnel>.ngrok-free.app in .env"
        )
    else:
        # 6. Initiate the outbound call
        session_id = uuid.uuid4().hex
        available_fields = _DEMO_FIELD_DEFAULTS.get(scenario, {})
        task_desc = f"Demo scenario '{scenario}' with fields: {available_fields}"

        logger.info("Initiating outbound call for scenario '%s' ...", scenario)
        logger.info("  session_id: %s", session_id)
        logger.info("  tree: %s", tree_id)
        logger.info("  fields: %s", available_fields)

        from telephony.twilio_client import initiate_stream_call

        call_sid = initiate_stream_call(
            to=TWILIO_IVR_NUMBER,
            stream_url=PIPELINE_STREAM_URL,
        )
        logger.info("Twilio call placed: CallSid=%s", call_sid)
        logger.info("Waiting for Twilio Media Stream to connect to pipeline ...")

        # 7. Run the Pipecat pipeline (blocks until call ends)
        from calltree.pipeline import run_agent_pipeline_sync

        run_agent_pipeline_sync(
            stream_sid="pending",
            call_sid=call_sid,
            session_id=session_id,
            tree_id=tree_id,
            task_description=task_desc,
            available_fields=available_fields,
        )
        logger.info("Pipeline finished.")

    # 8. Block until Ctrl+C (server stays up for dashboard inspection)
    if not (twilio_ready and stream_ready):
        logger.info("Server running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down.")
        server.should_exit = True


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-Driven Call Center Agent")
    parser.add_argument("audio", nargs="?", help="Path to audio file")
    parser.add_argument("--text", action="store_true", help="Run in text-only mode")
    parser.add_argument("--api", action="store_true", help="Start the HTTP API server")
    parser.add_argument("--demo", action="store_true", help="Launch full demo (API + dashboard + outbound call)")
    parser.add_argument("--scenario", default="password_reset", help="Demo scenario (default: password_reset)")
    parser.add_argument("--tree", default="acme_corp", help="Call tree schema (default: acme_corp)")
    parser.add_argument("--host", default="0.0.0.0", help="API server bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    if args.demo:
        run_demo(host=args.host, port=args.port, scenario=args.scenario, tree_id=args.tree)
    elif args.api:
        run_api_server(host=args.host, port=args.port, reload=args.reload)
    elif args.text or not args.audio:
        run_text_session()
    else:
        run_audio_session(args.audio)


if __name__ == "__main__":
    main()
