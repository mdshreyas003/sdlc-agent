"""Baseline: the answering model alone, with no retrieval and no tools.

It gets the question (and the Code Entity, when the gold question names one) and the date the answer must hold
at, and answers from what it already knows, with the committed prompt `eval/prompts/llm_alone.md`. Nothing from
the corpus reaches it, so `exclude` holds trivially; `as_of` it can only honour by being told. Its node ids and
quotes go into the Answer unverified, so citation precision shows how much of what it cites from memory is real.
"""

from __future__ import annotations

from whycode.eval.baselines import BaselineAnswer, render_query, to_answer
from whycode.eval.corpus import Corpus
from whycode.eval.models import StructuredModel
from whycode.eval.runner import Answered, Query, System


class LlmAlone:
    name = "llm-alone"

    def __init__(self, corpus: Corpus, model: StructuredModel, prompt: str, answer_model: str):
        self.corpus, self.model, self.prompt, self.answer_model = corpus, model, prompt, answer_model

    def system(self) -> System:
        return System(self.name, self, {"answer": self.answer_model})

    def __call__(self, query: Query) -> Answered:
        when = (f"\nAnswer as of {query.as_of.isoformat()}: ignore anything that happened after that date."
                if query.as_of else "\nAnswer with everything you know, up to today.")
        parsed = self.model.parse(system=self.prompt, user=render_query(query) + when, output=BaselineAnswer)
        return Answered(to_answer(parsed.value, query, self.corpus.get), parsed.usage)
