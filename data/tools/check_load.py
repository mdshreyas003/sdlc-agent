"""Gate for EVAL-2: the Kafka corpus replays through the real clients, adapters and mappers (no Neo4j needed).

Every Jira issue, comment, PR, commit and mail message must come out as an artifact; ids must be unique.
Run: uv run --no-project python data/tools/check_load.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hackfront.eval.corpus import load  # noqa: E402
from hackfront.ingest.demo import demo_clients  # noqa: E402
from hackfront.ingest.sources.github.adapter import GitHubAdapter  # noqa: E402
from hackfront.ingest.sources.jira.adapter import JiraAdapter  # noqa: E402
from hackfront.ingest.sources.slack.adapter import SlackAdapter  # noqa: E402

d = load()
gh, jira, slack = demo_clients(d)


def pages(fetch):
    cursor = None
    while True:
        page = fetch(cursor)
        yield from page.items
        cursor = page.next_cursor
        if not cursor:
            return


ids = set()
got = {}


def take(name, items):
    items = list(items)
    got[name] = len(items)
    ids.update(a.source.source_id + "|" + a.source.record_type + "|" + a.source.provider for a in items)
    return items


ga = GitHubAdapter(gh)
take("commits", pages(lambda c: ga.commits_page(d.OWNER, d.REPO, cursor=c)))
take("pulls", pages(lambda c: ga.pull_requests_page(d.OWNER, d.REPO, cursor=c)))
ja = JiraAdapter(jira, d.JIRA_SITE)
issues = take("issues", pages(lambda c: ja.issues_page("KAFKA", cursor=c)))
take("jira_comments", (a for i in issues for a in pages(lambda c: ja.comments_page(i.source.source_id, cursor=c))))
sa = SlackAdapter(slack)
msgs = 0
for ch, threads in d.SLACK_THREADS.items():
    roots = take(f"{ch}_roots", pages(lambda c: sa.history_page(d.SLACK_WS, ch, cursor=c)))
    replies = take(f"{ch}_replies", (a for r in roots if r.context.get("reply_count")
                                      for a in pages(lambda c: sa.thread_page(d.SLACK_WS, ch, r.source.source_id, cursor=c))))
    msgs += len(roots)

want = {"commits": len(d.COMMITS), "pulls": len(d.PULLS), "issues": len(d.JIRA_ISSUES["KAFKA"]),
        "jira_comments": sum(len(v) for v in d.JIRA_COMMENTS.values())}
errs = [f"{k}: got {got[k]} want {v}" for k, v in want.items() if got[k] != v]
mail = sum(len(m) for t in d.SLACK_THREADS.values() for m in t.values())
roots = sum(got[k] for k in got if k.endswith("_roots"))
replies = sum(got[k] for k in got if k.endswith("_replies"))
if roots != sum(len(t) for t in d.SLACK_THREADS.values()):
    errs.append("slack roots do not match threads")
if roots + replies - sum(1 for t in d.SLACK_THREADS.values() for m in t.values() if len(m) > 1) != mail:
    errs.append(f"slack messages: roots {roots} + replies {replies} (roots counted twice for threads) != {mail}")
print(got if len(got) < 12 else {k: v for k, v in got.items() if not k.startswith("KIP")}, "mail messages:", mail)
print("\n".join(errs) or "load ok")
sys.exit(bool(errs))
