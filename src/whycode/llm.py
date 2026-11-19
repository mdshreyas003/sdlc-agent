"""The one Anthropic call shape the system uses: a structured (pydantic) response, cached on disk.

These models take no sampling parameters, so outputs vary run to run; caching responses keyed by the exact
request makes rebuilds reproducible (the same graph from the same inputs). Tests never construct this with a
real client: they inject scripted proposers and composers at the domain seams instead.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TypeVar

import anthropic
import pydantic

log = logging.getLogger(__name__)

EXTRACTION_MODEL = "claude-sonnet-5-5"
COMPOSER_MODEL = "claude-opus-5-5"
JUDGE_MODEL = "claude-opus-5-5"

T = TypeVar("T", bound=pydantic.BaseModel)


class LlmError(RuntimeError):
    """The model gave no usable structured answer (refusal, truncation, API error)."""


class LlmClient:
    def __init__(self, client: anthropic.Anthropic, cache_dir: Path | None = None, max_tokens: int = 16000):
        self.client = client
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_tokens = max_tokens

    def parse(self, *, model: str, system: str, user: str, output: type[T], effort: str = "medium") -> T:
        key = hashlib.sha256(json.dumps(
            [model, system, user, output.__name__, output.model_json_schema(), effort], sort_keys=True
        ).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        if path and path.exists():
            return output.model_validate_json(path.read_text())
        try:
            response = self.client.messages.parse(
                model=model,
                max_tokens=self.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort},
                output_format=output,
            )
        except pydantic.ValidationError as exc:
            raise LlmError(f"{model} returned output that does not fit {output.__name__}: {exc}") from exc
        except anthropic.APIError as exc:
            raise LlmError(f"{model} request failed: {exc}") from exc
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            raise LlmError(f"{model} stopped with {response.stop_reason}")
        parsed = response.parsed_output
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(parsed.model_dump_json())
        return parsed
