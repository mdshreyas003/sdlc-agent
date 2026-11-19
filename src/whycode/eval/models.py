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
from pydantic import BaseModel, ConfigDict

ANSWER_MODEL = "claude-opus-5-5"
JUDGE_MODEL = "claude-opus-5-5"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # shared with our system's entity matching (spec: one embedding model)

# US$ per million tokens: input, output, cache read, cache write (5-minute TTL, 1.25x input).
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
}


class ModelError(RuntimeError):
    """The model returned nothing usable (refusal, truncation, invalid output)."""


class ModelCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @classmethod
    def from_response(cls, response: Any) -> ModelCall:
        u = response.usage
        return cls(model=response.model, input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
                   cache_read_input_tokens=getattr(u, "cache_read_input_tokens", None) or 0,
                   cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", None) or 0)

    def cost_usd(self) -> float | None:
        price = PRICES.get(self.model)
        if price is None:
            return None
        p_in, p_out, p_read, p_write = price
        return (self.input_tokens * p_in + self.output_tokens * p_out
                + self.cache_read_input_tokens * p_read + self.cache_creation_input_tokens * p_write) / 1e6


class Usage(BaseModel):
    """Every model call one answer took."""

    calls: list[ModelCall] = []

    def __add__(self, other: Usage) -> Usage:
        return Usage(calls=[*self.calls, *other.calls])

    @property
    def input_tokens(self) -> int:
        return sum(c.input_tokens + c.cache_read_input_tokens + c.cache_creation_input_tokens for c in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def cost_usd(self) -> float | None:
        """Total cost, or None when a call used a model with no known price."""
        costs = [c.cost_usd() for c in self.calls]
        return None if any(c is None for c in costs) else sum(costs)  # type: ignore[arg-type]


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


def _system(prompt: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


def _check_stop(response: Any) -> None:
    if response.stop_reason == "refusal":
        raise ModelError(f"model refused ({getattr(response.stop_details, 'category', None)})")
    if response.stop_reason == "max_tokens":
        raise ModelError("model output was truncated at max_tokens")


class AnthropicStructured:
    """StructuredModel over `client.messages.parse` (structured outputs)."""

    def __init__(self, client: Any, model: str, *, effort: str = "medium", max_tokens: int = 16000):
        self.client, self.model, self.effort, self.max_tokens = client, model, effort, max_tokens

    def parse(self, *, system: str, user: str, output: type[T]) -> Parsed[T]:
        try:
            response = self.client.messages.parse(
                model=self.model, max_tokens=self.max_tokens, system=_system(system),
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort}, output_format=output)
        except pydantic.ValidationError as error:  # truncated or refused output fails validation in parse
            raise ModelError(f"model output did not match {output.__name__}: {error.error_count()} errors") from error
        _check_stop(response)
        return Parsed(response.parsed_output, Usage(calls=[ModelCall.from_response(response)]))


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
                model=self.model, max_tokens=self.max_tokens, system=_system(system), messages=messages,
                tools=tool_defs, output_config=output_config, **extra)
            calls.append(ModelCall.from_response(response))
            _check_stop(response)
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
