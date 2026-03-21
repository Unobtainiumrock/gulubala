"""Layer 3: Dialogue Manager — state tracking, field extraction, prompt generation."""

import json
from client.eigen import chat_completion
from config.models import HIGGS_CHAT_MODEL, GPT_OSS_MODEL, MAX_VALIDATION_RETRIES
from validation.validators import get_validator
from actions.backend import execute_action


class DialogueState:
    """Tracks conversation state for a single call session."""

    def __init__(self, intent: str, workflow: dict):
        self.intent = intent
        self.workflow = workflow
        self.collected_fields: dict[str, str] = {}
        self.validation_failures: dict[str, int] = {}
        self.turn_count = 0
        self.escalated = False
        self.escalation_reason = ""
        self.resolved = False
        self.resolution_message = ""
        self.conversation_history: list[dict] = []

    @property
    def required_fields(self) -> list[dict]:
        return self.workflow["required_fields"]

    @property
    def missing_fields(self) -> list[dict]:
        return [f for f in self.required_fields if f["name"] not in self.collected_fields]

    @property
    def next_field(self) -> dict | None:
        missing = self.missing_fields
        return missing[0] if missing else None

    @property
    def all_fields_collected(self) -> bool:
        return len(self.missing_fields) == 0

    def get_state_summary(self) -> dict:
        return {
            "intent": self.intent,
            "collected_fields": self.collected_fields,
            "missing_required_fields": [f["name"] for f in self.missing_fields],
            "next_field": self.next_field["name"] if self.next_field else None,
            "escalated": self.escalated,
            "resolved": self.resolved,
        }

    def _extract_field(self, field: dict, user_utterance: str) -> str | None:
        """Use Higgs 2.5 to extract a field value from the user's utterance."""
        messages = [
            {
                "role": "system",
                "content": (
                    f"Extract the value for '{field['name']}' from the user's message. "
                    f"Field type: {field['type']}. "
                    f"Respond with ONLY the extracted value, nothing else. "
                    f"If the value is not present, respond with exactly: NOT_FOUND"
                ),
            },
            {"role": "user", "content": user_utterance},
        ]
        raw = chat_completion(model=HIGGS_CHAT_MODEL, messages=messages, temperature=0.1, max_tokens=128)
        value = raw.strip()
        return None if value == "NOT_FOUND" else value

    def _generate_response(self, context: str) -> str:
        """Use Higgs 2.5 to generate a natural conversational response."""
        state = self.get_state_summary()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a friendly, professional call center agent. "
                    "Generate a brief, natural response based on the current context. "
                    "Do not ask for information that has already been collected. "
                    "Ask for only ONE piece of information at a time."
                ),
            },
            {"role": "user", "content": f"State: {json.dumps(state)}\nContext: {context}"},
        ]
        return chat_completion(model=HIGGS_CHAT_MODEL, messages=messages, temperature=0.3, max_tokens=256)

    def _generate_escalation_summary(self) -> str:
        """Use GPT-OSS-120B to generate a detailed escalation summary."""
        messages = [
            {
                "role": "system",
                "content": (
                    "Generate a concise escalation summary for a human agent. Include: "
                    "1) caller's issue, 2) information collected so far, "
                    "3) reason for escalation, 4) recommended next steps."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "intent": self.intent,
                    "collected_fields": self.collected_fields,
                    "escalation_reason": self.escalation_reason,
                    "conversation_turns": self.turn_count,
                    "history": [
                        {"role": m["role"], "content": m["content"][:200]}
                        for m in self.conversation_history[-6:]
                    ],
                }),
            },
        ]
        return chat_completion(model=GPT_OSS_MODEL, messages=messages, temperature=0.2, max_tokens=512)

    def next_turn(self, user_utterance: str) -> str:
        """Process a user turn and return the agent's response.

        This is the main dialogue loop step:
        1. Check for escalation triggers
        2. Extract field value from utterance
        3. Validate extracted value
        4. If all fields collected, execute action
        5. Otherwise, ask for next missing field
        """
        self.turn_count += 1
        self.conversation_history.append({"role": "user", "content": user_utterance})

        # Check if user wants a human
        lower = user_utterance.lower()
        if any(phrase in lower for phrase in ("speak to a human", "talk to a person", "real person", "agent please", "supervisor")):
            self.escalated = True
            self.escalation_reason = "user_requests_human"
            summary = self._generate_escalation_summary()
            response = f"I understand. Let me connect you with a human agent. {summary}"
            self.conversation_history.append({"role": "assistant", "content": response})
            return response

        # Try to extract the current expected field
        field = self.next_field
        if field:
            value = self._extract_field(field, user_utterance)

            if value:
                validator = get_validator(field["validator"])
                valid, result = validator(value)

                if valid:
                    self.collected_fields[field["name"]] = result
                    self.validation_failures.pop(field["name"], None)
                else:
                    # Validation failed
                    failures = self.validation_failures.get(field["name"], 0) + 1
                    self.validation_failures[field["name"]] = failures

                    if failures >= MAX_VALIDATION_RETRIES:
                        self.escalated = True
                        self.escalation_reason = f"failed_verification_{failures}x"
                        summary = self._generate_escalation_summary()
                        response = f"I'm having trouble verifying that information. Let me connect you with someone who can help. {summary}"
                        self.conversation_history.append({"role": "assistant", "content": response})
                        return response

                    response = self._generate_response(f"Validation failed for {field['name']}: {result}. Ask again.")
                    self.conversation_history.append({"role": "assistant", "content": response})
                    return response

        # Check if all fields are now collected
        if self.all_fields_collected:
            action_name = self.workflow["action"]
            action_result = execute_action(action_name, self.collected_fields)
            self.resolved = True
            self.resolution_message = action_result
            response = self._generate_response(f"Action completed: {action_result}")
            self.conversation_history.append({"role": "assistant", "content": response})
            return response

        # Ask for next missing field
        next_f = self.next_field
        if next_f:
            response = self._generate_response(f"Need to collect: {next_f['name']}. Suggested prompt: {next_f['prompt']}")
        else:
            response = self._generate_response("All information collected, preparing to process.")

        self.conversation_history.append({"role": "assistant", "content": response})
        return response
