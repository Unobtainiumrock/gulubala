# AGENTS.md

Persistent implementation instructions for Codex and developers.

## Product rules
1. The LLM is the conversational layer only.
2. Business rules must live in code or schema, not in free-form prompts.
3. All required fields must come from workflow schema files under `SCHEMAS/`.
4. Ask only for the next missing required field unless the workflow explicitly allows bundling.
5. Never ask for already validated fields again unless the user changes them.
6. Boson AI is the voice I/O layer, not the workflow source of truth.
7. Eigen AI is an integration layer for documents and/or orchestration, not the conversational source of truth.
8. Do not let the model decide retention, compliance, or authorization policy.

## Engineering principles
- Prefer typed models over loose dicts.
- Prefer explicit state machines over hidden prompt state.
- Prefer deterministic validators over model judgment.
- Keep adapters thin and testable.
- Make conversation state serializable.

## Definition of done
A task is not done unless:
- code is typed,
- tests are added or updated,
- schema contracts are respected,
- docs are updated if behavior changed,
- failure cases are handled.

## Prohibited shortcuts
Do not:
- hardcode workflow logic into prompts,
- skip validation for “obvious” fields,
- collapse all logic into one monolithic agent,
- make Boson or Eigen a system of record.
