"""Write one KIP's material as a single text file for drafting gold questions.

Layout: the KIP page (the answer key, NOT in the system's graph), then every corpus artifact for that KIP with its
citation url. Run: uv run --no-project python data/tools/dump_kip.py N OUTDIR
"""
import html
import json
import re
import sys
from pathlib import Path

from gold_lib import index, norm

n, out = sys.argv[1], Path(sys.argv[2])
raw = Path(__file__).resolve().parents[1] / "raw" / f"KIP-{n}"
page = json.loads((raw / "page.json").read_text(encoding="utf8"))["body"]["storage"]["value"]
keys = set()
for p in raw.glob("hop*.bin"):
    try:
        j = json.loads(p.read_bytes())
    except ValueError:
        continue
    if isinstance(j, dict) and j.get("key"):
        keys.add(j["key"])
shas = {json.loads(p.read_bytes())["sha"] for p in raw.glob("commit-*.json")}
prs = {str(json.loads(p.read_bytes())["number"]) for p in raw.glob("pr[0-9]*.json")}

lines = [f"# KIP-{n} ANSWER KEY (not in the system's graph; use only to see what the reason is)\n",
         norm(html.unescape(re.sub(r"<[^>]+>", " ", page)))[:14000], "\n\n# CORPUS ARTIFACTS (cite these urls)\n"]
for url, a in sorted(index().items(), key=lambda kv: kv[1]["when"] or ""):
    mine = (f"/archives/KIP{n}/" in url or any(f"/browse/{k}" in url for k in keys)
            or any(s in url for s in shas) or any(url.endswith(f"/pull/{p}") for p in prs))
    if mine:
        lines.append(f"\n## {url}\n{a['kind']} {a['when']}\n{a['text'][:3500]}")
out.mkdir(parents=True, exist_ok=True)
(out / f"KIP-{n}.txt").write_text("\n".join(lines), encoding="utf8")
print(n, len(lines) - 3, "artifacts")
