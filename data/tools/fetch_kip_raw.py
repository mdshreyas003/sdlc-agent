"""Fetch the Kafka benchmark corpus (data/raw/KIP-*) from its ORIGINAL PUBLIC SOURCES and verify it. stdlib only.

The raw KIP data is not redistributed in this repo (KIP/ASF content licence unconfirmed). `data/raw/hashes.json`
lists every expected file with its source, how to rebuild it, and its sha256:
  confluence  KIP page from the cwiki.apache.org Confluence REST API (page.json)
  http        one GET, bytes kept as-is: issues.apache.org Jira, api.github.com PRs/commits, lists.apache.org (hop*, pr*, commit-*)
  ponymail    dev@kafka.apache.org messages by id from the lists.apache.org Pony Mail API, one JSON line each (dev_thread.jsonl)
  links       derived from page.json, same rule as pull_pilot.py (links.json)
  threads     derived from dev_thread.jsonl by build_threads.py (threads.json)
  inline      small index we authored (prs.json: Jira key -> PR numbers found by pull_commits.py), stored in hashes.json
Files already present with the right hash are skipped, so a stopped run can be resumed.
Upstream drift: Jira and GitHub API responses carry live metadata (repo star/fork counts embedded in every PR, Jira
statusCategory.colorName and comment.maxResults), so their bytes change even when the content does not. Each JSON file
therefore also has `content_sha256`, the hash of the parsed JSON without those VOLATILE fields (sorted keys). A file whose
bytes differ but whose content hash matches is reported as "drift" (kept, usable); a content mismatch is a real change.
Set GITHUB_TOKEN to lift GitHub's 60 calls/hour limit (25 calls needed).
Run: uv run --no-project python data/tools/fetch_kip_raw.py [--out DIR] [--workers 8]
Exit code: 0 every file matches by bytes or content hash, 1 content mismatch or fetch failure.
"""
import argparse, hashlib, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_threads import group  # noqa: E402
from pull_pilot import link_candidates  # noqa: E402

DATA = Path(__file__).resolve().parents[1]
MANIFEST = DATA / "raw" / "hashes.json"
UA = {"User-Agent": "hackfront-research/0.1"}
PONY = "https://lists.apache.org/api/email.lua?id="


VOLATILE_PR = ("repo",)  # under base/head: the whole repository object (stars, forks, size, pushed_at, ...)
VOLATILE_ANY = ("colorName", "maxResults")


def content_sha256(data):
    """sha256 of a JSON file minus live metadata, or None if it is not JSON."""
    try:
        obj = json.loads(data)
    except ValueError:
        return None

    def strip(o, parent=""):
        if isinstance(o, dict):
            return {k: strip(v, k) for k, v in o.items()
                    if k not in VOLATILE_ANY and not (parent in ("base", "head") and k in VOLATILE_PR)}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o
    return hashlib.sha256(json.dumps(strip(obj), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def get(url, tries=4):
    h = dict(UA)
    if "api.github.com" in url:
        h["Accept"] = "application/vnd.github+json"
        if os.environ.get("GITHUB_TOKEN"):
            h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=h), timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {url[:90]}: {e}", file=sys.stderr, flush=True)
            time.sleep(3 * (i + 1))


def mail_row(mid):
    e = json.loads(get(PONY + mid))
    return {"id": e["id"], "message-id": e["message-id"], "in-reply-to": e["in-reply-to"], "subject": e["subject"],
            "from": e["from"], "epoch": e["epoch"], "url": f"https://lists.apache.org/thread/{e['mid']}",
            "body": e.get("body", "")}


def build(name, spec, out, pool):
    kind = spec["kind"]
    if kind == "http":
        return get(spec["fetch"])
    if kind == "confluence":
        return json.dumps(json.loads(get(spec["fetch"]))).encode()
    if kind == "ponymail":
        rows = list(pool.map(mail_row, spec["ids"]))
        return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf8")
    rec = out / name.split("/")[0]
    if kind == "links":
        a, c = link_candidates(json.loads((rec / "page.json").read_bytes())["body"]["storage"]["value"])
        return json.dumps({"all": a, "candidates": c}, indent=1).encode()
    if kind == "threads":
        msgs = [json.loads(l) for l in (rec / "dev_thread.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
        return json.dumps({"threads": group(msgs)}, indent=1).encode("utf8")
    if kind == "inline":
        return json.dumps(spec["content"], indent=1).encode()
    raise ValueError(f"unknown kind {kind}")


def verdict(data, spec):
    if hashlib.sha256(data).hexdigest() == spec["sha256"]:
        return "ok   "
    if spec.get("content_sha256") and content_sha256(data) == spec["content_sha256"]:
        return "drift"
    return "DIFF "


ORDER = {"confluence": 0, "http": 1, "ponymail": 2, "inline": 3, "links": 4, "threads": 5}  # derived files last


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DATA / "raw")
    ap.add_argument("--workers", type=int, default=8, help="parallel Pony Mail requests")
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf8"))
    t0, bad, drift, failed, skipped = time.time(), [], [], [], 0
    with ThreadPoolExecutor(args.workers) as pool:
        for name, spec in sorted(manifest.items(), key=lambda kv: (ORDER[kv[1]["kind"]], kv[0])):
            path = args.out / name
            if path.exists() and (tag := verdict(path.read_bytes(), spec)) != "DIFF ":
                skipped += 1
                if tag == "drift":
                    drift.append(name)
                continue
            try:
                data = build(name, spec, args.out, pool)
            except Exception as e:  # noqa: BLE001
                failed.append(name)
                print(f"FAIL  {name}: {e}", flush=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            tag = verdict(data, spec)
            {"drift": drift, "DIFF ": bad}.get(tag, []).append(name)
            print(f"{tag} {name} ({len(data)} bytes, expected {spec['bytes']})", flush=True)
    n = len(manifest)
    print(f"{n} files: {n - len(bad) - len(drift) - len(failed)} byte-identical ({skipped} already present), "
          f"{len(drift)} volatile-metadata drift only (content hash matches), {len(bad)} CONTENT MISMATCH, "
          f"{len(failed)} failed, {time.time() - t0:.0f}s")
    for name in drift:
        print("  drift:", name)
    for name in bad:
        print("  CONTENT MISMATCH:", name)
    return 1 if bad or failed else 0


if __name__ == "__main__":
    sys.exit(main())
