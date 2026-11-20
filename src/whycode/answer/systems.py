"""Our system on the scoreboard (`whycode-eval run --systems ...`, see eval/README.md "Plugging in a system").

    --systems ours=whycode.answer.systems:ours,\
              ours-without-supersession=whycode.answer.systems:ours_without_supersession

Both answer `Query -> Answer` through `AnswerEngine.why`, honouring the whole query: `as_of` (history after it is
invisible, so the graph must be built through the end of the Held-out Window, `whycode build --cutoff <window
end>`) and `exclude` (those records, and everything that rests on them, are absent). The second is the ablation
the spec asks for: the same engine, models and graph, with every Decision treated as live.

Configuration (Neo4j, composer) comes from the environment, as for `why-mcp` (`whycode.config`).
"""

from __future__ import annotations

from collections.abc import Mapping

from whycode.answer.engine import AnswerEngine
from whycode.contract import Answer
from whycode.eval.runner import Query, System


def scoreboard_system(name: str, engine: AnswerEngine, models: Mapping[str, str] | None = None) -> System:
    def run(query: Query) -> Answer:
        anchor = query.anchor.id if query.anchor else query.question
        return engine.why(anchor, as_of=query.as_of, exclude=query.exclude)

    return System(name, run, dict(models or {}))


def ours(ctx) -> System:
    """`whycode-eval` factory: our system, configured from the environment (`ctx` is the scoreboard's
    `SystemContext`; our system reads the graph, not the corpus)."""
    return _from_environment("ours", supersession=True)


def ours_without_supersession(ctx) -> System:
    """`whycode-eval` factory: the same system with every Decision treated as live (the ablation)."""
    return _from_environment("ours-without-supersession", supersession=False)


def _from_environment(name: str, supersession: bool) -> System:
    from whycode.answer.patterns import GraphReader
    from whycode.config import Settings
    from whycode.llm import COMPOSER_MODEL

    settings = Settings.from_env()
    reader = GraphReader(settings.driver(), settings.neo4j_database)
    reader.selfcheck()
    engine = AnswerEngine(reader, settings.composer_impl(), supersession=supersession)
    answer_model = COMPOSER_MODEL if settings.composer == "anthropic" else "template"
    return scoreboard_system(name, engine, {"answer": answer_model})
