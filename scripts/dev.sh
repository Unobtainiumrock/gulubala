#!/usr/bin/env bash
# Launch ngrok + uvicorn in one command.
# Twilio webhook auto-syncs on FastAPI startup via the lifespan hook.
#
# Usage:  ./scripts/dev.sh [port]
#   port  defaults to 8000

set -euo pipefail

PORT="${1:-8000}"
NGROK_PID=""
cleanup() {
    if [ -n "$NGROK_PID" ] && kill -0 "$NGROK_PID" 2>/dev/null; then
        echo "[dev] stopping ngrok (pid $NGROK_PID)..."
        kill "$NGROK_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo "[dev] starting ngrok on port $PORT..."
ngrok http "$PORT" --log=stdout --log-level=warn &
NGROK_PID=$!

echo "[dev] waiting for ngrok tunnel..."
for i in $(seq 1 15); do
    URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
        | python3 -c "import sys,json; ts=json.load(sys.stdin).get('tunnels',[]); print(next((t['public_url'] for t in ts if t['public_url'].startswith('https://')), ''))" 2>/dev/null)
    if [ -n "$URL" ]; then
        echo "[dev] ngrok ready: $URL"
        break
    fi
    sleep 1
done

if [ -z "$URL" ]; then
    echo "[dev] WARNING: ngrok tunnel not detected after 15s. Twilio sync may fail."
fi

echo "[dev] starting uvicorn on 0.0.0.0:$PORT..."
exec uvicorn api.app:app --host 0.0.0.0 --port "$PORT"
