"""Shared test support for the scoreboard: a miniature CockroachDB-shaped corpus, scripted models,
a deterministic embedder and helpers to lay out a throwaway eval directory.

Nothing here talks to the network or builds a real Anthropic client.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from whycode.contract import Answer, EvidenceItem, Sentence
from whycode.eval.corpus import CorpusRecord
from whycode.eval.models import ModelCall, Parsed, Tool, Usage
from whycode.eval.runner import Query, System

REPO_ROOT = Path(__file__).resolve().parents[2]
CUTOFF = dt.date(2024, 6, 30)

SCHEMAS_RFC = """- Feature Name: User-defined SQL logical schemas
- Status: superseded by #48276
- Start Date: 2018-10-03
- RFC PR: #30916, originally #13319
- Cockroach Issue: #26443

# Summary

This RFC proposes to introduce an additional level in the namespace
structure of stored objects (tables, views, sequences), called the
*schema namespace*, in between the database and objects themselves.
"""

UDS_RFC = """- Feature Name: User Defined Schemas
- Status: in progress
- Start Date: 2020-05-01
- RFC PR: [#48276](https://github.com/cockroachdb/cockroach/pull/48276)
- Cockroach Issue: [#26443](https://github.com/cockroachdb/cockroach/issues/26443)

# Summary

Schemas get their own descriptors so that a schema can be renamed
without rewriting every table descriptor inside it.
"""

FIXTURE_RECORDS = [
    CorpusRecord(id="rfc:20181003_schemas", kind="rfc", title="20181003_schemas.md", text=SCHEMAS_RFC,
                 date=dt.date(2018, 10, 3), paths=["docs/RFCS/20181003_schemas.md"]),
    CorpusRecord(id="rfc:20200501_user_defined_schemas", kind="rfc", title="20200501_user_defined_schemas.md",
                 text=UDS_RFC, date=dt.date(2020, 5, 1), paths=["docs/RFCS/20200501_user_defined_schemas.md"]),
    CorpusRecord(id="issue:117574", kind="issue", number=117574,
                 title="sql: ALTER TABLE CONFIGURE ZONE panics on a dropped index",
                 text="Running CONFIGURE ZONE on an index that is being dropped panics the gateway node.",
                 date=dt.date(2024, 1, 10), labels=["C-bug", "regression", "A-schema-changes"]),
    CorpusRecord(id="pr:121026", kind="pr", number=121026,
                 title="sql: skip dropped indexes when configuring zones",
                 text="Zone configuration now ignores indexes in the DROP state, because their "
                      "descriptors may already be gone.\n\nFixes: #117574\n\nRelease note (bug fix): none",
                 date=dt.date(2024, 6, 22), paths=["pkg/sql/configure_zone.go", "pkg/sql/configure_zone_test.go"],
                 commits=["1111111111111111111111111111111111111111"]),
    CorpusRecord(id="pr:116000", kind="pr", number=116000, title="schemachanger: Implement CREATE DATABASE",
                 text="CREATE DATABASE now runs in the declarative schema changer, so that it gets "
                      "transactional semantics.",
                 date=dt.date(2023, 12, 1),
                 paths=["pkg/sql/schemachanger/scbuild/internal/scbuildstmt/create_database.go"],
                 commits=["2222222222222222222222222222222222222222"]),
    CorpusRecord(id="pr:116879", kind="pr", number=116879,
                 title='Revert "schemachanger: Implement CREATE DATABASE"',
                 text="This reverts commit 2222222222222222222222222222222222222222.\n\n"
                      "The declarative CREATE DATABASE broke backup restore of databases.",
                 date=dt.date(2023, 12, 20),
                 paths=["pkg/sql/schemachanger/scbuild/internal/scbuildstmt/create_database.go"]),
    CorpusRecord(id="pr:125000", kind="pr", number=125000,
                 title="sql: add sql.schema.force_declarative setting",
                 text="This adds a cluster setting that forces every DDL statement through the declarative "
                      "schema changer, to flush out gaps before the legacy path is removed.",
                 date=dt.date(2024, 5, 2), paths=["pkg/sql/exec_util.go"]),
    CorpusRecord(id="pr:127500", kind="pr", number=127500,
                 title='Revert "sql: add sql.schema.force_declarative setting"',
                 text="The setting made upgrades fail on clusters with legacy descriptors.",
                 date=dt.date(2024, 7, 15), paths=["pkg/sql/exec_util.go"]),
    CorpusRecord(id="pr:126100", kind="pr", number=126100, title="sql: bump lease renewal jitter",
                 text="Lease renewal now uses more jitter so that nodes do not renew at the same instant.",
                 date=dt.date(2024, 6, 21), paths=["pkg/sql/catalog/lease/lease.go"]),
    CorpusRecord(id="issue:130001", kind="issue", number=130001, title="sql: new lease bug after the cutoff",
                 text="Reported in the Held-out Window.", date=dt.date(2024, 8, 1), labels=["C-bug"]),
]


# --- scripted models ---------------------------------------------------------------------------

class ScriptedModel:
    """A StructuredModel that replies from a script; `reply(output_type, system, user)` builds the value."""

    def __init__(self, reply: Callable[[type[BaseModel], str, str], BaseModel], model: str = "claude-opus-5-5",
                 input_tokens: int = 1000, output_tokens: int = 100):
        self.reply, self.model = reply, model
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.calls: list[tuple[str, str]] = []

    def parse(self, *, system: str, user: str, output: type[BaseModel]) -> Parsed:
        self.calls.append((system, user))
        value = self.reply(output, system, user)
        return Parsed(value, Usage(calls=[ModelCall(model=self.model, input_tokens=self.input_tokens,
                                                    output_tokens=self.output_tokens)]))


class ScriptedToolLoop:
    """A ToolLoopModel that runs a fixed list of real tool calls, then builds the final value from their outputs."""

    def __init__(self, steps: Sequence[tuple[str, dict[str, Any]]],
                 final: Callable[[list[str]], BaseModel], model: str = "claude-opus-5-5"):
        self.steps, self.final, self.model = steps, final, model
        self.outputs: list[str] = []

    def run(self, *, system: str, user: str, tools: Sequence[Tool], output: type[BaseModel],
            max_turns: int) -> Parsed:
        by_name = {t.name: t for t in tools}
        for name, args in self.steps[:max_turns]:
            self.outputs.append(by_name[name].call(args))
        calls = [ModelCall(model=self.model, input_tokens=500, output_tokens=50)] * (len(self.steps) + 1)
        return Parsed(self.final(self.outputs), Usage(calls=calls))


class HashEmbedder:
    """Deterministic bag-of-words vectors: shared words give a high cosine, nothing else matters."""

    def __init__(self, name: str = "hash-bow-1024"):
        self.name = name

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(1024, dtype=np.float32)
        for word in re.findall(r"[a-z0-9_.]+", text.lower()):
            v[int(hashlib.sha256(word.encode()).hexdigest(), 16) % 1024] += 1.0
        norm = np.linalg.norm(v)
        return v / norm if norm else v

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, 1024), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vec(text)


def ours_factory(ctx) -> System:
    """Stands in for our `why` system, plugged in through `--systems ours=eval_support:ours_factory`."""
    def why(query: Query) -> Answer:
        return Answer(anchor=query.anchor, refused=False, confidence="High",
                      evidence_chain=[EvidenceItem(node_id="pr:121026", kind="pr",
                                                   quote="because their descriptors may already be gone")],
                      sentences=[Sentence(text="Dropped indexes may have lost their descriptors.", cites=["pr:121026"])])

    return System("ours", why, {"answer": ctx.answer_model, "embedding": ctx.embedding_model})


# --- the real Anthropic SDK over a fake transport (never the network) -------------------------

def anthropic_client(replies: Sequence[dict[str, Any]], requests: list[dict[str, Any]]):
    """An `anthropic.Anthropic` whose HTTP transport returns `replies` in order and records request bodies."""
    import httpx2
    from anthropic import Anthropic, DefaultHttpxClient

    queue = list(replies)

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        requests.append(body)
        reply = queue.pop(0)
        return httpx2.Response(200, json={
            "id": f"msg_{len(requests)}", "type": "message", "role": "assistant", "model": body["model"],
            "content": reply["content"], "stop_reason": reply.get("stop_reason", "end_turn"), "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 100}})

    return Anthropic(api_key="test", max_retries=0,
                     http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)))


def text_reply(value: BaseModel | dict[str, Any], stop_reason: str = "end_turn") -> dict[str, Any]:
    data = value.model_dump() if isinstance(value, BaseModel) else value
    return {"content": [{"type": "text", "text": json.dumps(data)}], "stop_reason": stop_reason}


def tool_use_reply(name: str, args: dict[str, Any], id: str = "toolu_1") -> dict[str, Any]:
    return {"content": [{"type": "tool_use", "id": id, "name": name, "input": args}], "stop_reason": "tool_use"}
