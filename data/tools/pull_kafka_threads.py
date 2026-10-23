"""Rebuild dev@kafka discussion for each pilot KIP via the Pony Mail search API. stdlib only.

Search body text for 'KIP-N', keep messages whose *subject* names the KIP, fetch each full body.
Writes data/raw/KIP-N/dev_thread.jsonl and adds sha256 entries to data/raw/hashes.json.
Run: uv run --no-project python -u data/tools/pull_kafka_threads.py
"""
import hashlib, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

RAW = Path(__file__).resolve().parents[1] / "raw"
KIPS = [98, 129, 405, 447, 500, 595, 630, 679, 848, 890]
API = "https://lists.apache.org/api"
CONF = "https://cwiki.apache.org/confluence/rest/api/content"
# ponytail: subject match only; replies that dropped the KIP tag from the subject are missed


def get(url, tries=4):
    for i in range(tries):
        try:
            return json.loads(urlopen(Request(url, headers={"User-Agent": "hackfront-research/0.1"}), timeout=120).read())
        except Exception as e:
            if i == tries - 1:
                raise
            print("retry", url[-40:], e, flush=True)
            time.sleep(3)


hp = RAW / "hashes.json"
hashes = json.loads(hp.read_text())
summary = {}
for n in KIPS:
    pid = json.loads((RAW / f"KIP-{n}/page.json").read_text())["id"]
    start = get(f"{CONF}/{pid}?expand=history")["history"]["createdDate"][:10]
    q = f"{API}/stats.lua?list=dev&domain=kafka.apache.org&q=KIP-{n}&d=dfr={start}|dto={datetime.now():%Y-%m-%d}"
    res = get(q)
    pat = re.compile(rf"KIP[-\s]?{n}(?!\d)", re.I)
    hit = [e for e in res["emails"] if pat.search(e["subject"].replace("\n", " "))]
    hit.sort(key=lambda e: e["epoch"])
    rows = []
    for e in hit:
        full = get(f"{API}/email.lua?id={e['id']}")
        rows.append({"id": e["id"], "message-id": e["message-id"], "in-reply-to": e["in-reply-to"],
                     "subject": e["subject"], "from": e["from"], "epoch": e["epoch"],
                     "url": f"https://lists.apache.org/thread/{e['mid']}", "body": full.get("body", "")})
        time.sleep(0.2)
    out = RAW / f"KIP-{n}/dev_thread.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf8")
    b = out.read_bytes()
    hashes[f"KIP-{n}/dev_thread.jsonl"] = {"url": q, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b),
        "messages": len(rows), "search_hits": res["hits"], "retrieved": datetime.now(timezone.utc).isoformat()}
    summary[n] = (len(rows), res["hits"])
    print(f"KIP-{n}: {len(rows)} messages with KIP in subject (of {res['hits']} body hits) from {start}", flush=True)
    hp.write_text(json.dumps(hashes, indent=1))
print(summary)
