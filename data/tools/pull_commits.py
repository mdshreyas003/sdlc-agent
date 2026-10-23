"""Pull the apache/kafka PRs and merge commits that fix each KIP's most-cited Jira keys. stdlib only.

For KIP-N: take the KEYS_PER_KIP most-mentioned KAFKA-* keys in its raw files, find PRs whose title
carries the key, keep PRS_PER_KEY, fetch each PR and its merge commit (with patch).
Writes data/raw/KIP-N/prs.json (key -> PR numbers) and pr<N>.json / commit-<sha7>.json,
and merges sha256 entries into data/raw/hashes.json. Re-runnable: existing files are skipped.
GitHub unauthenticated limit is 60 calls/hour; set GITHUB_TOKEN for more.
Run: uv run --no-project python data/tools/pull_commits.py
"""
import hashlib, json, os, re, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RAW = Path(__file__).resolve().parents[1] / "raw"
KEYS_PER_KIP, PRS_PER_KEY = 3, 1
API = "https://api.github.com"
H = {"User-Agent": "hackfront-research/0.1", "Accept": "application/vnd.github+json"}
if os.environ.get("GITHUB_TOKEN"):
    H["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
hashes = json.loads((RAW / "hashes.json").read_text())


def get(url):
    try:
        with urlopen(Request(url, headers=H), timeout=30) as r:
            return r.read()
    except HTTPError as e:
        if e.code in (403, 429):
            sys.exit(f"rate limited at {url}; wait and re-run (finished files are kept)")
        raise


def save(rec, name, data, url):
    (RAW / rec / name).write_bytes(data)
    hashes[f"{rec}/{name}"] = {"url": url, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                               "retrieved": datetime.now(timezone.utc).isoformat()}
    (RAW / "hashes.json").write_text(json.dumps(hashes, indent=1))


def top_keys(rec):
    text = "".join(p.read_bytes().decode("utf8", "replace") for p in (RAW / rec).glob("*")
                   if p.name in ("page.json", "links.json") or p.suffix == ".bin")
    return [k for k, _ in Counter(re.findall(r"\bKAFKA-\d+\b", text)).most_common(KEYS_PER_KIP)]


def pull(rec):
    out = RAW / rec / "prs.json"
    if out.exists():
        return
    found = {}
    for key in top_keys(rec):
        q = f"repo:apache/kafka is:pr is:merged {key} in:title"
        url = f"{API}/search/issues?q={q.replace(' ', '+')}&per_page={PRS_PER_KEY}"
        time.sleep(7)  # search API: 10 calls/minute unauthenticated
        nums = [i["number"] for i in json.loads(get(url))["items"]]
        found[key] = nums
        if not nums:  # old work often landed without a PR: fall back to commit messages naming the key
            curl = f"{API}/search/commits?q=repo:apache/kafka+{key}&per_page=1"
            time.sleep(7)
            for c in json.loads(get(curl))["items"]:
                u = f"{API}/repos/apache/kafka/commits/{c['sha']}"
                save(rec, f"commit-{c['sha'][:7]}.json", get(u), u)
                found[key] = [c["sha"][:7]]
        for n in [n for n in nums if isinstance(n, int)]:
            purl = f"{API}/repos/apache/kafka/pulls/{n}"
            pr = get(purl)
            save(rec, f"pr{n}.json", pr, purl)
            sha = json.loads(pr).get("merge_commit_sha")
            if sha:
                curl = f"{API}/repos/apache/kafka/commits/{sha}"
                save(rec, f"commit-{sha[:7]}.json", get(curl), curl)
        print(rec, key, "->", nums)
    out.write_text(json.dumps(found, indent=1))  # written last: marks the KIP done


if __name__ == "__main__":
    for d in sorted(RAW.glob("KIP-*")):
        pull(d.name)
