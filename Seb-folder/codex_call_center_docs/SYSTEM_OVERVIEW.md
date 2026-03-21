# System Overview

## Purpose

This document gives Codex and developers one canonical end-to-end view of how the system should behave.

It should be used as the reference for:
- orchestration flow
- API behavior
- state transitions
- Boson voice integration boundaries
- Eigen document integration boundaries
- action dispatch and escalation behavior

---

## Canonical Architecture

```text
Caller
  ↓
Boson Voice Layer
  ↓
Speech/Text Normalization
  ↓
Intent Router
  ↓
Workflow Registry
  ↓
Dialogue Manager / Workflow Engine
  ↓
Validation Layer
  ↓
Action Dispatcher
  ↓
Backend System or Escalation Service
```

Optional supporting path:

```text
Caller uploads supporting document
  ↓
Eigen Document Adapter
  ↓
Extracted fields + confidence
  ↓
Internal cross-check logic
  ↓
Backend decision or escalation
```

---

## Core Principle

The system must follow:

**detect intent → identify next missing required field → validate → act → escalate if needed**

The LLM is the conversational layer.  
The application is the source of truth.

---

## Main Internal Components

### 1. Intent Router
Responsible for:
- reading the latest caller utterance
- classifying intent
- returning confidence
- identifying unsupported or low-confidence cases

### 2. Workflow Registry
Responsible for:
- loading the correct schema from `src/schemas/`
- exposing required fields, validators, action name, and escalation conditions

### 3. Dialogue Manager / Workflow Engine
Responsible for:
- storing current call state
- determining missing required fields
- choosing the next field to collect
- generating the next system question

### 4. Validation Layer
Responsible for:
- validating a field after it is supplied
- updating retry counts
- deciding whether the value is accepted

### 5. Action Dispatcher
Responsible for:
- calling the correct backend action after all required fields are validated

### 6. Escalation Service
Responsible for:
- deciding whether human handoff is required
- returning a structured escalation reason
- preparing a clean summary for a human agent

### 7. Boson Adapter
Responsible for:
- normalized voice I/O events
- transcript event conversion
- interruption handling integration boundary

### 8. Eigen Adapter
Responsible for:
- document submission
- extracted field retrieval
- returning extraction results in normalized internal format

---

## State Object

The system state should look conceptually like this:

```json
{
  "session_id": "abc123",
  "channel": "voice",
  "intent": "password_reset",
  "confidence": 0.94,
  "collected_fields": {
    "account_id": "12345678"
  },
  "validated_fields": {
    "account_id": "12345678"
  },
  "missing_required_fields": [
    "verification_code"
  ],
  "current_field": "verification_code",
  "last_question": "Please tell me the 6-digit verification code we sent to your phone.",
  "retry_counts": {
    "verification_code": 1
  },
  "escalate": false,
  "escalation_reason": null
}
```

---

## Canonical End-to-End Flow

## Example A: Password Reset Happy Path

### Step 1: Caller speaks
Caller says:

> I can't log into my account.

### Step 2: Intent routing
Input to intent router:

```json
{
  "utterance": "I can't log into my account."
}
```

Expected result:

```json
{
  "intent": "password_reset",
  "confidence": 0.92,
  "reason": null
}
```

### Step 3: Load workflow schema
The application loads:

`src/schemas/password_reset.json`

Expected schema fields:
- required fields: `account_id`, `verification_code`
- action: `reset_password_tool`

### Step 4: Plan next step
Current state:

```json
{
  "session_id": "s1",
  "intent": "password_reset",
  "validated_fields": {}
}
```

Workflow engine output:

```json
{
  "intent": "password_reset",
  "missing_required_fields": [
    "account_id",
    "verification_code"
  ],
  "next_field": "account_id",
  "next_question": "What is your account ID?",
  "escalate": false,
  "escalation_reason": null
}
```

### Step 5: Caller provides field
Caller says:

> 12345678

Normalized field submission:

```json
{
  "field_name": "account_id",
  "value": "12345678"
}
```

Validation result:
- regex passes
- value added to `validated_fields`

Updated state:

```json
{
  "validated_fields": {
    "account_id": "12345678"
  }
}
```

### Step 6: Plan again
Workflow engine output:

```json
{
  "intent": "password_reset",
  "missing_required_fields": [
    "verification_code"
  ],
  "next_field": "verification_code",
  "next_question": "Please tell me the 6-digit verification code we sent to your phone.",
  "escalate": false,
  "escalation_reason": null
}
```

### Step 7: Caller provides verification code
Caller says:

> 123456

Field submission:

```json
{
  "field_name": "verification_code",
  "value": "123456"
}
```

Validation result:
- regex passes
- all required fields complete

### Step 8: Dispatch action
Dispatcher input:

```json
{
  "action": "reset_password_tool",
  "payload": {
    "account_id": "12345678",
    "verification_code": "123456"
  }
}
```

Dispatcher output:

```json
{
  "action": "reset_password_tool",
  "status": "stubbed",
  "payload": {
    "account_id": "12345678",
    "verification_code": "123456"
  }
}
```

### Step 9: Final user-facing response
System response:

> Your password reset request is complete.

---

## Example B: Password Reset Escalation After Repeated Failure

### Situation
Caller repeatedly provides invalid verification codes.

### Progression
- `account_id` is valid
- `verification_code` fails validation 3 times
- `verification_code_failed_attempts >= 3`

Expected escalation result:

```json
{
  "intent": "password_reset",
  "missing_required_fields": [],
  "next_field": null,
  "next_question": null,
  "escalate": true,
  "escalation_reason": "validation_retry_limit"
}
```

Expected handoff summary:

```json
{
  "session_id": "s1",
  "intent": "password_reset",
  "validated_fields": {
    "account_id": "12345678"
  },
  "blocked_field": "verification_code",
  "retry_counts": {
    "verification_code": 3
  },
  "escalation_reason": "validation_retry_limit"
}
```

---

## Example C: Billing Dispute With Document Cross-Check

### Step 1: Caller says
> I need to dispute a charge on my bill.

Intent router output:

```json
{
  "intent": "billing_dispute",
  "confidence": 0.90
}
```

### Step 2: Required fields
From `src/schemas/billing_dispute.json`:
- `account_number`
- `charge_date`
- `charge_amount`
- `dispute_reason`

### Step 3: Collect fields
Caller provides:
- account number
- charge date
- charge amount
- dispute reason

### Step 4: Request document
System asks the caller to upload a bill, statement, or invoice if needed.

### Step 5: Eigen extraction
Eigen adapter result:

```json
{
  "job_id": "eigen-job-1",
  "status": "completed",
  "fields": {
    "charge_date": "2026-03-01",
    "charge_amount": "$95.00"
  },
  "confidence": {
    "charge_date": 0.98,
    "charge_amount": 0.96
  }
}
```

### Step 6: Internal cross-check
System compares:
- caller-provided `charge_date`
- caller-provided `charge_amount`
- Eigen-extracted values

Possible outcomes:
- match → proceed
- mismatch → request clarification or escalate
- low-confidence extraction → request human review

### Step 7: Dispatch or escalate
If all checks pass:

```json
{
  "action": "open_dispute_case",
  "payload": {
    "account_number": "12345678",
    "charge_date": "2026-03-01",
    "charge_amount": "$95.00",
    "dispute_reason": "incorrect_amount"
  }
}
```

If the mismatch is material:

```json
{
  "escalate": true,
  "escalation_reason": "policy_review"
}
```

---

## API Shape Recommendation

A simple MVP API could expose:

### `POST /route-intent`
Input:
```json
{
  "session_id": "s1",
  "utterance": "I can't log into my account."
}
```

Output:
```json
{
  "intent": "password_reset",
  "confidence": 0.92
}
```

### `POST /plan-next-step`
Input:
```json
{
  "session_id": "s1"
}
```

Output:
```json
{
  "next_field": "account_id",
  "next_question": "What is your account ID?",
  "missing_required_fields": ["account_id", "verification_code"],
  "escalate": false
}
```

### `POST /submit-field`
Input:
```json
{
  "session_id": "s1",
  "field_name": "account_id",
  "value": "12345678"
}
```

Output:
```json
{
  "accepted": true,
  "validated_field": "account_id",
  "retry_count": 0
}
```

### `POST /dispatch-action`
Input:
```json
{
  "session_id": "s1"
}
```

Output:
```json
{
  "action": "reset_password_tool",
  "status": "stubbed"
}
```

### `POST /escalation-summary`
Input:
```json
{
  "session_id": "s1"
}
```

Output:
```json
{
  "session_id": "s1",
  "intent": "password_reset",
  "validated_fields": {
    "account_id": "12345678"
  },
  "escalation_reason": "validation_retry_limit"
}
```

---

## Boson Boundary

Boson should only handle:
- audio input/output
- transcript and interruption events
- session-level voice interaction behavior

Boson should not decide:
- required fields
- validation success
- escalation policy
- final business action

---

## Eigen Boundary

Eigen should only handle:
- document extraction or orchestration support
- structured extraction output
- confidence signals

Eigen should not decide:
- whether a workflow is complete
- whether a customer is authorized
- whether a case is approved
- whether a refund or dispute is accepted

---

## Codex Guidance

When implementing new features, Codex should preserve the following invariants:

1. Workflow schemas remain the source of truth.
2. Validated fields are never re-asked unless changed.
3. Prompts do not contain hidden business logic.
4. Boson and Eigen remain thin integration layers.
5. All important state transitions are testable.
6. Escalation reasons remain explicit and structured.

---

## Recommended Next Build Steps

1. Add an application entrypoint
2. Add a session manager
3. Add API routes for route / plan / submit / dispatch / escalate
4. Add structured logging
5. Add escalation summary generation
6. Add more workflow tests
