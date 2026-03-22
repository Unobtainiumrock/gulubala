"""Typed models for IVR call-tree schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, model_validator

from workflows.registry import list_intents


CallTreeInputType = Literal["dtmf", "speech"]


class CallTreeTransition(BaseModel):
    """A transition between two IVR nodes."""

    input: str
    next_node_id: str
    label: str | None = None


class CallTreeNode(BaseModel):
    """A single node in the IVR tree."""

    id: str
    label: str
    prompt: str
    input_type: CallTreeInputType
    transitions: list[CallTreeTransition] = Field(default_factory=list)
    intent: str | None = None
    invalid_input_prompt: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_transitions(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        raw_transitions = data.get("transitions")
        if isinstance(raw_transitions, dict):
            data["transitions"] = [
                {
                    "input": key,
                    "next_node_id": value,
                }
                for key, value in raw_transitions.items()
            ]
        return data


class CallTreeSchema(BaseModel):
    """Canonical IVR tree schema loaded from JSON."""

    id: str
    brand: str
    root_node_id: str
    nodes: list[CallTreeNode]
    _node_map: dict[str, CallTreeNode] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _validate_schema(self) -> "CallTreeSchema":
        node_ids = [node.id for node in self.nodes]
        unique_node_ids = set(node_ids)
        if len(unique_node_ids) != len(node_ids):
            raise ValueError("Call tree contains duplicate node ids")

        if self.root_node_id not in unique_node_ids:
            raise ValueError(f"Unknown root_node_id '{self.root_node_id}'")

        supported_intents = set(list_intents())
        for node in self.nodes:
            if not node.transitions and not node.intent:
                raise ValueError(f"Leaf node '{node.id}' must declare an intent")

            if node.input_type == "speech":
                if not node.intent:
                    raise ValueError(f"Speech node '{node.id}' must declare an intent")
                if node.transitions:
                    raise ValueError(f"Speech node '{node.id}' cannot declare transitions")

            if node.intent and node.intent not in supported_intents:
                raise ValueError(f"Node '{node.id}' references unknown intent '{node.intent}'")

            for transition in node.transitions:
                if transition.next_node_id not in unique_node_ids:
                    raise ValueError(
                        f"Node '{node.id}' references unknown next node '{transition.next_node_id}'"
                    )

        self._node_map = {node.id: node for node in self.nodes}
        return self

    def get_node(self, node_id: str) -> CallTreeNode | None:
        return self._node_map.get(node_id)
