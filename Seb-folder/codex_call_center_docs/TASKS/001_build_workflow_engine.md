# Task 001 — Build Workflow Engine

## Read first
- `PRD.md`
- `AGENTS.md`
- `ARCHITECTURE.md`
- `WORKFLOWS.md`
- `SCHEMAS/`

## Goal
Implement a workflow engine that:
1. loads a workflow schema by intent,
2. compares required fields against collected state,
3. chooses the next missing required field,
4. returns a structured planning object,
5. supports escalation rules.
