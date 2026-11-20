"""The miniature CockroachDB history: test fixture, offline demo corpus, and the shape ticket 02 scales up.

Story (all in `miniature/`):
- RFC 20151014_online_schema_change (completed) and RFC 20210115_new_schema_changer (draft).
- #98001, a regression: schema change jobs hot-loop on retry. Fixed by #98100, which adds capped exponential
  backoff and the `schemachanger.job.max_retry_backoff` setting (reviews by spilchen, approval by rafiss).
- #101200 makes descriptor validation errors permanent; #101400 (release-blocker) reports the fallout;
  #101450 reverts #101200 ("This reverts commit ...", "Fixes #101400").
- #110500 gates the plan sanity check behind `sql.schemachanger.strict_planning_sanity_check.enabled`;
  its author and approver have been inactive for over a year at the cutoff (departed).
- #104500 makes validation errors permanent again, but only once the upgrade is finalized: it refines #101450.
- RFC 20200909_transactional_schema_changes has `Status: superseded by #59288`, the RFC PR of
  20210115_new_schema_changer, whose statement-phase Decision governs the same function.
- #122400 touches `scbuild.Build` but records no Decision (the ungoverned Anchor).
- After the 2024-06-30 cutoff (the Held-out Window, up to `FIXTURE_WINDOW_END`): PR #127200 lowers the backoff cap
  default to 10s (superseding the 20s Decision of #98100), issue #127000, an RFC, comments, and PR #128000, which
  reverts #104500. None of them may be ingested at the default cutoff.

Recorded responses stand in for the models: `extractions.json` (and `extractions_window.json` for window records)
for Decision extraction, `judgments.json` for the supersession judge.
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
from whycode.supersession import RecordedSupersessionJudge, SupersessionJudge

FIXTURE_DIR = Path(__file__).parent / "miniature"
FIXTURE_REPO = "cockroachdb/cockroach"
FIXTURE_CUTOFF = dt.date(2024, 6, 30)
FIXTURE_WINDOW_END = dt.date(2025, 6, 30)
"""Build with this cutoff to include the Held-out Window (scoreboard runs answer `as_of` the cutoff from it)."""


def fixture_code_index() -> CodeIndex:
    return parse_go_tree(FIXTURE_DIR / "code")


def recorded_proposer(cutoff: dt.date = FIXTURE_CUTOFF) -> RecordedDecisionProposer:
    """Recorded extractions; records inside the Held-out Window have recordings only when the cutoff includes
    them, so a build that leaks them at the default cutoff fails loudly."""
    paths = [FIXTURE_DIR / "extractions.json"]
    if cutoff > FIXTURE_CUTOFF:
        paths.append(FIXTURE_DIR / "extractions_window.json")
    return RecordedDecisionProposer(*paths)


def recorded_judge() -> RecordedSupersessionJudge:
    return RecordedSupersessionJudge(FIXTURE_DIR / "judgments.json")


def fixture_graph(cutoff: dt.date = FIXTURE_CUTOFF, proposer: DecisionProposer | None = None,
                  judge: SupersessionJudge | None = None) -> Graph:
    """Build the fixture graph; by default with the recorded extraction and judge responses (no model, no network)."""
    history = load_history(FixtureHistorySource(FIXTURE_DIR, repo=FIXTURE_REPO), cutoff)
    return build_graph(history, fixture_code_index(), proposer or recorded_proposer(cutoff), judge or recorded_judge())
