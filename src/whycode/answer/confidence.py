"""Confidence scorer: a pure function from graph properties to High / Medium / Low.

Not how sure the model sounds, but how the answer is grounded:
- each Decision gets a strength from its governs link (hard: the implementing diff touched the code;
  soft: only named in text) and its source (a reviewed PR or a design RFC beats an issue comment), and
  whether a rationale was recorded;
- the answer starts at its strongest Decision's level;
- anything the verifier dropped lowers it one level;
- a refusal is always Low.

Ticket 04 adds Supersession (an inferred edge ranks below an explicit one). The thresholds are a first cut,
to be calibrated on the dev split (ticket 03/06).
"""

from __future__ import annotations

from dataclasses import dataclass

from whycode.contract import Confidence

_LEVELS: tuple[Confidence, ...] = ("Low", "Medium", "High")
_REVIEWED_SOURCES = frozenset({"pull_request", "rfc"})


@dataclass(frozen=True, slots=True)
class DecisionGrounding:
    link: str  # hard | soft
    source: str  # kind of the Discussion: pull_request | rfc | issue
    has_rationale: bool


@dataclass(frozen=True, slots=True)
class ConfidenceInputs:
    decisions: tuple[DecisionGrounding, ...]
    dropped: int = 0
    refused: bool = False


def _strength(d: DecisionGrounding) -> int:
    if d.link == "hard" and d.source in _REVIEWED_SOURCES and d.has_rationale:
        return 2
    return 1


def score_confidence(inputs: ConfidenceInputs) -> Confidence:
    if inputs.refused or not inputs.decisions:
        return "Low"
    level = max(_strength(d) for d in inputs.decisions)
    if inputs.dropped:
        level -= 1
    return _LEVELS[max(level, 0)]
