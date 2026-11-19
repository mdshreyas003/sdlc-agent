"""The raw history the scoreboard checks against.

Gold quotes, citation precision, automatic labels and the vector-RAG baseline all read the same
corpus: one `CorpusRecord` per citable record (RFC, pull request, issue, review, commit). The
record `id` is the node id a system cites, so it must be the same id the graph uses.

Ticket 02 feeds the real slice by writing one JSON object per line in this shape
(`MemoryCorpus.from_jsonl`); tests use a small fixture corpus.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict


def squash(text: str) -> str:
    """Collapse every whitespace run to one space and casefold."""
    return " ".join(text.split()).casefold()


def is_verbatim(quote: str, text: str) -> bool:
    """True when `quote` appears word for word in `text`.

    The rule (shared by the gold check and citation precision): whitespace runs collapse to one
    space and case is ignored, nothing else is forgiven: no elision, no typography folding, no
    fuzzy matching. An empty quote never matches.
    """
    q = squash(quote)
    return bool(q) and q in squash(text)


class CorpusRecord(BaseModel):
    """One citable record of raw history, as of the time it is visible to a system."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str  # rfc | pr | issue | review | comment | commit
    title: str = ""
    text: str = ""
    url: str | None = None
    date: dt.date | None = None  # merge date for a Change, creation date otherwise; None = always visible
    number: int | None = None  # GitHub number for a pull request or an issue
    labels: list[str] = []
    paths: list[str] = []  # files a Change touched, or the file an RFC lives in
    commits: list[str] = []  # commit SHAs a Change consists of

    @property
    def source_text(self) -> str:
        """What quotes are checked against: the title and the full text."""
        return f"{self.title}\n\n{self.text}" if self.title else self.text

    def visible(self, as_of: dt.date | None, exclude: frozenset[str] = frozenset()) -> bool:
        """Whether a system answering as of `as_of`, with `exclude` ablated, may see this record."""
        if self.id in exclude:
            return False
        return as_of is None or self.date is None or self.date <= as_of


class Corpus(Protocol):
    def records(self) -> Iterable[CorpusRecord]:
        """Every record that can be enumerated (some sources can only be looked up)."""
        ...

    def get(self, node_id: str) -> CorpusRecord | None:
        """The record a node id names, or None when it names nothing."""
        ...


class MemoryCorpus:
    def __init__(self, records: Iterable[CorpusRecord]):
        self._by_id: dict[str, CorpusRecord] = {}
        for record in records:
            if record.id in self._by_id:
                raise ValueError(f"duplicate corpus record id {record.id!r}")
            self._by_id[record.id] = record

    @classmethod
    def from_jsonl(cls, path: Path) -> MemoryCorpus:
        lines = path.read_text(encoding="utf-8").splitlines()
        return cls(CorpusRecord.model_validate(json.loads(line)) for line in lines if line.strip())

    def records(self) -> Iterator[CorpusRecord]:
        return iter(self._by_id.values())

    def get(self, node_id: str) -> CorpusRecord | None:
        return self._by_id.get(node_id)


class LayeredCorpus:
    """Several corpora seen as one: lookups try each in order."""

    def __init__(self, *layers: Corpus):
        self.layers = layers

    def records(self) -> Iterator[CorpusRecord]:
        for layer in self.layers:
            yield from layer.records()

    def get(self, node_id: str) -> CorpusRecord | None:
        for layer in self.layers:
            if (record := layer.get(node_id)) is not None:
                return record
        return None


def write_jsonl(path: Path, records: Iterable[CorpusRecord]) -> None:
    path.write_text("".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8")
