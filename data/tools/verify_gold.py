"""Check gold questions against the corpus (gate for EVAL-3).

Every gold_evidence url must exist and its quote must appear verbatim (whitespace-normalised) in that artifact.
Usage: verify_gold.py [file.jsonl]   default data/gold/questions.jsonl
"""
import collections
import json
import sys
from pathlib import Path

from gold_lib import index, norm

TIERS = {"A", "B", "C", "T", "N"}  # A one artifact, B several, C ablated copy, T time-adjacency trap, N no evidence exists
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "gold" / "questions.jsonl"
qs = [json.loads(l) for l in path.read_text(encoding="utf8").splitlines() if l.strip()]
ix = index()
ids = {q["id"] for q in qs if "id" in q}
errs = []
for n, q in enumerate(qs, 1):
    tag = q.get("id") or f"#{n}"
    if q.get("tier") not in TIERS or not q.get("question"):
        errs.append(f"{tag}: bad tier or empty question")
    ev = q.get("gold_evidence", [])
    if q.get("tier") in ("A", "B") and not (q.get("gold_facts") and ev):
        errs.append(f"{tag}: answerable question needs gold_facts and gold_evidence")
    if q.get("tier") == "B" and len({e["url"] for e in ev}) < 2:
        errs.append(f"{tag}: tier B needs at least two artifacts")
    if q.get("tier") == "C" and q.get("ablates") not in ids:
        errs.append(f"{tag}: ablates unknown question")
    for e in ev:
        if e["url"] not in ix:
            errs.append(f"{tag}: unknown url {e['url']}")
        elif e.get("quote") and norm(e["quote"]) not in ix[e["url"]]["text"]:
            errs.append(f"{tag}: quote not verbatim in {e['url']}: {e['quote'][:60]}")
print(dict(collections.Counter(q.get("tier") for q in qs)), "total", len(qs),
      "split", dict(collections.Counter(q.get("split") for q in qs)),
      "human_verified", sum(bool(q.get("human_verified")) for q in qs))
print("\n".join(errs) or "gold ok")
sys.exit(bool(errs))
