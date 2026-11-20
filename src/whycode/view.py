"""The human view: a thin HTTP endpoint and one page over the answer contract (the spec's only UI).

    uv run whycode serve [--port 8765]     # then open http://127.0.0.1:8765/

- `GET /why?anchor=<anchor>` returns the Answer contract as JSON, exactly what the `why` MCP tool returns.
- `GET /?anchor=<anchor>` renders that Answer as one page: the Decisions (live, then partly live), the superseded
  history, the Person to Ask, the Evidence Chain, Incidents, and the refusal state with its nearest evidence.

The page is rendered on the server from the Answer alone (no model, no query of its own), with inline styles and no
scripts or remote assets, so it works offline against the fixture graph with `WHY_COMPOSER=template`.
"""

from __future__ import annotations

import html
import logging
import re
import urllib.parse
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from whycode.codeindex import split_entity_id
from whycode.contract import Answer, DecisionView, EvidenceItem, PersonView

log = logging.getLogger(__name__)

MAX_ANCHOR_CHARS = 2000
REFUSALS = {
    "unresolved": "no Code Entity matched",
    "ungoverned": "no recorded Decision reaches this code",
    "superseded": "every recorded Decision that reaches this code has been superseded",
    "unverified": "nothing the composer wrote could be verified against the evidence",
}
STATUS_LABEL = {"live": "Live", "refined": "Partly live (refined)", "superseded": "Superseded"}
LINK_LABEL = {"hard": "hard link: implemented by a Change that touched this code",
              "soft": "soft link: the code is named in the Discussion"}


def e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _slug(node_id: str) -> str:
    return "ev-" + re.sub(r"[^A-Za-z0-9_-]", "-", node_id)


def _view_href(anchor: str) -> str:
    return "/?" + urllib.parse.urlencode({"anchor": anchor})


class _Page:
    """Renders one Answer; node ids link to their Evidence Chain entry, which links to the source."""

    def __init__(self, question: str, answer: Answer):
        self.q, self.a = question, answer
        self.evidence: dict[str, EvidenceItem] = {i.node_id: i for i in answer.evidence_chain}

    def node(self, node_id: str | None) -> str:
        if not node_id:
            return ""
        if node_id in self.evidence:
            return f'<a class="node" href="#{_slug(node_id)}">{e(node_id)}</a>'
        return f'<span class="node">{e(node_id)}</span>'

    def render(self) -> str:
        a = self.a
        parts = [self.summary()]
        if a.sentences:
            parts.append(self.section("answer", "Answer", "\n".join(
                f'<p class="sentence">{e(s.text)} ' + " ".join(f"[{self.node(c)}]" for c in s.cites) + "</p>"
                for s in a.sentences)))
        live = [d for d in a.decisions if d.status != "superseded"]
        dead = [d for d in a.decisions if d.status == "superseded"]
        if live:
            parts.append(self.section("decisions", "Decisions", "\n".join(self.decision(d) for d in live)))
        if dead:
            parts.append(self.section("history", "Superseded history",
                                      '<p class="hint">Dead Decisions: do not restore what they chose.</p>\n'
                                      + "\n".join(self.decision(d) for d in dead)))
        if a.people:
            parts.append(self.section("people", "Person to Ask", "<ul>" + "\n".join(
                self.person(p) for p in a.people) + "</ul>"))
        if a.evidence_chain:
            title = "Nearest evidence" if a.refused else "Evidence Chain"
            parts.append(self.section("evidence", title, "<ol>" + "\n".join(
                self.item(i) for i in a.evidence_chain) + "</ol>"))
        if a.incidents:
            parts.append(self.section("incidents", "Incidents", "<ul>" + "\n".join(
                f"<li>{self.link(i.id, i.url)}</li>" for i in a.incidents) + "</ul>"))
        return "\n".join(parts)

    @staticmethod
    def section(id_: str, title: str, body: str) -> str:
        return f'<section id="{id_}">\n<h2>{e(title)}</h2>\n{body}\n</section>'

    @staticmethod
    def link(label: str, url: str | None) -> str:
        return f'<a href="{e(url)}">{e(label)}</a>' if url else e(label)

    def summary(self) -> str:
        a = self.a
        if a.anchor is None:
            head = f'<h1 class="anchor">{e(self.q)}</h1>'
        else:
            head = (f'<p class="kind">{e(a.anchor.kind)}</p>\n<h1 class="anchor"><code>{e(a.anchor.id)}</code></h1>')
        lines = [head]
        if a.anchor_matched:
            lines.append(f'<p class="note">Matched from your question "{e(self.q)}" by the entity-matching step: '
                         "check that this is the code you meant.</p>")
        badges = [f'<span class="badge conf-{e(a.confidence.lower())}">{e(a.confidence)} confidence</span>']
        if not a.refused:
            badges.append(f'<span class="badge">{len(a.decisions)} Decision{"s" * (len(a.decisions) != 1)}</span>')
        lines.append('<p class="badges">' + " ".join(badges) + "</p>")
        if a.refused:
            reason = REFUSALS.get(a.refusal_reason or "", "no Decision could be given")
            asked = f' "{e(self.q)}"' if a.refusal_reason == "unresolved" else ""
            lines.append(f'<div class="refusal" role="status"><strong>Refused: {e(reason)}</strong>{asked}. '
                         "Treat the reason as unknown, not as permission to change the code."
                         + (" The nearest evidence and people to ask are below." if a.evidence_chain or a.people
                            else "") + "</div>")
        json_href = "/why?" + urllib.parse.urlencode({"anchor": self.q})
        lines.append(f'<p class="json"><a href="{e(json_href)}">This answer as JSON</a> (the answer contract)</p>')
        return '<section id="summary">\n' + "\n".join(lines) + "\n</section>"

    def decision(self, d: DecisionView) -> str:
        rows = [f'<p class="meta"><span class="status status-{e(d.status)}">{e(STATUS_LABEL[d.status])}</span> '
                f"{e(d.date.isoformat())}, {e(LINK_LABEL[d.link])}</p>",
                f"<h3>{e(d.choice)}</h3>"]
        if d.rationale:
            rows.append(f'<p class="rationale">{e(d.rationale)}</p>')
        rows.append(f"<blockquote>{e(d.quote)}</blockquote>")
        rows.append(f'<p class="source">From {self.node(d.discussion_id)}; Decision {self.node(d.id)}</p>')
        if d.alternatives_rejected:
            rows.append("<p>Rejected: " + "; ".join(e(x) for x in d.alternatives_rejected) + "</p>")
        if d.status != "live":
            verb = "Superseded" if d.status == "superseded" else "Refined"
            when = f" on {e(d.superseded_at.isoformat())}" if d.superseded_at else ""
            by = f" by {self.node(d.superseded_by)}" if d.superseded_by else " by its own record"
            title = self.evidence.get(d.superseded_by or "")
            name = f' "{e(title.title)}"' if title and title.title and title.kind == "decision" else ""
            how = ("inferred by the supersession judge, not stated in history" if d.explicit_or_inferred == "inferred"
                   else "stated in history")
            later = d.supersession_chain[1:]
            now = (f" That was itself superseded: {' then '.join(self.node(n) for n in later)} holds now."
                   if later else "")
            rows.append(f'<div class="supersession"><p>{verb}{when}{by}{name} ({how}).{now}</p>'
                        + (f"<blockquote>{e(d.supersession_quote)}</blockquote>"
                           f'<p class="source">From {self.node(d.supersession_source)}</p>'
                           if d.supersession_quote else "") + "</div>")
        if d.governs:
            rows.append('<p class="governs">Governs: ' + ", ".join(
                f'<a href="{e(_view_href(split_entity_id(g)[1]))}"><code>{e(split_entity_id(g)[1])}</code></a>'
                for g in d.governs) + "</p>")
        return f'<article class="decision status-{e(d.status)}">\n' + "\n".join(rows) + "\n</article>"

    def person(self, p: PersonView) -> str:
        handle = f'<span class="handle">@{e(p.handle)}</span>'
        if p.via:
            what = f"{e(p.role)} of {self.node(p.via)}, active in this area"
        elif p.active:
            what = f"{e(p.role)}, active"
        elif p.ask_instead:
            what = f'{e(p.role)}, departed: ask <span class="handle">@{e(p.ask_instead)}</span> instead'
        else:
            what = f"{e(p.role)}, departed"
        return f'<li class="{"active" if p.active else "departed"}">{handle} <span>{what}</span></li>'

    def item(self, i: EvidenceItem) -> str:
        title = f" {e(i.title)}" if i.title else ""
        date = f' <span class="date">{e(i.date.isoformat())}</span>' if i.date else ""
        source = f' <a href="{e(i.url)}">source</a>' if i.url else ""
        quote = f"<blockquote>{e(i.quote)}</blockquote>" if i.quote else ""
        return (f'<li id="{_slug(i.node_id)}"><span class="kind-tag">{e(i.kind)}</span> '
                f"<code>{e(i.node_id)}</code>{title}{date}{source}{quote}</li>")


STYLE = """
:root { color-scheme: light; --bg: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink2: #52514e; --muted: #898781;
  --line: #e1e0d9; --accent: #2a78d6; --live: #006300; --refined: #8a5a00; --dead: #52514e; --warn-bg: #fdf3e7;
  --warn-line: #ec835a; }
@media (prefers-color-scheme: dark) { :root { color-scheme: dark; --bg: #0d0d0d; --surface: #1a1a19; --ink: #f0efec;
  --ink2: #c3c2b7; --muted: #898781; --line: #2c2c2a; --accent: #3987e5; --live: #0ca30c; --refined: #c98500;
  --dead: #a3a29b; --warn-bg: #2a1d14; --warn-line: #ec835a; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 system-ui, -apple-system, "Segoe UI",
  sans-serif; }
header, main { max-width: 920px; margin: 0 auto; padding: 16px; }
header form { display: flex; gap: 8px; }
header input { flex: 1; min-width: 0; padding: 8px 10px; font: inherit; color: var(--ink); background: var(--surface);
  border: 1px solid var(--line); border-radius: 6px; }
header button { padding: 8px 14px; font: inherit; color: #fff; background: var(--accent); border: 0;
  border-radius: 6px; cursor: pointer; }
header p { margin: 6px 0 0; color: var(--muted); font-size: 13px; }
section { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px;
  margin: 14px 0; }
h1 { font-size: 20px; margin: 0 0 8px; overflow-wrap: anywhere; } h2 { font-size: 16px; margin: 0 0 10px; }
h3 { font-size: 15px; margin: 4px 0; }
code { font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
a { color: var(--accent); }
.kind, .meta, .source, .governs, .hint, .json, .date { color: var(--ink2); font-size: 13px; }
.kind { margin: 0; text-transform: uppercase; letter-spacing: .04em; }
.badge { display: inline-block; padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px;
  font-size: 13px; }
.conf-high { border-color: var(--live); } .conf-medium { border-color: var(--refined); }
.refusal { background: var(--warn-bg); border-left: 3px solid var(--warn-line); padding: 10px 12px; margin: 10px 0;
  border-radius: 4px; }
.note { background: var(--warn-bg); padding: 8px 12px; border-radius: 4px; }
article.decision { border-top: 1px solid var(--line); padding: 12px 0 4px; }
article.decision:first-of-type { border-top: 0; padding-top: 0; }
.status { font-weight: 600; } .status-live .status { color: var(--live); }
.status-refined .status { color: var(--refined); } .status-superseded .status { color: var(--dead); }
article.status-superseded h3 { text-decoration: line-through; text-decoration-thickness: 1px; color: var(--ink2); }
blockquote { margin: 8px 0; padding: 4px 12px; border-left: 3px solid var(--line); color: var(--ink2); }
.supersession { margin: 8px 0; padding: 8px 12px; border: 1px dashed var(--line); border-radius: 6px; }
.supersession p { margin: 0; }
ul, ol { margin: 0; padding-left: 20px; } li { margin: 6px 0; }
.handle { font-weight: 600; } li.departed > .handle { color: var(--ink2); }
.kind-tag { display: inline-block; min-width: 64px; color: var(--muted); font-size: 12px; text-transform: uppercase; }
.sentence { margin: 6px 0; } .node { font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; }
"""


def render_page(question: str = "", answer: Answer | None = None) -> str:
    """The whole page: the ask form, then the Answer (if any)."""
    body = _Page(question, answer).render() if answer is not None else (
        '<section><p>Ask about a function (<code>pkg/sql.(*SchemaChanger).exec</code>), a file '
        "(<code>pkg/sql/schema_changer.go</code>), a package or a cluster setting "
        "(<code>schemachanger.job.max_retry_backoff</code>), or ask a question in words.</p></section>")
    title = f"why: {question}" if question else "why"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<form method="get" action="/">
<input name="anchor" value="{e(question)}" placeholder="Anchor or question" aria-label="Anchor or question" autofocus>
<button type="submit">Why?</button>
</form>
<p>Why is this CockroachDB schema-change code the way it is? Decisions, their evidence and the people to ask.</p>
</header>
<main>
{body}
</main>
</body>
</html>
"""


def make_server(why: Callable[[str], Answer], host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """An HTTP server over `why` (port 0 picks a free port: read `server.server_address`)."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "whycode"

        def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
            url = urllib.parse.urlsplit(self.path)
            params = urllib.parse.parse_qs(url.query)
            anchor = (params.get("anchor") or [""])[0][:MAX_ANCHOR_CHARS]
            if url.path == "/why":
                if not anchor.strip():
                    return self._send(HTTPStatus.BAD_REQUEST, "application/json", '{"error": "anchor is required"}')
                return self._answer(anchor, lambda a: self._send(HTTPStatus.OK, "application/json",
                                                                 a.model_dump_json(indent=1)))
            if url.path == "/":
                if not anchor.strip():
                    return self._send(HTTPStatus.OK, "text/html", render_page())
                return self._answer(anchor, lambda a: self._send(HTTPStatus.OK, "text/html", render_page(anchor, a)))
            return self._send(HTTPStatus.NOT_FOUND, "text/plain", "not found\n")

        def _answer(self, anchor: str, respond: Callable[[Answer], None]) -> None:
            try:
                answer = why(anchor)
            except Exception as exc:  # noqa: BLE001  shown as a server error, never a half-rendered page
                log.exception("why(%r) failed", anchor)
                return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain", f"why failed: {type(exc).__name__}\n")
            respond(answer)

        def _send(self, status: HTTPStatus, kind: str, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            log.info("%s %s", self.address_string(), format % args)

    return ThreadingHTTPServer((host, port), Handler)
