"""Configuration from environment variables, and the composition root's factories.

Real clients (Neo4j driver, Anthropic) are only ever built here, from the environment, never at import time
and never in tests.

    NEO4J_URI            bolt://localhost:7687 (AuraDB: neo4j+s://<id>.databases.neo4j.io)
    NEO4J_USERNAME       neo4j
    NEO4J_PASSWORD       (required)
    NEO4J_DATABASE       neo4j
    WHY_CUTOFF           2024-06-30 (ADR-0002); nothing after this date is ingested
    WHY_COMPOSER         anthropic (Opus 5.5) | template (offline, model-free)
    WHY_EXTRACTOR        recorded (fixture recordings, offline) | anthropic (Sonnet 5.5)
    WHY_MODEL_CACHE      .cache/models (cached model responses, for reproducible rebuilds)
    ANTHROPIC_API_KEY    needed when WHY_COMPOSER or WHY_EXTRACTOR is anthropic
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver, GraphDatabase


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

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        def get(name: str, default: str) -> str:
            return env.get(name) or default  # an empty line copied from an example counts as unset

        composer, extractor = get("WHY_COMPOSER", "anthropic"), get("WHY_EXTRACTOR", "recorded")
        if composer not in ("anthropic", "template"):
            raise ConfigError(f"WHY_COMPOSER must be anthropic or template, not {composer!r}")
        if extractor not in ("anthropic", "recorded"):
            raise ConfigError(f"WHY_EXTRACTOR must be anthropic or recorded, not {extractor!r}")
        return cls(
            neo4j_uri=get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_username=get("NEO4J_USERNAME", "neo4j"),
            neo4j_password=get("NEO4J_PASSWORD", ""),
            neo4j_database=get("NEO4J_DATABASE", "neo4j"),
            cutoff=dt.date.fromisoformat(get("WHY_CUTOFF", "2024-06-30")),
            composer=composer,
            extractor=extractor,
            model_cache=Path(get("WHY_MODEL_CACHE", ".cache/models")),
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

    def composer_impl(self):
        from whycode.answer.compose import AnthropicComposer, TemplateComposer
        from whycode.llm import COMPOSER_MODEL

        return TemplateComposer() if self.composer == "template" else AnthropicComposer(self.llm(), COMPOSER_MODEL)
