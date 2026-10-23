"""Write data/gold/REVIEW.md: a readable page of every gold question for the human check (tier C twins are skipped)."""
import json
from pathlib import Path

g = Path(__file__).resolve().parents[1] / "gold"
out = ["# Gold review\n", "For each question: is it a real, non-trivial *why*? Do the facts follow from the quotes? "
       "Tell Claude the ids to fix or drop; ids you approve get `human_verified=true`.\n"]
for l in (g / "questions.jsonl").read_text(encoding="utf8").splitlines():
    q = json.loads(l)
    if q["tier"] == "C":
        continue
    out += [f"\n## {q['id']} · tier {q['tier']} · KIP-{q['kip']} · {q['split']}\n", f"**{q['question']}**\n"]
    out += [f"- fact: {f}" for f in q["gold_facts"]]
    out += [f"- evidence: <{e['url']}>\n  > {e['quote']}" for e in q["gold_evidence"]]
    out.append(f"- note: {q.get('note', '')}")
(g / "REVIEW.md").write_text("\n".join(out) + "\n", encoding="utf8")
print("ok")
