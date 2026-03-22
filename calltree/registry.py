"""Registry for loading IVR call-tree schemas."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from calltree.models import CallTreeNode, CallTreeSchema

_SCHEMA_DIR = Path(__file__).parent / "schemas"
_call_trees: dict[str, CallTreeSchema] = {}
_LOCK = Lock()


def _load_call_trees() -> dict[str, CallTreeSchema]:
    call_trees: dict[str, CallTreeSchema] = {}
    for schema_file in _SCHEMA_DIR.glob("*.json"):
        with open(schema_file) as f:
            raw_schema = json.load(f)
        schema = CallTreeSchema.model_validate(raw_schema)
        call_trees[schema.id] = schema
    return call_trees


def get_call_tree(tree_id: str = "acme_corp") -> CallTreeSchema | None:
    """Retrieve a call tree by id."""
    if not _call_trees:
        with _LOCK:
            if not _call_trees:
                _call_trees.update(_load_call_trees())
    return _call_trees.get(tree_id)


def get_call_tree_node(tree_id: str, node_id: str) -> CallTreeNode | None:
    """Retrieve a node from a call tree by id."""
    tree = get_call_tree(tree_id)
    if tree is None:
        return None
    return tree.get_node(node_id)
