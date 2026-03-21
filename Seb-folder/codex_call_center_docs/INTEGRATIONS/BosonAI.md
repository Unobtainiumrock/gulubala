# Boson AI Integration

## Role in the system
Boson AI should be treated as the **voice interaction layer**.

It should handle:
- speech input
- speech output
- interruption / barge-in behavior
- streaming transcripts
- voice experience quality

It should **not** be the source of truth for:
- workflow schemas
- required fields
- policy logic
- durable customer state

## Product rules for Boson
- Boson prompt should be channel-behavior-oriented, not workflow-authoritative.
- Workflow state must be held internally.
- Transcript retention must be explicitly configured.
- Human handoff summaries should use internal state plus transcript context.
