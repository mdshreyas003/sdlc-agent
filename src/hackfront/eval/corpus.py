"""Benchmark corpus: the raw Apache Kafka pull in data/raw/ as native-shaped GitHub, Jira and Slack payloads.

Same attribute names as ingest/demo/data.py, so the demo transports replay it through the real clients and mappers.
KIP wiki pages are never loaded (they are the answer key); the rationale has to come from Jira, PRs, commits and mail.
The dev@ mailing list stands in for Slack: one channel per KIP, one thread per mail thread (say so in any report).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

RAW = Path(os.environ.get("HACKFRONT_EVAL_RAW") or Path(__file__).resolve().parents[3] / "data" / "raw")
OWNER, REPO = "apache", "kafka"
JIRA_SITE = "https://issues.apache.org/jira"
SLACK_WS = "kafka-dev"


def _json(path: Path):
    try:
        return json.loads(path.read_bytes())
    except ValueError:
        return None


def _jira() -> tuple[dict, dict]:
    issues, comments = {}, {}
    for p in sorted(RAW.glob("KIP-*/hop*.bin")):
        j = _json(p)
        if not (isinstance(j, dict) and j.get("key") and isinstance(j.get("fields"), dict)):
            continue
        f = j["fields"]
        who = lambda u: {"accountId": (u or {}).get("key") or (u or {}).get("name") or "unknown",  # noqa: E731
                         "displayName": (u or {}).get("displayName")}
        key = j["key"]
        comments[key] = [{**c, "author": who(c.get("author"))} for c in (f.get("comment") or {}).get("comments", [])]
        issues[key] = {**j, "fields": {**{k: v for k, v in f.items() if k != "comment"},
                                       "project": {"key": key.split("-")[0]}, "reporter": who(f.get("reporter"))}}
    return {"KAFKA": sorted(issues.values(), key=lambda i: int(i["key"].split("-")[1]))}, comments


def _github() -> tuple[list, list, dict]:
    commits = {c["sha"]: c for p in RAW.glob("KIP-*/commit-*.json") if (c := _json(p))}
    pulls = {pr["number"]: pr for p in RAW.glob("KIP-*/pr[0-9]*.json") if (pr := _json(p))}
    by_date = lambda c: c["commit"]["author"]["date"]  # noqa: E731
    return (sorted(commits.values(), key=by_date, reverse=True), sorted(pulls.values(), key=lambda p: -p["number"]),
            {n: [commits[pr["merge_commit_sha"]]] for n, pr in pulls.items() if pr.get("merge_commit_sha") in commits})


def _slack() -> tuple[dict, dict, dict]:
    threads, names, users = {}, {}, {}
    for d in sorted(RAW.glob("KIP-*")):
        f, tf = d / "dev_thread.jsonl", d / "threads.json"
        if not (f.exists() and tf.exists()):
            continue
        channel = "KIP" + d.name.split("-")[1]
        names[channel] = f"kip-{d.name.split('-')[1]}-dev"
        msgs = {m["id"]: m for m in (json.loads(l) for l in f.read_text(encoding="utf8").splitlines() if l.strip())}
        order = {i: n for n, i in enumerate(sorted(msgs, key=lambda i: msgs[i]["epoch"]))}
        out = threads[channel] = {}
        for th in json.loads(tf.read_text(encoding="utf8"))["threads"]:
            built = []
            for mid in th["messages"]:
                m = msgs[mid]
                name = re.sub(r"\s*<.*", "", m["from"]).strip() or "unknown"
                uid = "U" + hashlib.sha1(name.lower().encode()).hexdigest()[:8].upper()
                users[uid] = name
                ts = f"{m['epoch']}.{order[mid]:06d}"
                text = f"Subject: {m['subject']}\n\n{m['body'].strip()}" if not built else m["body"].strip()
                built.append({"type": "message", "user": uid, "ts": ts, "text": text})
            root = built[0]["ts"]
            if len(built) > 1:
                built[0]["reply_count"] = len(built) - 1
                for b in built:
                    b["thread_ts"] = root
            out[root] = built
    return threads, names, users


def load() -> SimpleNamespace:
    jira, comments = _jira()
    commits, pulls, pr_commits = _github()
    threads, names, users = _slack()
    return SimpleNamespace(
        OWNER=OWNER, REPO=REPO, JIRA_SITE=JIRA_SITE, SLACK_WS=SLACK_WS,
        JIRA_ISSUES=jira, JIRA_COMMENTS=comments, JIRA_PROJECTS=[{"key": "KAFKA", "name": "Kafka"}],
        COMMITS=commits, PULLS=pulls, PR_COMMITS=pr_commits, PR_REVIEWS={}, PR_REVIEW_COMMENTS={}, PR_ISSUE_COMMENTS={},
        SLACK_THREADS=threads, CHANNEL_NAMES=names, USERS=users)


def workspace() -> dict:
    d = load()
    return {"name": "Kafka Eval", "demo": True, "github": {"owner": OWNER, "repos": [REPO]},
            "jira": {"site": JIRA_SITE, "projects": ["KAFKA"]},
            "slack": {"workspace": SLACK_WS, "channels": list(d.SLACK_THREADS), "channel_names": d.CHANNEL_NAMES,
                      "users": d.USERS}}
