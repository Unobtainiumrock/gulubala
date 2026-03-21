# Architecture

## Overview
```text
Caller
  ↓
Boson Voice Layer
  ↓
Speech/Text Normalization
  ↓
Intent Router
  ↓
Workflow Registry + Dialogue Manager
  ↓
Validation Layer
  ↓
Action Dispatcher / Escalation Service
  ↓
Backend Systems
```

Optional side paths:
- Eigen document processing
- analytics and QA logging
- human agent handoff

## Key state object
```json
{
  "session_id": "abc123",
  "channel": "voice",
  "intent": "password_reset",
  "confidence": 0.94,
  "collected_fields": {},
  "validated_fields": {},
  "missing_required_fields": [],
  "current_field": null,
  "last_question": null,
  "retry_counts": {},
  "escalate": false,
  "escalation_reason": null
}
```
