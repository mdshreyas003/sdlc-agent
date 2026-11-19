"""Verify: the model proposes, code decides. Runs on the composer's drafts before anything reaches the user.

Rules (ported in spirit from the legacy verifier, see notes: legacy-verifier.md):
- a citation survives only if its node id is in the retrieved evidence, and its quote (if any) is verbatim
  in that node's full text;
- a quoted passage inside a sentence ("...", at least three words) must be verbatim in one of the
  sentence's surviving citations, or the sentence is dropped;
- URLs that are not evidence URLs are removed from the text;
- a sentence left with no citation, or with no text, is dropped.

Every removal is counted in `dropped`; the confidence scorer lowers confidence for any of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from whycode.answer.compose import DraftSentence, EvidenceNode
from whycode.contract import Sentence
from whycode.quotes import is_verbatim

_INLINE_QUOTE = re.compile(r'"([^"]+)"|“([^”]+)”')
_URL = re.compile(r"https?://[^\s\]\)>,\"']+")
MIN_INLINE_QUOTE_WORDS = 3


@dataclass(frozen=True, slots=True)
class Verified:
    sentences: list[Sentence]
    dropped: int


def _norm_url(url: str) -> str:
    return url.split("#", 1)[0].split("?", 1)[0].rstrip(".;:")


def verify(drafts: list[DraftSentence], evidence: list[EvidenceNode]) -> Verified:
    by_id = {node.id: node for node in evidence}
    allowed_urls = {_norm_url(node.url) for node in evidence if node.url}
    dropped = 0
    sentences: list[Sentence] = []
    for draft in drafts:
        cites: list[str] = []
        for cite in draft.cites:
            node = by_id.get(cite.node_id)
            if node is None or (cite.quote.strip() and not is_verbatim(cite.quote, node.text)):
                dropped += 1
                continue
            if cite.node_id not in cites:
                cites.append(cite.node_id)

        def scrub(m: re.Match) -> str:
            nonlocal dropped
            if _norm_url(m.group(0)) in allowed_urls:
                return m.group(0)
            dropped += 1
            return ""

        text = " ".join(_URL.sub(scrub, draft.text).split())
        inline = [q for pair in _INLINE_QUOTE.findall(text) for q in pair if len(q.split()) >= MIN_INLINE_QUOTE_WORDS]
        quoted_ok = all(any(is_verbatim(q, by_id[c].text) for c in cites) for q in inline)
        if not cites or not text or not quoted_ok:
            dropped += 1
            continue
        sentences.append(Sentence(text=text, cites=cites))
    return Verified(sentences=sentences, dropped=dropped)
