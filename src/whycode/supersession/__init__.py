"""Supersession detector: which later Decisions supersede or refine earlier ones.

Edges go from the later node to the earlier Decision: `SUPERSEDES` (the earlier one is dead) or `REFINES` (it
is narrowed or extended, so partly live). Every edge carries `basis` (explicit | inferred), the verbatim `quote`
that states or justifies it, `source` (the record whose text holds that quote), a `locator` in that record, and
`observed_at` (when the later node took effect).

**Explicit** Supersession is parsed with no model (`origin: stated`):
- a revert: Change R reverts Change P (`Revert "<title>"`, `This reverts commit <sha>`; see `whycode.linker`),
  so every Decision of P is superseded;
- an RFC `Status:` of superseded, obsolete or rejected: every Decision of that RFC is superseded. For
  `superseded by #N` the later record is the RFC whose `RFC PR` is N (or the record N, when ingested); otherwise
  (obsolete, rejected, or a successor that was not ingested) the RFC itself declares its Decisions dead;
- `supersedes #N` / `superseded by #N` written in a pull request's or issue's title or description.

Edges start at Decisions whenever they can (the schema's Decision -> supersedes -> Decision): the superseding node
of an explicit case is each Decision of the later record that governs a Code Entity the earlier Decision governs.
A record starts the edge only when the later record yields no such Decision (a revert that records no Decision of
its own, a successor whose Decisions are about other code), or when an RFC declares its own Decisions dead.

**Inferred** Supersession (`origin: derived`): pairs of Decisions that govern the same Code Entity, where B took
effect later than A and comes from another Discussion, are candidates (`candidate_pairs`: the most specific code
both govern, so two Decisions on different functions of one file are not paired; at most `MAX_LATER` later
Decisions per Decision, configurable). The build reports how many pairs the judge was asked about and how many it
was not, by reason (`PairingReport`). The judge (Opus 5.5
behind the `SupersessionJudge` seam) labels it supersedes / refines / unrelated with a quote; the model proposes,
code decides: a label becomes an edge only when its quote has at least `MIN_DECISION_QUOTE_WORDS` words and is
verbatim in B's Discussion. Pairs that need no judgment are skipped: those already linked explicitly, and those
whose A was already explicitly superseded when B took effect.

`judge_report` scores the judge against the explicit cases (`whycode supersession-report`).

One module per job: `explicit` (parsing), `pairs` (candidate pairs, inferred edges, what the judge was asked),
`judge` (the model seam, its prompt and adapters, the quote rule), `report` (the judge against explicit cases);
`index` holds what they share about the graph.

Known limits: a revert of a revert does not bring the reverted Decisions back; an RFC's status comes from its
text as of the build, so the status edge is dated by the superseding RFC (or, failing that, the RFC itself).
"""

from __future__ import annotations

from collections.abc import Iterable

from whycode.discussions import Discussion
from whycode.graph import Edge, Graph
from whycode.history.records import History
from whycode.supersession.explicit import explicit_supersessions
from whycode.supersession.index import EXPLICIT, INFERRED
from whycode.supersession.judge import (
    AnthropicSupersessionJudge,
    CandidatePair,
    DecisionSummary,
    Judgment,
    RecordedSupersessionJudge,
    SupersessionJudge,
)
from whycode.supersession.pairs import MAX_LATER, CandidatePairs, PairingReport, candidate_pairs, inferred_supersessions
from whycode.supersession.report import JudgeReport, judge_report

__all__ = ["EXPLICIT", "INFERRED", "MAX_LATER", "AnthropicSupersessionJudge", "CandidatePair", "CandidatePairs",
           "DecisionSummary", "JudgeReport", "Judgment", "PairingReport", "RecordedSupersessionJudge",
           "SupersessionJudge", "candidate_pairs", "explicit_supersessions", "inferred_supersessions", "judge_report",
           "supersessions"]


def supersessions(graph: Graph, history: History, discussions: Iterable[Discussion], judge: SupersessionJudge | None,
                  max_later: int | None = MAX_LATER) -> tuple[list[Edge], PairingReport | None]:
    """Explicit Supersession always; inferred Supersession when a judge is given (with what it was asked)."""
    discussions = list(discussions)
    explicit = explicit_supersessions(graph, history, discussions)
    if judge is None:
        return explicit, None
    inferred, report = inferred_supersessions(graph, discussions, explicit, judge, max_later)
    return explicit + inferred, report
