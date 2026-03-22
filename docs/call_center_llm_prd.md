# Product Requirements Document (PRD)
## LLM-Driven Call Center Intake and Resolution Agent

### Document Status
Draft

### Owner
Seb S.

### Last Updated
March 20, 2026

---

## 1. Purpose

Build an LLM-driven call center agent that resolves customer issues with minimal human involvement by collecting only the information required for a specific call, validating that information, and triggering the correct backend action or escalation path.

The system should reduce unnecessary questioning, minimize average handling time, improve first-contact resolution, and safely escalate only when needed.

---

## 2. Problem Statement

Traditional call center flows are often inefficient because they:
- ask irrelevant or repetitive questions,
- collect too much information up front,
- rely on rigid IVR trees that frustrate users,
- hand off to humans even when an issue could have been resolved automatically,
- allow inconsistency in information collection across different issue types.

A purely free-form LLM approach is also risky because it may:
- forget required information,
- ask unnecessary questions,
- skip validation,
- hallucinate business rules,
- behave inconsistently across calls.

The product therefore needs a structured, deterministic framework where the LLM handles conversation while the application enforces workflow logic.

---

## 3. Product Vision

Create a call center agent that behaves like an intelligent intake specialist:
- understands the caller’s goal,
- identifies the correct workflow,
- asks only for the next missing required piece of information,
- validates answers in real time,
- completes the correct backend action when possible,
- escalates only when necessary.

The LLM should act as a conversational layer, not the source of truth for business logic.

---

## 4. Goals

### Primary Goals
- Reduce human involvement in routine call center interactions.
- Collect all required information for a call with high precision.
- Minimize the number of turns needed to complete a workflow.
- Improve consistency across intents and agents.
- Ensure safe and deterministic execution of backend actions.

### Secondary Goals
- Support voice and text channels.
- Improve customer satisfaction by reducing friction.
- Create reusable workflow templates for new call types.
- Generate structured logs for analytics and optimization.

---

## 5. Non-Goals

The initial version will not:
- allow the LLM to invent business policies,
- let the LLM independently determine eligibility or authorization rules,
- support completely open-ended troubleshooting without workflow structure,
- replace all human agents for high-risk or emotionally sensitive cases,
- serve as a general chatbot outside defined service workflows.

---

## 6. Users

### Primary Users
- Customers contacting a support or service center
- Operations teams managing call automation
- Product and engineering teams configuring workflows

### Secondary Users
- Compliance and QA teams reviewing interactions
- Analysts measuring workflow performance
- Human agents receiving escalations

---

## 7. Key Use Cases

### Example Use Cases
1. Password reset
2. Billing dispute
3. Update address or profile
4. Cancel service
5. Order status inquiry
6. Technical troubleshooting intake
7. Identity verification and account recovery

---

## 8. Core Product Principle

The system must follow:

**intent → required fields → validation → action**

For every call:
1. Detect likely intent.
2. Load the workflow schema for that intent.
3. Identify required fields.
4. Ask for the next missing required field only.
5. Validate the response.
6. Repeat until complete.
7. Trigger the correct tool or backend action.
8. Escalate if necessary.

---

## 9. Product Requirements

### 9.1 Intent Detection
The system must:
- classify the caller’s issue into one supported workflow,
- return an intent label and confidence score,
- support ambiguity handling when multiple intents are plausible,
- escalate when confidence is too low or unsupported intent is detected.

#### Output
- `intent`
- `confidence`
- `needs_disambiguation`
- `escalate`
- `reason`

---

### 9.2 Workflow Registry
The application must maintain a workflow registry that defines, for each intent:
- required fields,
- optional fields,
- validators,
- field priority,
- escalation conditions,
- action to trigger upon completion.

#### Example
```json
{
  "intent": "billing_dispute",
  "required_fields": [
    "account_number",
    "charge_date",
    "charge_amount",
    "dispute_reason"
  ],
  "optional_fields": [
    "merchant_name",
    "reference_number"
  ],
  "validators": {
    "account_number": "^[0-9]{8,12}$",
    "charge_amount": "^\\$?[0-9]+(\\.[0-9]{2})?$"
  },
  "action": "open_dispute_case"
}
```

---

### 9.3 Dialogue Manager
The system must keep a persistent conversation state including:
- current intent,
- collected fields,
- validated fields,
- missing required fields,
- failed validation attempts,
- last question asked,
- escalation status.

The dialogue manager must ensure the agent:
- never asks for information already collected and validated,
- never skips required fields,
- never asks optional questions before required ones are complete unless explicitly allowed by the workflow.

---

### 9.4 Ask-Next-Missing-Field Logic
The system must ask only the highest-priority missing required field at each step unless the workflow explicitly permits bundling fields.

#### Requirement
For each turn, the system should output:
- `known_fields`
- `missing_required_fields`
- `next_field`
- `next_question`

#### Example
```json
{
  "intent": "reset_password",
  "known_fields": {
    "account_id": "12345678",
    "full_name": null,
    "verification_code": null,
    "callback_number": "408-555-1212"
  },
  "missing_required_fields": [
    "full_name",
    "verification_code"
  ],
  "next_field": "verification_code",
  "next_question": "Please tell me the verification code we sent to your phone."
}
```

---

### 9.5 Field Validation
Each required field must support validation logic such as:
- regex validation,
- type checking,
- enumerated values,
- backend lookups,
- cross-field validation,
- retry limits.

When validation fails, the system must:
- briefly explain the issue,
- re-ask for that same field,
- avoid resetting other collected information.

#### Example
- “That account number should be 8 to 12 digits. Please say or enter it again.”

---

### 9.6 Structured Output
The LLM must always return machine-readable structured output for orchestration.

Minimum structured output:
- `intent`
- `confidence`
- `collected_fields`
- `missing_required_fields`
- `next_question`
- `escalate`
- `escalation_reason`

This output must be schema-validated before the system acts on it.

---

### 9.7 Backend Action Layer
The LLM must not directly execute business logic. Instead, the application must trigger tools or APIs once all required fields are present and valid.

Examples:
- `reset_password_tool`
- `open_dispute_case`
- `cancel_subscription`
- `lookup_order_status`

The backend layer remains the source of truth for:
- eligibility,
- verification success,
- policy decisions,
- case outcomes.

---

### 9.8 Escalation Rules
The system must escalate when:
- the user requests a human,
- intent confidence is below threshold,
- verification fails after retry limits,
- workflow is unsupported,
- backend action fails,
- the conversation stalls or loops,
- the issue falls into a restricted category.

Escalation output must include:
- escalation reason,
- current collected data,
- conversation summary,
- recommended next step for the human agent.

---

### 9.9 Voice and IVR Compatibility
For voice channels, the system should support:
- ASR-friendly prompts,
- DTMF fallback for structured inputs,
- concise field questions,
- re-prompts and examples,
- confirmation strategies only where necessary.

Fields particularly suited for DTMF:
- account number,
- ZIP code,
- PIN,
- verification code,
- menu options.

---

## 10. Functional Requirements

### FR1: Intent Routing
The system shall classify a caller utterance into a supported workflow intent.

### FR2: Schema Retrieval
The system shall load a workflow schema based on the current intent.

### FR3: Missing Field Detection
The system shall compare collected fields against required fields and identify the next missing required field.

### FR4: Single-Question Prompting
The system shall ask one targeted question at a time unless workflow rules allow grouping.

### FR5: Validation
The system shall validate field values before marking them complete.

### FR6: State Persistence
The system shall persist state across turns within a call session.

### FR7: Structured Output
The system shall return schema-valid JSON or equivalent structured format.

### FR8: Backend Invocation
The system shall invoke the appropriate backend action when required fields are complete and valid.

### FR9: Escalation
The system shall escalate based on configured rules.

### FR10: Logging
The system shall log intent, fields collected, validation failures, escalation triggers, and final disposition.

---

## 11. Non-Functional Requirements

### Reliability
- The workflow must behave deterministically across repeated similar inputs.
- Structured outputs must validate successfully before actions are taken.

### Precision
- The agent should ask only relevant questions for the active workflow.
- Hallucinated questions should be near zero.

### Latency
- Response time should be fast enough for natural call flow.
- Backend validations should not create noticeable delays where possible.

### Auditability
- All state transitions and final actions must be logged.

### Maintainability
- New workflows should be configurable without retraining the model.

### Safety
- High-risk decisions must remain outside the LLM.
- Verification and authorization rules must be enforced by code.

---

## 12. Recommended System Architecture

### Layer 1: Intent Router
Responsible for:
- classifying the issue,
- returning confidence,
- flagging ambiguity or unsupported intents.

### Layer 2: Workflow Registry
Responsible for:
- storing intent definitions,
- required and optional fields,
- validators,
- escalation conditions,
- action mappings.

### Layer 3: Dialogue Manager
Responsible for:
- managing state,
- identifying the next missing field,
- generating the next prompt,
- tracking retries and failures.

### Layer 4: Validation and Business Logic
Responsible for:
- validating field format and semantics,
- checking eligibility and verification,
- making policy decisions.

### Layer 5: Tool / Backend Action Layer
Responsible for:
- performing the actual customer operation,
- returning success or failure.

---

## 13. LLM Responsibilities vs Application Responsibilities

### LLM Responsibilities
- understand user intent,
- extract field values from natural language,
- generate the next question,
- summarize state for escalation.

### Application Responsibilities
- define workflows,
- determine required information,
- validate data,
- enforce business rules,
- execute tools,
- handle escalation.

This separation is critical for precision and safety.

---

## 14. Example Conversation Flow

### Use Case: Password Reset

#### Step 1
Caller: “I can’t log into my account.”

System:
- detect intent: `password_reset`
- load workflow
- required fields: `account_id`, `verification_code`

Agent:
- “I can help with that. What is your account ID?”

#### Step 2
Caller: “12345678”

System:
- validate account ID
- identify next missing field: `verification_code`

Agent:
- “Thanks. Please tell me the verification code we sent to your phone.”

#### Step 3
Caller: “481920”

System:
- validate code
- call `reset_password_tool`

Agent:
- “Your password reset request is complete. I’ve sent the reset instructions to your registered email.”

---

## 15. Metrics and Success Criteria

### Primary Metrics
- average turns to resolution,
- average handling time,
- successful completion rate,
- human escalation rate,
- required field completion rate.

### Quality Metrics
- validation failure rate,
- repeated-question rate,
- hallucinated-question rate,
- unsupported-intent rate,
- backend action failure rate.

### Customer Experience Metrics
- caller abandonment rate,
- customer satisfaction score,
- rate of caller repetition,
- time to resolution.

---

## 16. Risks

### Risk 1: Over-reliance on LLM judgment
Mitigation:
- keep business logic outside the LLM,
- use strict schemas and validators.

### Risk 2: Bad intent classification
Mitigation:
- confidence thresholds,
- ambiguity handling,
- fallback escalation.

### Risk 3: Excessive questioning
Mitigation:
- ask-next-missing-field logic,
- state tracking,
- avoid redundant prompts.

### Risk 4: Voice recognition errors
Mitigation:
- concise prompts,
- DTMF fallback,
- retry logic.

### Risk 5: Workflow sprawl
Mitigation:
- standardized workflow templates,
- central workflow registry,
- versioned schema management.

---

## 17. MVP Scope

The MVP should support:
- 3 to 5 high-volume call intents,
- structured workflow schemas,
- field validation,
- one-question-at-a-time prompting,
- backend action triggering,
- human escalation,
- logging and analytics.

### Suggested MVP Intents
1. Password reset
2. Billing dispute
3. Update profile information
4. Order status
5. Cancel service

---

## 18. Future Enhancements

- multi-intent handling within a single call,
- proactive field inference from CRM context,
- multilingual support,
- sentiment-aware escalation,
- dynamic workflow optimization using analytics,
- personalized prompts based on prior customer history,
- agent assist mode for hybrid human + AI workflows.

---

## 19. Open Questions

- What confidence threshold should trigger disambiguation vs escalation?
- Which workflows are safe for full automation in the first release?
- What backend systems will be available for validation and action execution?
- Which fields can be inferred from caller metadata versus explicitly asked?
- What compliance requirements apply to data storage and call logging?
- What retry threshold should trigger handoff to a human?

---

## 20. Final Recommendation

The product should be built around a **workflow registry + dialogue manager + validation layer**, with the LLM serving as the conversational interface rather than the decision engine.

The most efficient and precise strategy is:

**detect intent → ask for the next missing required field → validate → act**

This design minimizes unnecessary human involvement while preserving reliability, safety, and operational control.
