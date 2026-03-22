"""Auto-detect running ngrok tunnel URL for the demo stack.

Queries the local ngrok inspection API and prints a shell ``export``
statement for NGROK_URL (API tunnel).  The Pipecat WebSocket stream
is proxied through the FastAPI app at ``/ws/twilio-stream``, so only
one tunnel is needed.

Usage::

    eval $(python scripts/detect_ngrok.py [API_PORT])
"""

from __future__ import annotations

import json
import sys
import urllib.request

NGROK_API = "http://127.0.0.1:4040/api/tunnels"


def detect_tunnel(api_port: int) -> str | None:
    """Return the public HTTPS URL for *api_port* from running ngrok."""
    try:
        with urllib.request.urlopen(NGROK_API, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"Cannot reach ngrok API at {NGROK_API}: {exc}", file=sys.stderr)
        return None

    tunnels: list[dict] = data.get("tunnels", [])

    for t in tunnels:
        public_url: str = t.get("public_url", "")
        addr: str = t.get("config", {}).get("addr", "")
        if not public_url.startswith("https://"):
            continue
        if addr.endswith(f":{api_port}"):
            return public_url

    return None


def main() -> None:
    api_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    url = detect_tunnel(api_port)

    if url is None:
        print(f"WARNING: No ngrok tunnel found for port {api_port}", file=sys.stderr)

    print(f"export NGROK_URL={url or ''}")


if __name__ == "__main__":
    main()
