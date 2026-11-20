"""Configuration from environment variables, and the composition root's factories.

Real clients (Neo4j driver, Anthropic) are only ever built here, from the environment, never at import time
and never in tests.

    NEO4J_URI            bolt://localhost:7687 (AuraDB: neo4j+s://<id>.databases.neo4j.io)
    NEO4J_USERNAME       neo4j
    NEO4J_PASSWORD       (required)
    NEO4J_DATABASE       neo4j
    WHY_CUTOFF           2024-06-30 (ADR-0002); nothing after this date is ingested
    WHY_COMPOSER         anthropic (Opus 5.5, or WHY_OPENAI_MODEL) | template (offline, model-free). Also picks
                         the entity-matching step for free-form questions: the same model with anthropic; none
                         with template (a question that names no Code Entity exactly is then refused)
    WHY_EXTRACTOR        recorded (fixture recordings, offline) | anthropic (Sonnet 5.5) | none (no Decisions)
                         default: recorded for the fixture history, anthropic for the GitHub history
    WHY_MODEL_CACHE      .cache/models (cached model responses, for reproducible rebuilds)
    WHY_LLM              anthropic (default) | openai: which API every model step above calls (ADR-0004). With
                         openai, the steps named anthropic (composer, extractor, judge, entity matching) all run
                         on WHY_OPENAI_MODEL at OPENAI_BASE_URL instead of Opus/Sonnet
    ANTHROPIC_API_KEY    needed when WHY_LLM is anthropic and WHY_COMPOSER or WHY_EXTRACTOR is anthropic
    OPENAI_BASE_URL      https://api.sarvam.ai/v1 (any OpenAI-compatible server: Sarvam, vLLM, OpenRouter)
    OPENAI_API_KEY       needed when WHY_LLM is openai (for Sarvam, the Sarvam API subscription key)
    WHY_OPENAI_MODEL     sarvam-105b

The real slice (`--history github`, scope in `whycode.history.scope`):

    GITHUB_TOKEN         (or GH_TOKEN; e.g. `export GITHUB_TOKEN=$(gh auth token)`) needed only for requests
                         that are not cached yet
    WHY_GITHUB_CACHE     .cache/github (one file per GitHub response; makes the backfill resumable)
    WHY_CHECKOUT         .cache/cockroach (sparse, blobless checkout of the scoped paths)
    WHY_CUTOFF_COMMIT    d13253527955eaa2da09394b8a2729627ab25c48 (last merge into master before WHY_CUTOFF;
                         change both together). The code index is always read at this commit; a Held-out Window
                         build (`--cutoff` past WHY_CUTOFF) passes `--window-commit` for pull request discovery
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

LLMS = ("anthropic", "openai")
OPENAI_BASE_URL = "https://api.sarvam.ai/v1"
OPENAI_MODEL = "sarvam-105b"
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
    llm_api: str = "anthropic"
    openai_base_url: str = OPENAI_BASE_URL
    openai_model: str = OPENAI_MODEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        def get(name: str, default: str) -> str:
            return env.get(name) or default  # an empty line copied from an example counts as unset

        composer, extractor = get("WHY_COMPOSER", "anthropic"), get("WHY_EXTRACTOR", "recorded")
        if composer not in ("anthropic", "template"):
            raise ConfigError(f"WHY_COMPOSER must be anthropic or template, not {composer!r}")
        if extractor not in EXTRACTORS:
            raise ConfigError(f"WHY_EXTRACTOR must be one of {', '.join(EXTRACTORS)}, not {extractor!r}")
        if (llm_api := get("WHY_LLM", "anthropic")) not in LLMS:
            raise ConfigError(f"WHY_LLM must be one of {', '.join(LLMS)}, not {llm_api!r}")
        return cls(
            llm_api=llm_api,
            openai_base_url=get("OPENAI_BASE_URL", OPENAI_BASE_URL),
            openai_model=get("WHY_OPENAI_MODEL", OPENAI_MODEL),
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

    def reader(self, driver: Driver | None = None):
        """A read-only `GraphReader` over the configured database, every query pattern checked (fails fast)."""
        from whycode.answer.patterns import GraphReader

        reader = GraphReader(driver or self.driver(), self.neo4j_database)
        reader.selfcheck()
        return reader

    def model(self, anthropic_model: str) -> str:
        """The model a step runs on: its Claude model, or WHY_OPENAI_MODEL with WHY_LLM=openai."""
        return self.openai_model if self.llm_api == "openai" else anthropic_model

    def llm(self):
        import anthropic

        from whycode.llm import LlmClient

        if self.llm_api == "openai":
            return LlmClient(openai_client(self.openai_base_url), cache_dir=self.model_cache)
        if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            raise ConfigError("ANTHROPIC_API_KEY is not set (or use WHY_COMPOSER=template / WHY_EXTRACTOR=recorded)")
        return LlmClient(anthropic.Anthropic(), cache_dir=self.model_cache)

    def proposer(self, extractor: str, cutoff: dt.date | None = None):
        """The Decision proposer for an extractor name (see WHY_EXTRACTOR)."""
        from whycode.decisions import AnthropicDecisionProposer, NoDecisionProposer
        from whycode.llm import EXTRACTION_MODEL

        if extractor == "anthropic":
            return AnthropicDecisionProposer(self.llm(), self.model(EXTRACTION_MODEL))
        if extractor == "none":
            return NoDecisionProposer()
        from whycode.fixtures import recorded_proposer

        return recorded_proposer(cutoff or self.cutoff)  # the window's recordings only for a later cutoff

    def judge(self, kind: str):
        """The supersession judge for a kind (JUDGES): Opus 5.5 (or WHY_OPENAI_MODEL), the fixture's recordings,
        or None (explicit Supersession only)."""
        if kind == "anthropic":
            from whycode.llm import JUDGE_MODEL
            from whycode.supersession import AnthropicSupersessionJudge

            return AnthropicSupersessionJudge(self.llm(), self.model(JUDGE_MODEL))
        if kind == "recorded":
            from whycode.fixtures import recorded_judge

            return recorded_judge()
        return None

    def matcher_impl(self):
        """The entity-matching step for free-form questions: the composer's model with the anthropic composer,
        else None."""
        if self.composer != "anthropic":
            return None
        from whycode.answer.resolve import AnthropicEntityMatcher
        from whycode.llm import MATCHER_MODEL

        return AnthropicEntityMatcher(self.llm(), self.model(MATCHER_MODEL))

    def answer_engine(self, reader, supersession: bool = True):
        """The AnswerEngine every interface uses (MCP, `whycode why`, the human view, the scoreboard)."""
        from whycode.answer.engine import AnswerEngine

        return AnswerEngine(reader, self.composer_impl(), supersession=supersession, matcher=self.matcher_impl())

    def composer_impl(self):
        from whycode.answer.compose import AnthropicComposer, TemplateComposer
        from whycode.llm import COMPOSER_MODEL

        if self.composer == "template":
            return TemplateComposer()
        return AnthropicComposer(self.llm(), self.model(COMPOSER_MODEL))


def openai_client(base_url: str = OPENAI_BASE_URL):
    """An OpenAI SDK client for an OpenAI-compatible server, its key from OPENAI_API_KEY."""
    import openai

    if not os.environ.get("OPENAI_API_KEY"):
        raise ConfigError("OPENAI_API_KEY is not set (or use WHY_COMPOSER=template / WHY_EXTRACTOR=recorded)")
    return openai.OpenAI(base_url=base_url)
