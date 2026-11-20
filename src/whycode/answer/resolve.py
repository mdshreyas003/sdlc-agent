"""Resolve: the entity-matching step for free-form questions that name no Code Entity exactly.

`EntityMatcher` is the model seam. It sees the question and a shortlist of Code Entities (found by a fixed
read-only pattern from the question's words, never by the model) and picks one, saying whether it is sure. Code
decides: a pick that is unsure, or not on the shortlist, is a refusal. One call per question, never a loop.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from pydantic import BaseModel, Field

from whycode.llm import LlmClient, LlmError

log = logging.getLogger(__name__)

MAX_WORDS = 12
_WORD = re.compile(r"[a-z][a-z0-9]+")
STOPWORDS = frozenset("""
a about above after again against all also an and any are as at be because been before being between both but by
can could did do does doing done each every few for from had has have having here how if in into is it its itself
just like made make makes many may might more most much must my no nor not now of off on once only or other our out
over own same she should so some still such than that the their them then there these they this those through to
too under until up us very was way we were what when where which while who whom why will with would you your
code codebase cockroach cockroachdb crdb file files function functions method package setting settings cluster
thing things work works working reason reasons decision decisions behind written change changed
""".split())


class EntityCandidate(BaseModel):
    id: str
    kind: str
    key: str


class EntityChoice(BaseModel):
    entity_id: str | None = Field(description="Id of the one candidate the question asks about, or null.")
    sure: bool = Field(description="True only when the question clearly asks about that one candidate.")
    reason: str = Field(default="", description="One sentence: why this candidate, or why none is clear.")


class EntityMatcher(Protocol):
    def match(self, question: str, candidates: list[EntityCandidate]) -> EntityChoice: ...


def question_words(question: str) -> list[str]:
    """Lower-case content words of a question, crudely stemmed (`retries` -> `retry`), for the shortlist."""
    out: list[str] = []
    for word in _WORD.findall(question.lower()):
        if word in STOPWORDS or len(word) < 3:
            continue
        for suffix, repl in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
            if word.endswith(suffix) and len(word) - len(suffix) + len(repl) >= 4:
                word = word[: -len(suffix)] + repl
                break
        out.append(word)
    return list(dict.fromkeys(out))[:MAX_WORDS]


MATCHER_SYSTEM = """You match a developer's question about CockroachDB SQL schema-change code to the one Code \
Entity it asks about: a package, a file, a function or a cluster setting.

Rules:
- Choose only from the candidates you are given, by their `id`.
- Set `sure` to true only when the question clearly asks about that one candidate.
- When the question could mean several candidates, is about the system in general, or none of the candidates \
fits, set `sure` to false and `entity_id` to null. Do not guess: a refusal is better than a loose match."""


class AnthropicEntityMatcher:
    """Production adapter: Opus 5.5 with structured output, responses cached on disk by the LlmClient."""

    def __init__(self, llm: LlmClient, model: str):
        self.llm = llm
        self.model = model

    def match(self, question: str, candidates: list[EntityCandidate]) -> EntityChoice:
        user = json.dumps({"question": question, "candidates": [c.model_dump() for c in candidates]}, indent=1)
        try:
            return self.llm.parse(model=self.model, system=MATCHER_SYSTEM, user=user, output=EntityChoice,
                                  effort="low")
        except LlmError as exc:
            log.warning("entity matching failed: %s", exc)
            return EntityChoice(entity_id=None, sure=False, reason="the matching step failed")
