# Security and Compliance

## Principles
- Collect the minimum information required for task completion.
- Do not store more than is necessary.
- Make retention behavior explicit and configurable.
- Keep third-party providers outside the role of system of record.

## Third-party integration rules
### Boson
- use for voice I/O
- do not rely on Boson for durable workflow state

### Eigen
- use for extraction/orchestration only
- do not rely on Eigen as sole audit store
