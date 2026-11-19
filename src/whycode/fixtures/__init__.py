"""The miniature CockroachDB history: test fixture, offline demo corpus, and the shape ticket 02 scales up.

Story (all in `miniature/`):
- RFC 20151014_online_schema_change (completed) and RFC 20210115_new_schema_changer (draft).
- #98001, a regression: schema change jobs hot-loop on retry. Fixed by #98100, which adds capped exponential
  backoff and the `schemachanger.job.max_retry_backoff` setting (reviews by spilchen, approval by rafiss).
- #101200 makes descriptor validation errors permanent; #101400 (release-blocker) reports the fallout;
  #101450 reverts #101200 ("This reverts commit ...", "Fixes #101400").
- #110500 gates the plan sanity check behind `sql.schemachanger.strict_planning_sanity_check.enabled`;
  its author and approver have been inactive for over a year at the cutoff (departed).
- #122400 touches `scbuild.Build` but records no Decision (the ungoverned Anchor).
- After the 2024-06-30 cutoff: PR #127200, issue #127000, an RFC and a comment, none of which may be ingested.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from whycode.build import build_graph
from whycode.codeindex import CodeIndex
from whycode.codeindex.go import parse_go_tree
from whycode.decisions import DecisionProposer, RecordedDecisionProposer
from whycode.graph import Graph
from whycode.history import load_history
from whycode.history.fixture import FixtureHistorySource

FIXTURE_DIR = Path(__file__).parent / "miniature"
FIXTURE_REPO = "cockroachdb/cockroach"
FIXTURE_CUTOFF = dt.date(2024, 6, 30)


def fixture_code_index() -> CodeIndex:
    return parse_go_tree(FIXTURE_DIR / "code")


def recorded_proposer() -> RecordedDecisionProposer:
    return RecordedDecisionProposer(FIXTURE_DIR / "extractions.json")


def fixture_graph(cutoff: dt.date = FIXTURE_CUTOFF, proposer: DecisionProposer | None = None) -> Graph:
    """Build the fixture graph; by default with the recorded extraction responses (no model, no network)."""
    history = load_history(FixtureHistorySource(FIXTURE_DIR, repo=FIXTURE_REPO), cutoff)
    return build_graph(history, fixture_code_index(), proposer or recorded_proposer())
