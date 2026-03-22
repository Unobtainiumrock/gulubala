# LLM Call Center Agent

Python call-center agent with a local CLI, a FastAPI server, and Boson-compatible voice event handling. The project uses Eigen AI for chat, ASR, and optional TTS.

## What It Does

- Runs text conversations from the terminal
- Accepts audio files, transcribes them with Eigen ASR, and continues the dialogue in the CLI
- Exposes an HTTP API for workflow routing, field capture, action dispatch, and document submission
- Accepts Boson-style voice events on `/voice-event`

Supported workflows include:

- `password_reset`
- `billing_dispute`
- `order_status`
- `update_profile`
- `cancel_service`

## Requirements

- Python 3.10+
- An Eigen AI API key

## Environment Setup

Copy the example file and add your Eigen credentials:

```bash
cp .env.example .env
```

Required values:

```env
EIGEN_API_KEY=your-api-key-here
EIGEN_BASE_URL=https://api-web.eigenai.com/api/v1
```

Optional values you can add to `.env`:

```env
EIGEN_GENERATE_URL=https://api-web.eigenai.com/api/v1/generate
HIGGS_ASR_MODEL=higgs_asr_3
HIGGS_CHAT_MODEL=gpt-oss-120b
HIGGS_TTS_MODEL=higgs2p5
ASR_LANGUAGE=English
SESSION_DB_PATH=call_center_sessions.sqlite3
DEMO_BRAND_NAME=Callit-Dev
DEMO_TTS_VOICE=Linda
```

Notes:

- `EIGEN_API_KEY` is required for chat, ASR, document extraction, and TTS calls.
- `SESSION_DB_PATH` controls where the API server stores session state.
- `DEMO_TTS_VOICE` and `HIGGS_TTS_MODEL` matter if you use the TTS helpers in [`audio/tts.py`](audio/tts.py).

## Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run the CLI

Text mode:

```bash
python main.py --text
```

`python main.py` also defaults to text mode when no audio file is provided.

Audio mode:

```bash
python main.py path/to/audio.wav
```

The CLI will:

1. Upload the audio file to Eigen ASR
2. Print the transcript
3. Continue the workflow in interactive voice-mode dialogue

## Run the API Server

Using the built-in entry point:

```bash
python main.py --api --reload
```

Or directly with Uvicorn:

```bash
uvicorn api.app:app --reload
```

By default the server starts on `http://127.0.0.1:8000` and exposes docs at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`

You can change the bind address and port:

```bash
python main.py --api --host 0.0.0.0 --port 8000
```

## Run With Voice / Boson

Start the API server first, then send Boson-compatible events to `/voice-event`.

Basic transcript event:

```bash
curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d '{
    "type": "transcript",
    "session_id": "voice-demo-1",
    "text": "I need to reset my password"
  }'
```

Follow up with DTMF input:

```bash
curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d '{
    "type": "dtmf",
    "session_id": "voice-demo-1",
    "digits": "12345678"
  }'
```

Supported Boson-style event types:

- `transcript` or `user_transcript`
- `dtmf`
- `interrupt` or `barge_in`
- `assistant_output` or `tts`

The payload may use either `session_id` or `call_id`.

Voice responses now include a `voice_response` envelope alongside the plain `message`. That envelope contains:

- `spoken_text`: TTS-normalized text
- `ssml`: light SSML with pacing hints
- `boson`: a Boson-ready `assistant_output` payload with `text`, `ssml`, and `voice`

The voice envelope is derived deterministically from the canonical `message`. It does not run a second free-form LLM rewrite step, and if the voice formatter fails the system falls back to the original message text.

### Voice Event With Raw Audio

If you send base64 audio as `audio_data` on a transcript event, the API runs ASR before routing the utterance:

```bash
AUDIO_BASE64=$(base64 < path/to/audio.wav | tr -d '\n')

curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d "{
    \"type\": \"transcript\",
    \"session_id\": \"voice-audio-1\",
    \"audio_data\": \"${AUDIO_BASE64}\"
  }"
```

### Guided Voice Demo

You can also run a seeded demo flow over the API:

```bash
curl -X POST http://127.0.0.1:8000/demo/start \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "password_reset",
    "channel": "voice"
  }'
```

Then send an audio turn to `/demo/voice-turn`:

```bash
curl -X POST http://127.0.0.1:8000/demo/voice-turn \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "replace-with-session-id",
    "audio_base64": "replace-with-base64-audio",
    "filename": "recording.webm",
    "content_type": "audio/webm"
  }'
```

## Backend Action Contract

Teammates replacing stub actions in [`actions/backend.py`](actions/backend.py) should follow this drop-in contract:

```python
# Example runtime shape. Use the specific TypedDict for your action when available.
def action_name(fields: dict[str, str]) -> str:
    ...
```

Rules:

- `fields` is the normalized `session.validated_fields` mapping after workflow validation has already passed.
- The function must stay synchronous and accept exactly one positional `fields` argument.
- The return value must be a caller-safe plain string. It is shown directly in the CLI, API, and voice channel.
- For compatibility with the current demo and tests, successful actions should begin with a stable status phrase:
  - `Password reset initiated`
  - `Dispute case opened`
  - `Profile updated`
  - `Service cancelled`
- To signal failure, either raise an exception or return a string that starts with `Error:`.

Key input shapes:

- `reset_password(fields) -> str`
  Required keys: `account_id`, `verification_code`
  Optional keys: `callback_number`

- `cancel_subscription(fields) -> str`
  Required keys: `account_number`, `cancellation_reason`, `confirm_cancel`
  `confirm_cancel` arrives normalized as `yes` or `no`

The source file also defines per-action `TypedDict` contracts for all backend actions so replacements can use the exact expected shape.

## Demo Walkthrough

Use this section for a live demo from a clean terminal. The steps below exercise the main flows without requiring anyone to inspect the codebase.

### 1. Start the API and verify health

```bash
python main.py --api --reload
```

In a second terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected result:

- JSON response with `{"status":"ok"}`

### 2. Demo a password reset over the HTTP API

Route the intent:

```bash
curl -X POST http://127.0.0.1:8000/route-intent \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-password-1",
    "utterance": "I need to reset my password"
  }'
```

Submit the required fields:

```bash
curl -X POST http://127.0.0.1:8000/submit-field \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-password-1",
    "field_name": "account_id",
    "value": "12345678"
  }'

curl -X POST http://127.0.0.1:8000/submit-field \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-password-1",
    "field_name": "verification_code",
    "value": "654321"
  }'
```

Dispatch the backend action:

```bash
curl -X POST http://127.0.0.1:8000/dispatch-action \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-password-1"
  }'
```

Expected result:

- `status` is `completed`
- `result` begins with `Password reset initiated`

### 3. Demo a billing dispute over the HTTP API

```bash
curl -X POST http://127.0.0.1:8000/route-intent \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-dispute-1",
    "utterance": "I want to dispute a charge on my account"
  }'

curl -X POST http://127.0.0.1:8000/submit-field \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-dispute-1",
    "field_name": "account_number",
    "value": "12345678"
  }'

curl -X POST http://127.0.0.1:8000/submit-field \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-dispute-1",
    "field_name": "charge_date",
    "value": "03/01/2026"
  }'

curl -X POST http://127.0.0.1:8000/submit-field \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-dispute-1",
    "field_name": "charge_amount",
    "value": "$95.00"
  }'

curl -X POST http://127.0.0.1:8000/submit-field \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-dispute-1",
    "field_name": "dispute_reason",
    "value": "duplicate charge"
  }'

curl -X POST http://127.0.0.1:8000/dispatch-action \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "demo-dispute-1"
  }'
```

Expected result:

- `status` is `completed`
- `result` begins with `Dispute case opened`
- the response includes a deterministic `Case ID`

### 4. Demo the voice event path on `/voice-event`

Send a transcript event:

```bash
curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d '{
    "type": "transcript",
    "session_id": "voice-demo-2",
    "text": "I need to reset my password"
  }'
```

Follow with DTMF input:

```bash
curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d '{
    "type": "dtmf",
    "session_id": "voice-demo-2",
    "digits": "12345678"
  }'
```

Expected result:

- responses include both `message` and `voice_response`
- `voice_response` contains `spoken_text`, `ssml`, and a Boson-ready `assistant_output` payload

### 5. Demo escalation / human handoff

Start a voice interaction, then ask for a human:

```bash
curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d '{
    "type": "transcript",
    "session_id": "voice-escalation-1",
    "text": "I need to reset my password"
  }'

curl -X POST http://127.0.0.1:8000/voice-event \
  -H "Content-Type: application/json" \
  -d '{
    "type": "transcript",
    "session_id": "voice-escalation-1",
    "text": "let me speak to a human"
  }'
```

Expected result:

- `escalated` becomes `true`
- the returned `message` includes a human handoff summary

### 6. Optional seeded demo endpoints

List available demo scenarios:

```bash
curl http://127.0.0.1:8000/demo/scenarios
```

Start a seeded voice demo:

```bash
curl -X POST http://127.0.0.1:8000/demo/start \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": "password_reset",
    "channel": "voice"
  }'
```

Use `/demo/voice-turn` if you want to drive the seeded scenario with recorded audio instead of plain transcript events.

## Useful Files

- [`actions/backend.py`](actions/backend.py): backend action signatures, field shapes, and failure contract
- [`main.py`](main.py): CLI and API entry point
- [`api/app.py`](api/app.py): FastAPI routes
- [`config/models.py`](config/models.py): environment-backed settings
- [`boson/adapter.py`](boson/adapter.py): Boson event normalization
