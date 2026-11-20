"""The model seam the scoreboard depends on, and its Anthropic adapters.

Baselines and the judge talk to two tiny interfaces: `StructuredModel` (one call, schema-valid
output) and `ToolLoopModel` (a tool-use loop that ends in schema-valid output). Tests inject
scripted implementations; only the composition root (`whycode.eval.cli`) builds a real
`anthropic.Anthropic` client.

Scored runs must use the same models for every system, so eval calls never opt into
server-side refusal fallbacks (a fallback silently changes the model): a refusal becomes an
error record instead.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

import pydantic
from pydantic import BaseModel

from whycode.llm import PRICES, LlmError, ModelCall, Usage, cached_system, check_stop, structured_call

__all__ = ["ANSWER_MODEL", "EMBEDDING_MODEL", "JUDGE_MODEL", "PRICES", "AnthropicStructured", "AnthropicToolLoop",
           "ModelCall", "ModelError", "Parsed", "StructuredModel", "Tool", "ToolLoopModel", "Usage"]

ANSWER_MODEL = "claude-opus-5-5"
JUDGE_MODEL = "claude-opus-5-5"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # the vector RAG baseline's embeddings (spec: one embedding model)

ModelError = LlmError
"""The model returned nothing usable (refusal, truncation, invalid output)."""


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Parsed(Generic[T]):
    value: T
    usage: Usage


@dataclass(frozen=True)
class Tool:
    """A read-only tool a ToolLoopModel may call: arguments validate against `input_model`."""

    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[[Any], str]

    def call(self, args: dict[str, Any]) -> str:
        return self.fn(self.input_model.model_validate(args))


class StructuredModel(Protocol):
    def parse(self, *, system: str, user: str, output: type[T]) -> Parsed[T]: ...


class ToolLoopModel(Protocol):
    def run(self, *, system: str, user: str, tools: Sequence[Tool], output: type[T],
            max_turns: int) -> Parsed[T]: ...


class AnthropicStructured:
    """StructuredModel over `whycode.llm.structured_call` (structured outputs)."""

    def __init__(self, client: Any, model: str, *, effort: str = "medium", max_tokens: int = 16000):
        self.client, self.model, self.effort, self.max_tokens = client, model, effort, max_tokens

    def parse(self, *, system: str, user: str, output: type[T]) -> Parsed[T]:
        value, call = structured_call(self.client, model=self.model, system=system, user=user, output=output,
                                      effort=self.effort, max_tokens=self.max_tokens)
        return Parsed(value, Usage(calls=[call]))


class AnthropicToolLoop:
    """ToolLoopModel over a manual `client.messages.create` tool-use loop.

    The final answer comes back as structured output (`output_config.format`). When the turn
    budget is spent, one last request with `tool_choice: none` asks for the answer.
    """

    def __init__(self, client: Any, model: str, *, effort: str = "medium", max_tokens: int = 16000):
        self.client, self.model, self.effort, self.max_tokens = client, model, effort, max_tokens

    def run(self, *, system: str, user: str, tools: Sequence[Tool], output: type[T],
            max_turns: int) -> Parsed[T]:
        import anthropic

        by_name = {t.name: t for t in tools}
        tool_defs = [{"name": t.name, "description": t.description,
                      "input_schema": anthropic.transform_schema(t.input_model)} for t in tools]
        output_config = {"effort": self.effort,
                         "format": {"type": "json_schema", "schema": anthropic.transform_schema(output)}}
        messages: list[dict[str, Any]] = [{"role": "user", "content": user}]
        calls: list[ModelCall] = []
        for turn in range(max_turns + 1):
            extra = {"tool_choice": {"type": "none"}} if turn == max_turns else {}
            response = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=cached_system(system), messages=messages,
                tools=tool_defs, output_config=output_config, **extra)
            calls.append(ModelCall.from_response(response))
            check_stop(response)
            uses = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason == "tool_use" and uses:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [_run_tool(by_name, b) for b in uses]})
                continue
            text = next((b.text for b in response.content if b.type == "text"), "")
            try:
                return Parsed(output.model_validate_json(text), Usage(calls=calls))
            except pydantic.ValidationError as error:
                raise ModelError(f"final answer did not match {output.__name__}") from error
        raise ModelError("tool loop ended without an answer")


def _run_tool(by_name: dict[str, Tool], block: Any) -> dict[str, Any]:
    result = {"type": "tool_result", "tool_use_id": block.id}
    tool = by_name.get(block.name)
    if tool is None:
        return result | {"content": f"unknown tool {block.name}", "is_error": True}
    try:
        args = block.input if isinstance(block.input, dict) else json.loads(block.input)
        return result | {"content": tool.call(args)}
    except Exception as error:  # noqa: BLE001  a bad call goes back to the model, never ends the run
        return result | {"content": f"{type(error).__name__}: {error}", "is_error": True}
