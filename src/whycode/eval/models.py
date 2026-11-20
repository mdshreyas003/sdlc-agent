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
           "ModelCall", "ModelError", "OpenAIStructured", "OpenAIToolLoop",
           "Parsed", "StructuredModel", "Tool", "ToolLoopModel", "Usage"]

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


class OpenAIStructured(AnthropicStructured):
    """StructuredModel over an OpenAI-compatible server (Sarvam, vLLM): the same `structured_call`, which picks the
    API by the client it is given (an `openai.OpenAI`)."""


class OpenAIToolLoop:
    """ToolLoopModel over an OpenAI-compatible server: `AnthropicToolLoop` in chat-completions shapes.

    Every request offers the tools and asks for the final answer as a strict JSON schema; when the turn budget is
    spent, one last request with `tool_choice: none` asks for the answer. No prompt caching (no OpenAI-style
    equivalent); `effort` becomes `reasoning_effort`.
    """

    def __init__(self, client: Any, model: str, *, effort: str = "medium", max_tokens: int = 16000):
        self.client, self.model, self.effort, self.max_tokens = client, model, effort, max_tokens

    def run(self, *, system: str, user: str, tools: Sequence[Tool], output: type[T],
            max_turns: int) -> Parsed[T]:
        from openai.lib._parsing import type_to_response_format_param

        from whycode.llm import openai_call

        by_name = {t.name: t for t in tools}
        # Plain (not strict) tools: the SDK would validate strict tool arguments itself and end the run on a bad
        # call, where a bad call must go back to the model as a tool error.
        tool_defs = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                       "parameters": t.input_model.model_json_schema()}}
                     for t in tools]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        calls: list[ModelCall] = []
        for turn in range(max_turns + 1):
            extra = {"tool_choice": "none"} if turn == max_turns else {}
            response = self.client.chat.completions.create(
                model=self.model, max_tokens=self.max_tokens, reasoning_effort=self.effort, messages=messages,
                tools=tool_defs, response_format=type_to_response_format_param(output), **extra)
            calls.append(openai_call(response))
            choice = response.choices[0]
            if choice.finish_reason == "length":
                raise ModelError(f"{self.model} output was truncated at max_tokens")
            message = choice.message
            if message.tool_calls:
                messages.append({"role": "assistant", "content": message.content, "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name,
                                                                  "arguments": c.function.arguments}}
                    for c in message.tool_calls]})
                messages.extend({"role": "tool", "tool_call_id": c.id,
                                 "content": _call_tool(by_name, c.function.name, c.function.arguments)[0]}
                                for c in message.tool_calls)
                continue
            if message.refusal:
                raise ModelError(f"{self.model} refused: {message.refusal}")
            try:
                return Parsed(output.model_validate_json(message.content or ""), Usage(calls=calls))
            except pydantic.ValidationError as error:
                raise ModelError(f"final answer did not match {output.__name__}") from error
        raise ModelError("tool loop ended without an answer")


def _call_tool(by_name: dict[str, Tool], name: str, args: dict[str, Any] | str) -> tuple[str, bool]:
    """A tool's output, or an error message for the model: (content, is_error)."""
    tool = by_name.get(name)
    if tool is None:
        return f"unknown tool {name}", True
    try:
        return tool.call(args if isinstance(args, dict) else json.loads(args)), False
    except Exception as error:  # noqa: BLE001  a bad call goes back to the model, never ends the run
        return f"{type(error).__name__}: {error}", True


def _run_tool(by_name: dict[str, Tool], block: Any) -> dict[str, Any]:
    content, is_error = _call_tool(by_name, block.name, block.input)
    result = {"type": "tool_result", "tool_use_id": block.id, "content": content}
    return result | {"is_error": True} if is_error else result
