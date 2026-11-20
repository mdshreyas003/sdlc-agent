"""The one model call shape the system uses: a structured (pydantic) response, with its usage, cached on disk.
It goes to Anthropic, or to an OpenAI-compatible server (Sarvam, vLLM) when given an `openai.OpenAI` client
(`WHY_LLM=openai`, ADR-0004).

These models take no sampling parameters, so outputs vary run to run; caching responses keyed by the exact
request makes rebuilds reproducible (the same graph from the same inputs). Tests never construct this with a
real client: they inject scripted proposers and composers at the domain seams instead.

`structured_call` is the single request both `LlmClient` (graph building, answers) and the scoreboard's
`whycode.eval.models.AnthropicStructured` make. Every call's usage is a `ModelCall`; inside `metered()`, each call
an `LlmClient` makes (a cached one reports the usage recorded when it was made) is collected, which is how our
system reports its cost per answer to the scoreboard.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, TypeVar

import anthropic
import openai
import pydantic
from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)

EXTRACTION_MODEL = "claude-sonnet-5-5"
COMPOSER_MODEL = "claude-opus-5-5"
JUDGE_MODEL = "claude-opus-5-5"
MATCHER_MODEL = "claude-opus-5-5"  # the entity-matching step for free-form questions

# US$ per million tokens: input, output, cache read, cache write (5-minute TTL, 1.25x input).
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5),
}

T = TypeVar("T", bound=pydantic.BaseModel)


class LlmError(RuntimeError):
    """The model gave no usable structured answer (refusal, truncation, API error)."""


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


def cached_system(prompt: str) -> list[dict[str, Any]]:
    """A system prompt marked for prompt caching."""
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


def check_stop(response: Any) -> None:
    """Raise unless the response ended normally (a refusal or truncation is no usable answer)."""
    if response.stop_reason == "refusal":
        raise LlmError(f"{response.model} refused ({getattr(response.stop_details, 'category', None)})")
    if response.stop_reason == "max_tokens":
        raise LlmError(f"{response.model} output was truncated at max_tokens")


def structured_call(client: Any, *, model: str, system: str, user: str, output: type[T], effort: str,
                    max_tokens: int) -> tuple[T, ModelCall]:
    """One structured-output request over either SDK (an `openai.OpenAI` client means an OpenAI-compatible
    server such as Sarvam or vLLM); raises `LlmError` when it gives nothing usable."""
    if isinstance(client, openai.OpenAI):
        return _openai_structured_call(client, model=model, system=system, user=user, output=output,
                                       effort=effort, max_tokens=max_tokens)
    try:
        response = client.messages.parse(model=model, max_tokens=max_tokens, system=cached_system(system),
                                         messages=[{"role": "user", "content": user}],
                                         output_config={"effort": effort}, output_format=output)
    except pydantic.ValidationError as exc:  # truncated or refused output fails validation in parse
        raise LlmError(f"{model} returned output that does not fit {output.__name__}: "
                       f"{exc.error_count()} errors") from exc
    check_stop(response)
    if response.parsed_output is None:
        raise LlmError(f"{model} stopped with {response.stop_reason} and no parsed output")
    return response.parsed_output, ModelCall.from_response(response)


def openai_call(response: Any) -> ModelCall:
    """The usage of one OpenAI-style chat completion."""
    u = response.usage
    return ModelCall(model=response.model, input_tokens=(u.prompt_tokens if u else 0) or 0,
                     output_tokens=(u.completion_tokens if u else 0) or 0)


def _openai_structured_call(client: openai.OpenAI, *, model: str, system: str, user: str, output: type[T],
                            effort: str, max_tokens: int) -> tuple[T, ModelCall]:
    """One `chat.completions.parse` request with a strict JSON schema. No prompt caching (no OpenAI-style
    equivalent); `effort` becomes `reasoning_effort`, whose reasoning text the answer never includes."""
    try:
        response = client.chat.completions.parse(
            model=model, max_tokens=max_tokens, reasoning_effort=effort, response_format=output,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    except openai.LengthFinishReasonError as exc:
        raise LlmError(f"{model} output was truncated at max_tokens") from exc
    except openai.ContentFilterFinishReasonError as exc:
        raise LlmError(f"{model} refused (content filter)") from exc
    except pydantic.ValidationError as exc:
        raise LlmError(f"{model} returned output that does not fit {output.__name__}: "
                       f"{exc.error_count()} errors") from exc
    message = response.choices[0].message
    if message.refusal:
        raise LlmError(f"{model} refused: {message.refusal}")
    if message.parsed is None:
        raise LlmError(f"{model} stopped with {response.choices[0].finish_reason} and no parsed output")
    return message.parsed, openai_call(response)


_calls: ContextVar[list[ModelCall] | None] = ContextVar("whycode_model_calls", default=None)


@contextmanager
def metered() -> Iterator[list[ModelCall]]:
    """Collect every call `LlmClient.parse` makes inside the block (in this thread or task)."""
    calls: list[ModelCall] = []
    token = _calls.set(calls)
    try:
        yield calls
    finally:
        _calls.reset(token)


def _record(call: ModelCall) -> None:
    if (calls := _calls.get()) is not None:
        calls.append(call)


class LlmClient:
    def __init__(self, client: anthropic.Anthropic | openai.OpenAI, cache_dir: Path | None = None,
                 max_tokens: int = 16000):
        self.client = client
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_tokens = max_tokens

    def parse(self, *, model: str, system: str, user: str, output: type[T], effort: str = "medium") -> T:
        key = hashlib.sha256(json.dumps(
            [model, system, user, output.__name__, output.model_json_schema(), effort], sort_keys=True
        ).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        usage_path = path.with_suffix(".usage.json") if path else None
        if path and path.exists():
            if usage_path.exists():
                _record(ModelCall.model_validate_json(usage_path.read_text()))
            return output.model_validate_json(path.read_text())
        try:
            parsed, call = structured_call(self.client, model=model, system=system, user=user, output=output,
                                           effort=effort, max_tokens=self.max_tokens)
        except (anthropic.APIError, openai.APIError) as exc:
            raise LlmError(f"{model} request failed: {exc}") from exc
        _record(call)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(parsed.model_dump_json())
            usage_path.write_text(call.model_dump_json())
        return parsed
