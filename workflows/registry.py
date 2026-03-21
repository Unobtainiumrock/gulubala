"""Layer 2: Workflow Registry — load and retrieve intent workflow schemas."""

import json
from pathlib import Path

_SCHEMA_DIR = Path(__file__).parent / "schemas"
_workflows: dict[str, dict] = {}


def _load_schemas():
    """Load all workflow schemas from the schemas directory."""
    global _workflows
    for schema_file in _SCHEMA_DIR.glob("*.json"):
        with open(schema_file) as f:
            schema = json.load(f)
        _workflows[schema["intent"]] = schema


def get_workflow(intent: str) -> dict | None:
    """Retrieve the workflow schema for a given intent."""
    if not _workflows:
        _load_schemas()
    return _workflows.get(intent)


def list_intents() -> list[str]:
    """Return all registered intent names."""
    if not _workflows:
        _load_schemas()
    return list(_workflows.keys())
