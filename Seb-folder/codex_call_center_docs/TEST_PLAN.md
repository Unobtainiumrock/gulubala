# Test Plan

## Unit tests
- validators
- dialogue manager
- schema loader

## Integration tests
- password reset happy path
- invalid code then retry
- billing dispute full flow
- backend failure propagation

## Conversation simulation tests
- short successful call
- repeated ASR confusion on digits
- caller requests human

## Privacy tests
- redaction behavior
- retention flags
- escalation summary sensitivity checks
