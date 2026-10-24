"""Pull the pilot slice: 10 KIPs plus one hop of links. stdlib only.

Writes data/raw/<id>/... and merges sha256 per file + retrieval time into data/raw/hashes.pull.json.
Promote: copy reviewed entries from data/raw/hashes.pull.json into data/raw/hashes.json by hand (add kind/fetch), then verify with fetch_kip_raw.py.
Run: python data/tools/pull_pilot.py
"""
import hashlib, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

RAW = Path(__file__).resolve().parents[1] / "raw"
KIPS = [98, 129, 405, 447, 500, 595, 630, 679, 848, 890]
CONF = "https://cwiki.apache.org/confluence/rest/api/content"
HOPS_PER_RECORD = 6
# one hop only to these hosts; everything else is recorded as a link but not fetched
ALLOWED = {"lists.apache.org", "mail-archives.apache.org", "issues.apache.org", "github.com"}
PULL = RAW / "hashes.pull.json"  # pull output only; never read or write the curated hashes.json
hashes = {}  # loaded from PULL in __main__ only, so importing link_candidates() reads nothing


def get(url, accept=None):
    req = Request(url, headers={"User-Agent": "hackfront-research/0.1", **({"Accept": accept} if accept else {})})
    with urlopen(req, timeout=30) as r:
        return r.read()


def save(rec, name, data, url):
    p = RAW / rec / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    hashes[f"{rec}/{name}"] = {"url": url, "sha256": hashlib.sha256(data).hexdigest(),
                               "bytes": len(data), "retrieved": datetime.now(timezone.utc).isoformat()}


def hop_url(u):
    """Map a link to a fetchable URL, or None."""
    h = urlparse(u).netloc
    if h not in ALLOWED or "thread.html" in u:  # old lists.apache.org urls are JS stubs, not fetchable
        return None
    if h == "github.com" and not re.search(r"/(issues|pull)/\d+", u):
        return None
    m = re.match(r"https://lists\.apache\.org/thread/(\w+)", u)
    if m:
        return f"https://lists.apache.org/api/thread.lua?id={m[1]}"  # ponytail: endpoint unverified, failure is logged
    m = re.match(r"https://github\.com/([\w.-]+/[\w.-]+)/(issues|pull)/(\d+)", u)
    if m:
        return f"https://api.github.com/repos/{m[1]}/{'issues' if m[2]=='issues' else 'pulls'}/{m[3]}"
    m = re.match(r"https://issues\.apache\.org/jira/browse/([A-Z]+-\d+)", u)
    if m:
        return f"https://issues.apache.org/jira/rest/api/2/issue/{m[1]}?expand=renderedFields&fields=summary,description,comment,issuelinks,status,created,resolutiondate"
    return u


def link_candidates(text):
    """All links in a record's text, plus the ones worth one hop (also used by fetch_kip_raw.py)."""
    links = list(dict.fromkeys(re.findall(r"https?://[^\s<>\")\]]+", text)))
    jira = [f"https://issues.apache.org/jira/browse/{k}" for k in dict.fromkeys(re.findall(r"\b(KAFKA-\d+)\b", text))]
    cand = [u.rstrip(".,;") for u in links if hop_url(u)] + jira
    return links, list(dict.fromkeys(cand))


def one_hop(rec, text):
    links, cand = link_candidates(text)
    (RAW / rec).mkdir(parents=True, exist_ok=True)
    (RAW / rec / "links.json").write_text(json.dumps({"all": links, "candidates": cand}, indent=1))
    for i, u in enumerate(cand[:HOPS_PER_RECORD]):
        try:
            save(rec, f"hop{i}.bin", get(hop_url(u)), u)
        except Exception as e:  # keep going; failures are data
            print(f"  hop FAIL {u}: {e}", file=sys.stderr)
        time.sleep(0.5)


def kip(n):
    rec = f"KIP-{n}"
    res = json.loads(get(f"{CONF}/{ids[n]}?expand=body.storage,version"))
    save(rec, "page.json", json.dumps(res).encode(), res["_links"]["self"])
    one_hop(rec, res["body"]["storage"]["value"])


def kip_titles():
    out = {}
    for n in KIPS:
        q = quote(f'space=KAFKA AND type=page AND title ~ "KIP-{n}"')
        for r in json.loads(get(f"{CONF}/search?cql={q}&limit=10"))["results"]:
            if re.match(rf"KIP-{n}[:\s-]", r["title"]):
                out[n] = r["id"]
    return out


if __name__ == "__main__":
    if PULL.exists():
        hashes.update(json.loads(PULL.read_text()))
    tmap = kip_titles()
    ids = tmap
    print("KIPs found:", sorted(tmap), "missing:", sorted(set(KIPS) - set(tmap)))
    for n in sorted(tmap):
        print("KIP", n); kip(n)
    PULL.write_text(json.dumps(hashes, indent=1))
    print("files:", len(hashes))
