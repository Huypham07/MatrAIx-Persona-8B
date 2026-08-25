"""Tool-driven user simulator session with messages[] memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from playground.task_content_bundle import TaskContentBundle
from playground.types import Persona
from playground.user_sim.prompt import assemble_system_prompt
from playground.user_sim.tool_client import ToolStepClient
from playground.user_sim.tools import TurnAction, extract_stop_token, parse_tool_calls


_START_OBSERVATION = (
    "The conversation is starting. The application chatbot has not replied yet. "
    "Send your opening message with send_message."
)


def _format_assistant_turn(action: TurnAction) -> str:
    """Record what the simulated user did without echoing tool-call syntax."""
    parts: List[str] = []
    if action.capability_tool:
        parts.append(
            "[Used tool `{}` with {}]".format(
                action.capability_tool,
                action.capability_arguments or {},
            )
        )
    if action.message:
        parts.append(action.message)
    if action.end_reason:
        note = (action.note or "").strip()
        if note:
            parts.append("[Ended: {} — {}]".format(action.end_reason, note))
        else:
            parts.append("[Ended: {}]".format(action.end_reason))
    return "\n".join(parts) if parts else "(no action)"


class UserSimSession:
    """Tool-driven simulated user with real multi-turn ``messages[]`` memory."""

    def __init__(
        self,
        client: ToolStepClient,
        persona: Persona,
        *,
        persona_yaml_path: Optional[str] = None,
        task_bundle: Optional[TaskContentBundle] = None,
    ) -> None:
        self._client = client
        self._persona = persona
        self._persona_yaml_path = persona_yaml_path
        system = assemble_system_prompt(
            persona,
            persona_yaml_path=persona_yaml_path,
            task_bundle=task_bundle,
        )
        self._messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
        self.system_prompt = system


    @property
    def messages(self) -> List[Dict[str, Any]]:
        return list(self._messages)

    def next_action(self, observation: str, *, allow_end: bool = True) -> TurnAction:
        """Generate the next user step, rejecting premature termination briefly."""
        prompt = observation
        for _ in range(3):
            self._messages.append({"role": "user", "content": prompt})
            calls = self._client.complete_with_tools(self._messages)
            action = parse_tool_calls(calls)
            if action.message:
                stop = extract_stop_token(action.message)
                if stop and not action.end_reason:
                    action.end_reason = stop
            self._messages.append(
                {
                    "role": "assistant",
                    "content": _format_assistant_turn(action),
                }
            )
            if allow_end or not action.end_reason:
                return action
            prompt = (
                "Latest application observation:\n\"\"\"{}\"\"\"\n\n"
                "You have not completed the minimum number of meaningful exchanges. "
                "Ask one specific natural follow-up based on the latest answer; do not end yet."
            ).format(observation)
        raise RuntimeError(
            "persona model repeatedly ended before the minimum conversation depth"
        )

    def opening_action(self, *, allow_end: bool = True) -> TurnAction:
        return self.next_action(_START_OBSERVATION, allow_end=allow_end)
