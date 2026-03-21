# Product Requirements Document (PRD)
## LLM-Driven Call Center Intake and Resolution Agent

### Status
Draft

### Owner
Seb S.

### Last Updated
March 21, 2026

## Purpose
Build an LLM-driven call center agent that resolves customer issues with minimal human involvement by collecting only the information required for a specific call, validating that information, and triggering the correct backend action or escalation path.

## Product principle
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

## Primary goals
- Reduce human involvement in routine call center interactions.
- Collect all required information for a call with high precision.
- Minimize the number of turns needed to complete a workflow.
- Improve consistency across intents and agents.
- Ensure safe and deterministic execution of backend actions.

## Non-goals
- letting the LLM invent business policies
- allowing the LLM to determine authorization rules
- completely open-ended troubleshooting without workflow structure

## MVP intents
1. Password reset
2. Billing dispute
3. Update profile information
4. Order status
5. Cancel service
