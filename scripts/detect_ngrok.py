"""Auto-detect running ngrok tunnel URLs for the demo stack.

Queries the local ngrok inspection API and prints shell ``export``
statements for NGROK_URL (API tunnel) and PIPELINE_STREAM_URL
(Pipecat WebSocket stream tunnel).

Usage::

    eval $(python scripts/detect_ngrok.py [API_PORT] [WS_PORT])
"""

from __future__ import annotations

import json
import sys
import urllib.request

NGROK_API = "http://127.0.0.1:4040/api/tunnels"


def detect_tunnels(api_port: int, ws_port: int) -> dict[str, str]:
    """Return ``{NGROK_URL: ..., PIPELINE_STREAM_URL: ...}`` from running ngrok."""
    try:
        with urllib.request.urlopen(NGROK_API, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"Cannot reach ngrok API at {NGROK_API}: {exc}", file=sys.stderr)
        return {}

    tunnels: list[dict] = data.get("tunnels", [])
    result: dict[str, str] = {}

    for t in tunnels:
        public_url: str = t.get("public_url", "")
        addr: str = t.get("config", {}).get("addr", "")
        if not public_url.startswith("https://"):
            continue
        if addr.endswith(f":{api_port}"):
            result["NGROK_URL"] = public_url
        elif addr.endswith(f":{ws_port}"):
            # Twilio <Stream> needs wss://
            result["PIPELINE_STREAM_URL"] = public_url.replace(
                "https://", "wss://", 1,
            )

    return result


def main() -> None:
    api_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    ws_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765

    urls = detect_tunnels(api_port, ws_port)

    if "NGROK_URL" not in urls:
        print(f"WARNING: No ngrok tunnel found for port {api_port}", file=sys.stderr)
    if "PIPELINE_STREAM_URL" not in urls:
        print(f"WARNING: No ngrok tunnel found for port {ws_port}", file=sys.stderr)

    for key in ("NGROK_URL", "PIPELINE_STREAM_URL"):
        print(f"export {key}={urls.get(key, '')}")


if __name__ == "__main__":
    main()
