"""Twilio-compatible IVR routes."""

from __future__ import annotations

from urllib.parse import parse_qs
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, HTTPException, Request, Response

from calltree.models import CallTreeNode
from calltree.registry import get_call_tree, get_call_tree_node
from ivr.agent import cleanup_call, process_agent_turn, start_agent_session

router = APIRouter(prefix="/ivr", tags=["ivr"])


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
        },
    )
    if prefix_prompt:
        _add_say(gather, prefix_prompt)
    _add_say(gather, node.prompt)
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
    return _xml_response(root)


def _build_redirect_response(url: str) -> Response:
    root = _response_root()
    redirect = SubElement(root, "Redirect", {"method": "POST"})
    redirect.text = url
    return _xml_response(root)


def _get_service(request: Request):
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
    body = (await request.body()).decode()
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


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
    result = start_agent_session(call_sid, node.id, service)
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
    result = process_agent_turn(call_sid, utterance, service)
    if result["resolved"] or result["escalated"]:
        return _build_terminal_response(result["message"])
    return _build_speech_response([result["message"]], f"/ivr/agent-turn?node_id={node_id}")


@router.post("/status-callback")
async def status_callback(request: Request) -> Response:
    form = await _read_twilio_form(request)
    call_sid = str(form.get("CallSid", "")).strip()
    _call_status = str(form.get("CallStatus", "")).strip()
    if call_sid:
        cleanup_call(call_sid)
    return _xml_response(_response_root())
