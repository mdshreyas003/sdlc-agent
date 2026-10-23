"""Group each KIP's dev_thread.jsonl messages into threads. stdlib only.

Two messages share a thread if one replies to the other (in-reply-to) or they have the same
subject once Re:/Fwd: prefixes are stripped. Writes data/raw/KIP-N/threads.json:
{"threads": [{"id", "subject", "first", "last", "messages": [message ids by time]}]}
"""
import json, re
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "raw"
norm = lambda s: re.sub(r"^(\s*(re|fwd?)\s*:\s*)+", "", s, flags=re.I).strip().lower()


def group(msgs):
    parent = {m["id"]: m["id"] for m in msgs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    by_mid = {m["message-id"]: m["id"] for m in msgs if m.get("message-id")}
    by_subj = {}
    for m in msgs:
        if m.get("in-reply-to") in by_mid:
            union(m["id"], by_mid[m["in-reply-to"]])
        union(m["id"], by_subj.setdefault(norm(m["subject"]), m["id"]))
    out = {}
    for m in sorted(msgs, key=lambda m: m["epoch"]):
        out.setdefault(find(m["id"]), []).append(m)
    return [{"id": ms[0]["id"], "subject": ms[0]["subject"], "first": ms[0]["epoch"], "last": ms[-1]["epoch"],
             "messages": [m["id"] for m in ms]} for ms in out.values()]


if __name__ == "__main__":
    for f in sorted(RAW.glob("KIP-*/dev_thread.jsonl")):
        msgs = [json.loads(l) for l in f.read_text(encoding="utf8").splitlines() if l.strip()]
        threads = group(msgs)
        (f.parent / "threads.json").write_text(json.dumps({"threads": threads}, indent=1), encoding="utf8")
        print(f.parent.name, len(msgs), "messages ->", len(threads), "threads")
