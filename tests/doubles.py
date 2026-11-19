"""Scripted composers for seam-2 tests: they stand in for the composing model and never call one."""

from __future__ import annotations

from whycode.answer.compose import ComposeRequest, DraftCite, DraftSentence

FABRICATED_ID = "github:cockroachdb/cockroach#99999"
PARAPHRASED_QUOTE = "The team decided exponential backoff is always better."
INVENTED_INLINE = "never retry a schema change at all"
INVENTED_URL = "https://example.com/made-up-design-doc"


class FaithfulComposer:
    """Writes one sentence per Decision, citing the Decision and its Discussion with the real quote."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        return [
            DraftSentence(text=f"{d.choice} ({d.date.isoformat()}).",
                          cites=[DraftCite(node_id=d.id), DraftCite(node_id=d.discussion_id, quote=d.quote)])
            for d in request.decisions
        ]


class FabricatingComposer(FaithfulComposer):
    """The faithful sentences plus everything the verifier must strip."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        first = request.decisions[0]
        return [
            *super().compose(request),
            DraftSentence(text="A later design review confirmed this choice.", cites=[DraftCite(node_id=FABRICATED_ID)]),
            DraftSentence(text="The team settled on backoff after a long debate.",
                          cites=[DraftCite(node_id=first.discussion_id, quote=PARAPHRASED_QUOTE)]),
            DraftSentence(text=f'A reviewer insisted to "{INVENTED_INLINE}".',
                          cites=[DraftCite(node_id=first.discussion_id)]),
            DraftSentence(text=f"See {INVENTED_URL} for the full design.", cites=[DraftCite(node_id=first.id)]),
        ]


class OnlyFabricationsComposer:
    """Nothing it writes can be verified."""

    def compose(self, request: ComposeRequest) -> list[DraftSentence]:
        return [DraftSentence(text="This was decided in a design review.", cites=[DraftCite(node_id=FABRICATED_ID)])]
