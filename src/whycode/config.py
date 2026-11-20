"""Configuration from environment variables, and the composition root's factories.

Real clients (Neo4j driver, Anthropic) are only ever built here, from the environment, never at import time
and never in tests.

    NEO4J_URI            bolt://localhost:7687 (AuraDB: neo4j+s://<id>.databases.neo4j.io)
    NEO4J_USERNAME       neo4j
    NEO4J_PASSWORD       (required)
    NEO4J_DATABASE       neo4j
    WHY_CUTOFF           2024-06-30 (ADR-0002); nothing after this date is ingested
    WHY_COMPOSER         anthropic (Opus 5.5) | template (offline, model-free)
    WHY_EXTRACTOR        recorded (fixture recordings, offline) | anthropic (Sonnet 5.5) | none (no Decisions)
                         default: recorded for the fixture history, anthropic for the GitHub history
    WHY_MODEL_CACHE      .cache/models (cached model responses, for reproducible rebuilds)
    ANTHROPIC_API_KEY    needed when WHY_COMPOSER or WHY_EXTRACTOR is anthropic

The real slice (`--history github`, scope in `whycode.history.scope`):

    GITHUB_TOKEN         (or GH_TOKEN; e.g. `export GITHUB_TOKEN=$(gh auth token)`) needed only for requests
                         that are not cached yet
    WHY_GITHUB_CACHE     .cache/github (one file per GitHub response; makes the backfill resumable)
    WHY_CHECKOUT         .cache/cockroach (sparse, blobless checkout of the scoped paths)
    WHY_CUTOFF_COMMIT    d13253527955eaa2da09394b8a2729627ab25c48 (last merge into master before WHY_CUTOFF;
                         change both together)
    WHY_CORPUS           data/corpus.jsonl (the scoreboard corpus written by `build --history github`)
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver, GraphDatabase

from whycode.history.scope import CUTOFF_COMMIT

EXTRACTORS = ("recorded", "anthropic", "none")
JUDGES = ("recorded", "anthropic", "none")  # supersession judge; none: explicit Supersession only


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str
    neo4j_database: str
    cutoff: dt.date
    composer: str
    extractor: str
    model_cache: Path
    extractor_set: bool = False  # WHY_EXTRACTOR was given (otherwise the default depends on the history)
    github_token: str | None = None
    github_cache: Path = Path(".cache/github")
    checkout: Path = Path(".cache/cockroach")
    cutoff_commit: str = CUTOFF_COMMIT
    corpus: Path = Path("data/corpus.jsonl")

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        def get(name: str, default: str) -> str:
            return env.get(name) or default  # an empty line copied from an example counts as unset

        composer, extractor = get("WHY_COMPOSER", "anthropic"), get("WHY_EXTRACTOR", "recorded")
        if composer not in ("anthropic", "template"):
            raise ConfigError(f"WHY_COMPOSER must be anthropic or template, not {composer!r}")
        if extractor not in EXTRACTORS:
            raise ConfigError(f"WHY_EXTRACTOR must be one of {', '.join(EXTRACTORS)}, not {extractor!r}")
        return cls(
            neo4j_uri=get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_username=get("NEO4J_USERNAME", "neo4j"),
            neo4j_password=get("NEO4J_PASSWORD", ""),
            neo4j_database=get("NEO4J_DATABASE", "neo4j"),
            cutoff=dt.date.fromisoformat(get("WHY_CUTOFF", "2024-06-30")),
            composer=composer,
            extractor=extractor,
            model_cache=Path(get("WHY_MODEL_CACHE", ".cache/models")),
            extractor_set=bool(env.get("WHY_EXTRACTOR")),
            github_token=env.get("GITHUB_TOKEN") or env.get("GH_TOKEN") or None,
            github_cache=Path(get("WHY_GITHUB_CACHE", ".cache/github")),
            checkout=Path(get("WHY_CHECKOUT", ".cache/cockroach")),
            cutoff_commit=get("WHY_CUTOFF_COMMIT", CUTOFF_COMMIT),
            corpus=Path(get("WHY_CORPUS", "data/corpus.jsonl")),
        )

    def driver(self) -> Driver:
        if not self.neo4j_password:
            raise ConfigError("NEO4J_PASSWORD is not set")
        driver = GraphDatabase.driver(self.neo4j_uri, auth=(self.neo4j_username, self.neo4j_password),
                                      notifications_min_severity="OFF", connection_acquisition_timeout=30)
        driver.verify_connectivity()
        return driver

    def llm(self):
        import anthropic

        from whycode.llm import LlmClient

        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            raise ConfigError("ANTHROPIC_API_KEY is not set (or use WHY_COMPOSER=template / WHY_EXTRACTOR=recorded)")
        return LlmClient(anthropic.Anthropic(), cache_dir=self.model_cache)

    def proposer(self, extractor: str, cutoff: dt.date | None = None):
        """The Decision proposer for an extractor name (see WHY_EXTRACTOR)."""
        from whycode.decisions import AnthropicDecisionProposer, NoDecisionProposer
        from whycode.llm import EXTRACTION_MODEL

        if extractor == "anthropic":
            return AnthropicDecisionProposer(self.llm(), EXTRACTION_MODEL)
        if extractor == "none":
            return NoDecisionProposer()
        from whycode.fixtures import recorded_proposer

        return recorded_proposer(cutoff or self.cutoff)  # the window's recordings only for a later cutoff

    def judge(self, kind: str):
        """The supersession judge for a kind (JUDGES): Opus 5.5, the fixture's recordings, or None (explicit
        Supersession only)."""
        if kind == "anthropic":
            from whycode.llm import JUDGE_MODEL
            from whycode.supersession import AnthropicSupersessionJudge

            return AnthropicSupersessionJudge(self.llm(), JUDGE_MODEL)
        if kind == "recorded":
            from whycode.fixtures import recorded_judge

            return recorded_judge()
        return None

    def composer_impl(self):
        from whycode.answer.compose import AnthropicComposer, TemplateComposer
        from whycode.llm import COMPOSER_MODEL

        return TemplateComposer() if self.composer == "template" else AnthropicComposer(self.llm(), COMPOSER_MODEL)
