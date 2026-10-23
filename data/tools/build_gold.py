"""Assemble data/gold/questions.jsonl from per-KIP drafts: ids, ablated copies (tier C), dev/test split.

Every second answerable question gets a tier-C twin: same question, `ablates` = the original id, whose gold
artifacts the runner deletes from the graph, so the only right answer is "not established". Twins share the original's
split. Split is a stable hash of the id: about 30% dev, the rest test (touch test once; see EVAL_PLAN.md).
Run: uv run --no-project python data/tools/build_gold.py DRAFT_DIR
"""
import hashlib
import json
import sys
from pathlib import Path

draft = Path(sys.argv[1])
out = Path(__file__).resolve().parents[1] / "gold" / "questions.jsonl"
rows = [json.loads(l) for f in sorted(draft.glob("KIP-*.jsonl"), key=lambda p: int(p.stem[4:]))
        for l in f.read_text(encoding="utf8").splitlines() if l.strip()]
split = lambda i: "dev" if int(hashlib.sha1(i.encode()).hexdigest(), 16) % 100 < 30 else "test"  # noqa: E731
final, answerable = [], 0
for n, r in enumerate(rows, 1):
    qid = f"Q{n:03d}"
    final.append({"id": qid, **r, "answerable": r["tier"] in ("A", "B"), "split": split(qid), "human_verified": False})
    if r["tier"] in ("A", "B"):
        answerable += 1
        if answerable % 2 == 1:
            final.append({"id": f"{qid}C", "kip": r["kip"], "tier": "C", "question": r["question"], "ablates": qid,
                          "answerable": False, "gold_facts": [], "gold_evidence": r["gold_evidence"],
                          "split": split(qid), "human_verified": False,
                          "note": "twin of " + qid + " with its gold artifacts removed from the graph"})
out.parent.mkdir(exist_ok=True)
out.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in final), encoding="utf8")
print(len(final), "questions ->", out)
