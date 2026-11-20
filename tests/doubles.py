"""Scripted composers for seam-2 tests: they stand in for the composing model and never call one."""

from __future__ import annotations

from whycode.answer.compose import ComposeRequest, DraftCite, DraftSentence

FABRICATED_ID = "pr:99999"
INVENTED_URL = "https://example.com/made-up-design-doc"

# Sentences the verifier must drop, each for one reason.
CITES_FABRICATED_ID = "A later design review confirmed this choice."
RESTS_ON_PARAPHRASE = "The team settled on backoff after a long debate."
QUOTES_INVENTED_TEXT = 'A reviewer insisted to "never retry a schema change at all".'
DROPPED_SENTENCES = (CITES_FABRICATED_ID, RESTS_ON_PARAPHRASE, QUOTES_INVENTED_TEXT)


class FaithfulComposer:
    """Writes one sentence per Decision, citing the Decision and its Discussion with the real quote, and for a
    superseded or refined Decision also what superseded or refined it."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        out = []
        for d in request.decisions:
            cites = [DraftCite(node_id=d.id), DraftCite(node_id=d.discussion_id, quote=d.quote)]
            text = f"{d.choice} ({d.date.isoformat()})."
            if d.status != "live" and d.superseded_by:
                cites.append(DraftCite(node_id=d.superseded_by))
                text = f"{d.choice} ({d.date.isoformat()}), {d.status} on {d.superseded_at.isoformat()}."
            out.append(DraftSentence(text=text, cites=cites))
        return out


class FabricatingComposer(FaithfulComposer):
    """The faithful sentences plus everything the verifier must strip."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        first = request.decisions[0]
        return [
            *super().compose(request),
            DraftSentence(text=CITES_FABRICATED_ID, cites=[DraftCite(node_id=FABRICATED_ID)]),
            DraftSentence(text=RESTS_ON_PARAPHRASE, cites=[
                DraftCite(node_id=first.discussion_id, quote="The team decided exponential backoff is always better."),
            ]),
            DraftSentence(text=QUOTES_INVENTED_TEXT, cites=[DraftCite(node_id=first.discussion_id)]),
            DraftSentence(text=f"See {INVENTED_URL} for the full design.", cites=[DraftCite(node_id=first.id)]),
        ]


class StaleComposer(FaithfulComposer):
    """The faithful sentences plus one that states every superseded Decision as if it still held."""

    PRESENTS_AS_LIVE = "The schema changer currently follows this Decision."

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        stale = [DraftSentence(text=self.PRESENTS_AS_LIVE,
                               cites=[DraftCite(node_id=d.id), DraftCite(node_id=d.discussion_id, quote=d.quote)])
                 for d in request.decisions if d.status == "superseded"]
        return [*super().compose(request), *stale]


class OnlyFabricationsComposer:
    """Nothing it writes can be verified."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        return [DraftSentence(text=CITES_FABRICATED_ID, cites=[DraftCite(node_id=FABRICATED_ID)])]


class ScriptedJudge:
    """Stands in for the supersession judge: labels pairs by (earlier quote, later quote); everything else is
    unrelated."""

    def __init__(self, labels=None):
        self.labels = labels or {}

    def judge(self, pair):
        from whycode.supersession import Judgment

        label, quote = self.labels.get((pair.earlier.quote, pair.later.quote), ("unrelated", ""))
        return Judgment(label=label, quote=quote, reason=f"scripted {label}")
