"""Confidence scorer: a pure function from graph properties to High / Medium / Low.

Not how sure the model sounds, but how the answer is grounded:
- each Decision gets a strength from its governs link (hard: the implementing diff touched the code;
  soft: only named in text) and its source (a reviewed PR or a design RFC beats an issue comment), and
  whether a rationale was recorded;
- the answer starts at its strongest Decision that is not superseded (superseded Decisions are history, not
  the reason the code is the way it is now); when every Decision is superseded, it is Low;
- Supersession resting on model judgment caps it at Medium: when any Decision's status (superseded or refined)
  comes from an inferred edge rather than one history states; so does an Anchor the entity-matching step chose
  for a free-form question;
- anything the verifier dropped lowers it one level;
- a refusal is always Low.

The thresholds are a first cut, to be calibrated on the dev split (ticket 03/06).
"""

from __future__ import annotations

from dataclasses import dataclass

from whycode.contract import Confidence

_LEVELS: tuple[Confidence, ...] = ("Low", "Medium", "High")
_REVIEWED_SOURCES = frozenset({"pr", "rfc"})


@dataclass(frozen=True, slots=True)
class DecisionGrounding:
    link: str  # hard | soft
    source: str  # kind of the Discussion: pr | rfc | issue
    has_rationale: bool
    status: str = "live"  # live | superseded | refined
    supersession: str | None = None  # explicit | inferred: what the status rests on, when not live


@dataclass(frozen=True, slots=True)
class ConfidenceInputs:
    decisions: tuple[DecisionGrounding, ...]
    dropped: int = 0
    refused: bool = False
    anchor_matched: bool = False


def _strength(d: DecisionGrounding) -> int:
    if d.link == "hard" and d.source in _REVIEWED_SOURCES and d.has_rationale:
        return 2
    return 1


def score_confidence(inputs: ConfidenceInputs) -> Confidence:
    current = [d for d in inputs.decisions if d.status != "superseded"]
    if inputs.refused or not current:
        return "Low"
    level = max(_strength(d) for d in current)
    if inputs.anchor_matched or any(d.supersession == "inferred" for d in inputs.decisions):
        level = min(level, 1)
    if inputs.dropped:
        level -= 1
    return _LEVELS[max(level, 0)]
