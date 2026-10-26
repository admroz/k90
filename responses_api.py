"""Stateless Responses API conversation for models that require it for tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import json

from openai import OpenAI
from outbound_policy import ModelCallError, sanitize_payload
from profiling import span


def uses_responses(model: str) -> bool:
    """Keep other models/providers on the existing LiteLLM path."""
    name = model.removeprefix("openai/")
    return name == "gpt-6.1-sol" or name.startswith("gpt-6.1-sol-")


@dataclass
class FunctionCall:
    call_id: str
    name: str
    arguments: str


@dataclass
class Turn:
    text: str
    calls: list[FunctionCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    complete: bool = True


def _input_messages(messages: list[dict]) -> list[dict]:
    result = deepcopy(messages)
    for message in result:
        if not isinstance(message["content"], list):
            continue
        parts = []
        for part in message["content"]:
            if part["type"] == "text":
                parts.append({"type": "input_text", "text": part["text"]})
            elif part["type"] == "image_url":
                image = part["image_url"]
                parts.append({
                    "type": "input_image",
                    "image_url": image["url"],
                    "detail": image.get("detail", "auto"),
                })
            else:
                raise ValueError("Unsupported message content type")
        message["content"] = parts
    return result


class ResponsesConversation:
    def __init__(
        self, model: str, messages: list[dict], tools: list[dict] | None = None,
        *, reasoning_effort: str = "low", max_output_tokens: int = 8192,
    ):
        if reasoning_effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError("GPT-6.1 Sol reasoning effort must be low, medium, high, xhigh or max")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        self.model = model.removeprefix("openai/")
        self.input = _input_messages(sanitize_payload(messages))
        # Existing schemas have optional/default fields. Preserve their semantics.
        self.tools = [
            {"type": "function", **deepcopy(tool["function"]), "strict": False}
            for tool in (tools or [])
        ]
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    def complete(self) -> Turn:
        options = {}
        if self.tools:
            options = {"tools": self.tools, "tool_choice": "auto"}
        payload = sanitize_payload(dict(
            model=self.model, input=deepcopy(self.input),
            reasoning={"effort": self.reasoning_effort}, max_output_tokens=self.max_output_tokens,
            store=False, include=["reasoning.encrypted_content"], **options,
        ))
        try:
            with span('provider_request'), OpenAI(timeout=120.0, max_retries=2) as client:
                response = client.responses.create(**payload)
        except Exception:
            raise ModelCallError('model_request_failed') from None
        if response.status not in {"completed", "incomplete"}:
            raise RuntimeError("Responses API did not complete the request")
        # Replay ALL output items, including encrypted reasoning, within this turn.
        # No server-side response ID or reasoning is persisted in the local history.
        self.input.extend(item.model_dump(exclude_none=True) for item in response.output)
        calls = [
            FunctionCall(item.call_id, item.name, item.arguments)
            for item in response.output if item.type == "function_call"
        ]
        text = []
        for item in response.output:
            if item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        text.append(part.text)
                    elif part.type == "refusal":
                        text.append(part.refusal)
        usage = response.usage
        return Turn(
            text="\n".join(text), calls=calls,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            complete=response.status == "completed",
        )

    def add_tool_result(self, call_id: str, result: dict) -> None:
        self.input.append({
            "type": "function_call_output", "call_id": call_id,
            "output": json.dumps(result, ensure_ascii=False, default=str),
        })
