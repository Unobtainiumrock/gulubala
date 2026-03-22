"""Pipecat pipeline assembly for the outbound IVR navigation agent.

Creates a bidirectional audio pipeline that connects to a Twilio call
via Media Streams and drives the ``IvrNavigatorProcessor`` to
autonomously navigate an IVR phone tree.

Pipeline topology::

    Twilio audio in
        -> TwilioFrameSerializer (mu-law decode)
        -> WebsocketServerTransport input
        -> EigenSTTService or ScriptedIvrSttProcessor (demo: timed transcripts)
        -> IvrNavigatorProcessor (classify IVR prompt, decide action)
        -> EigenTTSService (text-to-speech via Higgs Audio V2.5)
        -> WebsocketServerTransport output
        -> TwilioFrameSerializer (mu-law encode)
    Twilio audio out
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.transports.websocket.server import (
    WebsocketServerParams,
    WebsocketServerTransport,
)

from calltree.demo_ivr_scripts import get_demo_ivr_script
from calltree.navigator import IvrNavigatorProcessor
from calltree.scripted_ivr_stt import ScriptedIvrSttProcessor
from config.models import (
    DEMO_FORCE_HUMAN_FLOWS,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
)
from pipecat_services.eigen_stt import EigenSTTService
from pipecat_services.eigen_tts import EigenTTSService

logger = logging.getLogger("call_center.pipeline")

PIPELINE_WS_HOST = os.environ.get("PIPELINE_WS_HOST", "0.0.0.0")
PIPELINE_WS_PORT = int(os.environ.get("PIPELINE_WS_PORT", "8765"))


def build_transport(
    stream_sid: str,
    call_sid: str,
) -> WebsocketServerTransport:
    """Create a WebSocket transport wired to a Twilio Media Stream."""
    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=TWILIO_ACCOUNT_SID,
        auth_token=TWILIO_AUTH_TOKEN,
    )
    return WebsocketServerTransport(
        host=PIPELINE_WS_HOST,
        port=PIPELINE_WS_PORT,
        params=WebsocketServerParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=serializer,
        ),
    )


def build_pipeline(
    transport: WebsocketServerTransport,
    *,
    session_id: str,
    call_sid: str | None = None,
    tree_id: str = "acme_corp",
    task_description: str = "",
    available_fields: dict[str, str] | None = None,
    scripted_ivr_scenario: str | None = None,
    demo_force_human_flows: bool | None = None,
) -> Pipeline:
    """Assemble the full Pipecat pipeline for IVR navigation.

    If *scripted_ivr_scenario* is set (e.g. ``\"cancel_service\"``), inbound audio
    is ignored and timed ``TranscriptionFrame``s are injected so the demo
    matches the Acme tree without a real IVR on the callee leg.
    """
    ready_event: asyncio.Event | None = None
    if scripted_ivr_scenario:
        ready_event = asyncio.Event()
        stt: EigenSTTService | ScriptedIvrSttProcessor = ScriptedIvrSttProcessor(
            get_demo_ivr_script(scripted_ivr_scenario),
            ready_event=ready_event,
        )
    else:
        stt = EigenSTTService()
    tts = EigenTTSService()
    if demo_force_human_flows is None:
        demo_force_human_flows = bool(
            scripted_ivr_scenario == "cancel_service" and DEMO_FORCE_HUMAN_FLOWS
        )
    navigator = IvrNavigatorProcessor(
        session_id=session_id,
        tree_id=tree_id,
        task_description=task_description,
        available_fields=available_fields,
        twilio_call_sid=call_sid,
        ready_event=ready_event,
        demo_force_human_flows=demo_force_human_flows,
    )

    return Pipeline([
        transport.input(),
        stt,
        navigator,
        tts,
        transport.output(),
    ])


async def run_agent_pipeline(
    *,
    stream_sid: str,
    call_sid: str,
    session_id: str,
    tree_id: str = "acme_corp",
    task_description: str = "",
    available_fields: dict[str, str] | None = None,
    scripted_ivr_scenario: str | None = None,
    demo_force_human_flows: bool | None = None,
) -> None:
    """Build and run the full agent pipeline until the call ends.

    This is the top-level entry point that the demo orchestrator calls
    after initiating an outbound Twilio call.  It blocks until the
    pipeline finishes (call hangup or escalation).
    """
    transport = build_transport(stream_sid, call_sid)
    pipeline = build_pipeline(
        transport,
        session_id=session_id,
        call_sid=call_sid,
        tree_id=tree_id,
        task_description=task_description,
        available_fields=available_fields,
        scripted_ivr_scenario=scripted_ivr_scenario,
        demo_force_human_flows=demo_force_human_flows,
    )

    task = PipelineTask(pipeline)
    runner = PipelineRunner(handle_sigint=False)

    logger.info(
        "Starting agent pipeline session=%s call=%s stream=%s",
        session_id, call_sid, stream_sid,
    )
    await runner.run(task)
    logger.info("Agent pipeline finished session=%s", session_id)


def run_agent_pipeline_sync(
    *,
    stream_sid: str,
    call_sid: str,
    session_id: str,
    tree_id: str = "acme_corp",
    task_description: str = "",
    available_fields: dict[str, str] | None = None,
    scripted_ivr_scenario: str | None = None,
    demo_force_human_flows: bool | None = None,
) -> None:
    """Synchronous wrapper for ``run_agent_pipeline``.

    Useful for launching from a thread or subprocess.
    """
    asyncio.run(run_agent_pipeline(
        stream_sid=stream_sid,
        call_sid=call_sid,
        session_id=session_id,
        tree_id=tree_id,
        task_description=task_description,
        available_fields=available_fields,
        scripted_ivr_scenario=scripted_ivr_scenario,
        demo_force_human_flows=demo_force_human_flows,
    ))
