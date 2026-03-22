"""Twilio-compatible IVR routes."""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException, Request, Response

from calltree.models import CallTreeNode
from calltree.registry import get_call_tree, get_call_tree_node
from ivr.agent import cleanup_call, process_agent_turn, start_agent_session
from services.orchestrator import CallCenterService
from telephony.presenter_gather import resolve_gather

router = APIRouter(prefix="/ivr", tags=["ivr"])

_TERMINAL_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled", "cancelled"}


def _xml_response(root: Element) -> Response:
    return Response(content=tostring(root, encoding="unicode"), media_type="application/xml")


def _response_root() -> Element:
    return Element("Response")


def _add_say(parent: Element, text: str) -> None:
    child = SubElement(parent, "Say")
    child.text = text


def _build_menu_response(node: CallTreeNode, action_url: str, prefix_prompt: str | None = None) -> Response:
    root = _response_root()
    gather = SubElement(
        root,
        "Gather",
        {
            "action": action_url,
            "method": "POST",
            "numDigits": "1",
            "timeout": "10",
        },
    )
    if prefix_prompt:
        _add_say(gather, prefix_prompt)
    _add_say(gather, node.prompt)
    redirect = SubElement(root, "Redirect", {"method": "POST"})
    redirect.text = action_url
    return _xml_response(root)


def _build_speech_response(messages: list[str], action_url: str) -> Response:
    root = _response_root()
    gather = SubElement(
        root,
        "Gather",
        {
            "action": action_url,
            "method": "POST",
            "input": "speech",
        },
    )
    for message in messages:
        _add_say(gather, message)
    return _xml_response(root)


def _build_terminal_response(message: str) -> Response:
    root = _response_root()
    _add_say(root, message)
    SubElement(root, "Hangup")
    return _xml_response(root)


def _build_redirect_response(url: str) -> Response:
    root = _response_root()
    redirect = SubElement(root, "Redirect", {"method": "POST"})
    redirect.text = url
    return _xml_response(root)


def _get_service(request: Request) -> CallCenterService:
    get_service = getattr(request.app.state, "get_service", None)
    if get_service is None:
        raise HTTPException(status_code=500, detail="IVR service is not configured")
    return get_service()


def _require_node(node_id: str) -> CallTreeNode:
    node = get_call_tree_node("acme_corp", node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Unknown IVR node '{node_id}'")
    return node


async def _read_twilio_form(request: Request) -> dict[str, str]:
    form = await request.form()
    return {key: str(value) for key, value in form.items()}


@router.post("/incoming")
async def incoming() -> Response:
    tree = get_call_tree("acme_corp")
    if tree is None:
        raise HTTPException(status_code=404, detail="Missing IVR tree 'acme_corp'")

    root_node = tree.get_node(tree.root_node_id)
    if root_node is None:
        raise HTTPException(status_code=404, detail=f"Unknown IVR node '{tree.root_node_id}'")
    return _build_menu_response(root_node, f"/ivr/menu?node_id={root_node.id}")


@router.post("/menu")
async def menu(request: Request, node_id: str) -> Response:
    node = _require_node(node_id)
    if node.input_type != "dtmf":
        raise HTTPException(status_code=400, detail=f"IVR node '{node_id}' is not a menu node")

    form = await _read_twilio_form(request)
    digits = str(form.get("Digits", "")).strip()
    if not digits:
        return _build_menu_response(node, f"/ivr/menu?node_id={node.id}")

    transition = next((item for item in node.transitions if item.input == digits), None)
    if transition is None:
        invalid_prompt = node.invalid_input_prompt or "Sorry, that was not a valid selection."
        return _build_menu_response(node, f"/ivr/menu?node_id={node.id}", prefix_prompt=invalid_prompt)

    next_node = _require_node(transition.next_node_id)
    if next_node.input_type == "speech":
        return _build_redirect_response(f"/ivr/agent-greeting?node_id={next_node.id}")
    return _build_menu_response(next_node, f"/ivr/menu?node_id={next_node.id}")


@router.post("/agent-greeting")
async def agent_greeting(request: Request, node_id: str) -> Response:
    node = _require_node(node_id)
    form = await _read_twilio_form(request)
    call_sid = str(form.get("CallSid", "")).strip()
    if not call_sid:
        raise HTTPException(status_code=400, detail="Missing CallSid")

    service = _get_service(request)
    try:
        result = start_agent_session(call_sid, node.id, service)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_speech_response(
        [node.prompt, result["message"]],
        f"/ivr/agent-turn?node_id={node.id}",
    )


@router.post("/agent-turn")
async def agent_turn(request: Request, node_id: str) -> Response:
    _require_node(node_id)
    form = await _read_twilio_form(request)
    call_sid = str(form.get("CallSid", "")).strip()
    if not call_sid:
        raise HTTPException(status_code=400, detail="Missing CallSid")

    utterance = str(form.get("SpeechResult", "")).strip()
    if not utterance:
        return _build_speech_response(
            ["I did not catch that. Please say that again."],
            f"/ivr/agent-turn?node_id={node_id}",
        )

    service = _get_service(request)
    try:
        result = process_agent_turn(call_sid, utterance, service)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if result["resolved"] or result["escalated"]:
        return _build_terminal_response(result["message"])
    return _build_speech_response([result["message"]], f"/ivr/agent-turn?node_id={node_id}")


@router.post("/presenter-gather/{session_id}/{field_name}")
async def presenter_gather(
    request: Request,
    session_id: str,
    field_name: str,
) -> Response:
    """Twilio ``<Gather>`` callback — delivers the presenter's spoken answer."""
    form = await _read_twilio_form(request)
    speech = str(form.get("SpeechResult", "")).strip()

    root = _response_root()
    if speech:
        resolve_gather(session_id, field_name, speech)
        _add_say(root, f"Got it. Passing that back to the agent. Thank you.")
    else:
        _add_say(root, "No response detected. The agent will try another approach.")
    SubElement(root, "Hangup")
    return _xml_response(root)


@router.post("/status-callback")
async def status_callback(request: Request) -> Response:
    form = await _read_twilio_form(request)
    call_sid = str(form.get("CallSid", "")).strip()
    call_status = str(form.get("CallStatus", "")).strip().lower()
    if call_sid and call_status in _TERMINAL_STATUSES:
        cleanup_call(call_sid)
    return _xml_response(_response_root())
