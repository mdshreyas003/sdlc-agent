"""Shared by the gold tools: every corpus artifact as {url: text}, read through the real adapters.

The url is what the system cites, so gold evidence is written as these urls (Jira issue/comment, PR, commit,
mail permalink). Text is title + body, plus the patch for commits, so a quote is checked against what the system sees.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hackfront.eval.corpus import load  # noqa: E402
from hackfront.ingest.demo import demo_clients  # noqa: E402
from hackfront.ingest.sources.github.adapter import GitHubAdapter  # noqa: E402
from hackfront.ingest.sources.jira.adapter import JiraAdapter  # noqa: E402
from hackfront.ingest.sources.slack.adapter import SlackAdapter  # noqa: E402

norm = lambda s: re.sub(r"\s+", " ", s or "").strip()  # noqa: E731


def _pages(fetch):
    cursor = None
    while True:
        page = fetch(cursor)
        yield from page.items
        cursor = page.next_cursor
        if not cursor:
            return


def index() -> dict[str, dict]:
    """url -> {"text", "when", "kind"} for every non-stub artifact; any ?query is dropped from the url."""
    d = load()
    gh, jira, slack = demo_clients(d)
    ga, ja, sa = GitHubAdapter(gh), JiraAdapter(jira, d.JIRA_SITE), SlackAdapter(slack)
    arts = [*_pages(lambda c: ga.commits_page(d.OWNER, d.REPO, cursor=c)),
            *_pages(lambda c: ga.pull_requests_page(d.OWNER, d.REPO, cursor=c))]
    issues = list(_pages(lambda c: ja.issues_page("KAFKA", cursor=c)))
    arts += issues
    for i in issues:
        arts += _pages(lambda c: ja.comments_page(i.source.source_id, cursor=c))
    for ch in d.SLACK_THREADS:
        roots = list(_pages(lambda c: sa.history_page(d.SLACK_WS, ch, cursor=c)))
        arts += roots
        for r in roots:
            if r.context.get("reply_count"):
                arts += _pages(lambda c: sa.thread_page(d.SLACK_WS, ch, r.source.source_id, cursor=c))
    out = {}
    for a in arts:
        raw = a.raw_payload or {}
        patches = " ".join(f.get("patch", "") for f in raw.get("files", []) if isinstance(f, dict))
        url = a.source.uri.split("?")[0] if a.source.record_type != "comment" else a.source.uri
        out[url] = {"text": norm(" ".join(filter(None, [a.title, a.text, patches]))), "when": a.event_time,
                    "kind": f"{a.source.provider}:{a.source.record_type}"}
    return out
