"""Baseline: dense vector RAG over the same corpus, with the same answering and embedding models.

Records are cut into overlapping chunks, embedded once (vectors cached on disk by model and
content), and the top-k chunks a system may see (as of the cutoff, minus ablated records) go to
the answering model with the committed prompt `eval/prompts/rag_answer.md`.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from whycode.eval.baselines import BaselineAnswer, refusal, render_query, to_answer
from whycode.eval.corpus import Corpus, CorpusRecord
from whycode.eval.models import EMBEDDING_MODEL, StructuredModel
from whycode.eval.runner import Answered, Query, System

TOP_K = 8
CHUNK_CHARS = 1500  # ~375 tokens: under bge's silent 512-token truncation
CHUNK_OVERLAP = 200


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


class FastEmbedder:
    """The shared local embedding model (fastembed, no API key); downloads once to `cache_dir`."""

    def __init__(self, name: str = EMBEDDING_MODEL, cache_dir: Path | None = None):
        from fastembed import TextEmbedding

        self.name = name
        cache = cache_dir or Path(os.environ.get("FASTEMBED_CACHE_PATH", ".cache/fastembed"))
        self._model = TextEmbedding(name, cache_dir=str(cache))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return np.stack(list(self._model.embed(list(texts), batch_size=64))) if texts else np.zeros((0, 1))

    def embed_query(self, text: str) -> np.ndarray:
        return next(iter(self._model.query_embed([text])))


@dataclass(frozen=True)
class Chunk:
    record_id: str
    text: str


def chunk_record(record: CorpusRecord, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    text = record.source_text
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + size // 2, end)
            end = space if space > 0 else end
        chunks.append(Chunk(record.id, text[start:end].strip()))
        if end >= len(text):
            break
        space = text.find(" ", end - overlap, end)  # restart on a word boundary inside the overlap
        start = space + 1 if space > start else end
    return [c for c in chunks if c.text]


class VectorIndex:
    def __init__(self, records: Iterable[CorpusRecord], embedder: Embedder, cache_dir: Path | None = None):
        self.records = {r.id: r for r in records}
        self.chunks = [c for r in self.records.values() for c in chunk_record(r)]
        self.embedder = embedder
        self.matrix = self._embed(cache_dir)

    def _embed(self, cache_dir: Path | None) -> np.ndarray:
        texts = [c.text for c in self.chunks]
        key = hashlib.sha256("\x00".join([self.embedder.name, *texts]).encode()).hexdigest()[:16]
        path = cache_dir / f"vectors-{self.embedder.name.replace('/', '_')}-{key}.npy" if cache_dir else None
        if path is not None and path.exists():
            return np.load(path)
        matrix = self.embedder.embed_documents(texts)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, matrix)
        return matrix

    def search(self, text: str, k: int, query: Query) -> list[Chunk]:
        if not self.chunks:
            return []
        scores = self.matrix @ self.embedder.embed_query(text)
        found = []
        for i in np.argsort(-scores, kind="stable"):
            chunk = self.chunks[int(i)]
            if self.records[chunk.record_id].visible(query.as_of, query.exclude):
                found.append(chunk)
                if len(found) == k:
                    break
        return found


class VectorRag:
    name = "vector-rag"

    def __init__(self, corpus: Corpus, index: VectorIndex, model: StructuredModel, prompt: str, answer_model: str,
                 top_k: int = TOP_K):
        self.corpus, self.index, self.model, self.prompt = corpus, index, model, prompt
        self.answer_model, self.top_k = answer_model, top_k

    def system(self) -> System:
        return System(self.name, self, {"answer": self.answer_model, "embedding": self.index.embedder.name})

    def __call__(self, query: Query) -> Answered:
        search_text = query.question + (f" {query.anchor.id}" if query.anchor else "")
        chunks = self.index.search(search_text, self.top_k, query)
        if not chunks:
            return Answered(refusal(query, "No passage matched the question."))
        passages = "\n\n".join(self._passage(c) for c in chunks)
        parsed = self.model.parse(system=self.prompt, user=f"{passages}\n\n{render_query(query)}",
                                  output=BaselineAnswer)
        return Answered(to_answer(parsed.value, query, self.corpus.get), parsed.usage)

    def _passage(self, chunk: Chunk) -> str:
        r = self.index.records[chunk.record_id]
        return (f'<passage node_id="{r.id}" kind="{r.kind}" date="{r.date or "unknown"}">\n'
                f"{chunk.text}\n</passage>")
