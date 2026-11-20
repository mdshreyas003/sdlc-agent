"""Our system on the scoreboard (`whycode-eval run --systems ...`, see eval/README.md "Plugging in a system").

    --systems ours=whycode.answer.systems:ours,\
              ours-without-supersession=whycode.answer.systems:ours_without_supersession

Both answer `Query -> Answered` through `AnswerEngine.why`, with the usage of every model call the answer took
(the entity-matching step, the composer; a cached response reports what it cost to make), honouring the whole
query: `as_of` (history after it is invisible, so the graph must be built through the end of the Held-out Window:
`whycode build --cutoff <window end>` for the fixture, plus `--history github --window-commit <last commit by the
window end>` for the real slice, whose code index stays at the cutoff commit) and `exclude` (those records, and
everything that rests on them, are absent). The second is the ablation
the spec asks for: the same engine, models and graph, with every Decision treated as live.

Configuration (Neo4j, composer) comes from the environment, as for `why-mcp` (`whycode.config`).
"""

from __future__ import annotations

from collections.abc import Mapping

from whycode.answer.engine import AnswerEngine
from whycode.eval.runner import Answered, Query, System
from whycode.llm import Usage, metered


def scoreboard_system(name: str, engine: AnswerEngine, models: Mapping[str, str] | None = None) -> System:
    def run(query: Query) -> Answered:
        anchor = query.anchor.id if query.anchor else query.question
        with metered() as calls:  # every model call the answer took: entity matching, composing
            answer = engine.why(anchor, as_of=query.as_of, exclude=query.exclude)
        return Answered(answer, Usage(calls=list(calls)))

    return System(name, run, dict(models or {}))


def ours(ctx) -> System:
    """`whycode-eval` factory: our system, configured from the environment (`ctx` is the scoreboard's
    `SystemContext`; our system reads the graph, not the corpus)."""
    return _from_environment("ours", supersession=True)


def ours_without_supersession(ctx) -> System:
    """`whycode-eval` factory: the same system with every Decision treated as live (the ablation)."""
    return _from_environment("ours-without-supersession", supersession=False)


def _from_environment(name: str, supersession: bool) -> System:
    from whycode.config import Settings
    from whycode.llm import COMPOSER_MODEL

    settings = Settings.from_env()
    engine = settings.answer_engine(settings.reader(), supersession=supersession)
    answer_model = settings.model(COMPOSER_MODEL) if settings.composer == "anthropic" else "template"
    return scoreboard_system(name, engine, {"answer": answer_model})
