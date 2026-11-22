"""Optional, one-way projection of people and reviewed memory into Neo4j, so a graph tool (Neo4j Bloom) can show them.

    (:Person)-[:AUTHORED]->(:Artifact)     the source names the author; WHICH person is declared by the workspace admin
    (:Person)-[:APPROVED]->(:Decision)     who signed the entry off
    (:Decision)-[:CITES]->(:Artifact)      the evidence an entry stands on
    (:Decision)-[:SUPERSEDES]->(:Decision) a newer decision replaced an older one

Labels are disjoint from :Artifact, so the agent's read-only evidence queries can never see them and a Decision is never
cited as evidence (ADR 0002). Derived data: rebuilt from scratch per workspace, safe to run again.
"""

from __future__ import annotations


KIND_LABELS = {"issue": "Issue", "pull_request": "PullRequest", "git_commit": "Commit", "discussion_thread": "Thread", "discussion_message": "Message"}


def project(driver, database: str, ws: str, entries: list[dict], people: dict, slack_users: dict, scopes: list[str]) -> dict:
    run = lambda q, **kw: driver.execute_query(q, database_=database, **kw)  # noqa: E731
    run("MATCH (n) WHERE (n:Person OR n:Decision) AND n.workspace = $ws DETACH DELETE n", ws=ws)
    for kind, label in KIND_LABELS.items():  # a second label per record kind, so graph tools can colour and filter by it
        run(f"MATCH (a:Artifact) WHERE a.scope IN $scopes AND a.record_kind = $k SET a:{label}", scopes=scopes, k=kind)
    slack_id = {name: uid for uid, name in slack_users.items()}
    authored = 0
    for key, p in people.items():
        run("CREATE (:Person {key: $k, workspace: $ws, name: $name, role: $role, github: $gh})",
            k=f"{ws}/{key}", ws=ws, name=p["name"], role=p["role"], gh=p.get("github"))
        for provider, match in (("github", "a.actor_display_name = $h"), ("jira", "a.actor_display_name = $h"),
                                ("slack", "a.actor_source_id = $h")):
            handle = slack_id.get(p.get("slack")) if provider == "slack" else p.get(provider)
            if not handle:
                continue
            _, summary, _ = run(f"MATCH (n:Person {{key: $k}}), (a:Artifact) WHERE a.scope IN $scopes AND a.provider = $prov AND {match} "
                                "MERGE (n)-[r:AUTHORED]->(a) SET r.origin = 'declared-identity'",
                                k=f"{ws}/{key}", scopes=scopes, prov=provider, h=handle)
            authored += summary.counters.relationships_created
    decisions = cited = 0
    for e in entries:
        s = e.get("served") or {}
        run("CREATE (:Decision {key: $k, workspace: $ws, name: $title, title: $title, kind: $kind, status: $status, version: $v, live_version: $lv, "
            "approved_by: $by, body: $body, anchor: $anchor})", k=f"{ws}/{e['id']}", ws=ws, title=s.get("title") or e["title"],
            kind=s.get("kind") or e["kind"], status=e["status"], v=e["version"], lv=s.get("version"), by=s.get("approved_by"),
            body=(s.get("body") or e["body"])[:2000], anchor=e.get("anchor"))
        decisions += 1
        ids = s.get("evidence") or [x["id"] for x in e["evidence"]]
        _, summary, _ = run("MATCH (d:Decision {key: $k}), (a:Artifact) WHERE a.canonical_id IN $ids AND coalesce(a.is_stub, false) = false "
                            "MERGE (d)-[:CITES]->(a)", k=f"{ws}/{e['id']}", ids=ids)
        cited += summary.counters.relationships_created
        if s.get("approved_by"):
            run("MATCH (p:Person {workspace: $ws, github: $by}), (d:Decision {key: $k}) MERGE (p)-[:APPROVED]->(d)",
                ws=ws, by=s["approved_by"], k=f"{ws}/{e['id']}")
        if e.get("supersedes"):
            run("MATCH (n:Decision {key: $a}), (o:Decision {key: $b}) MERGE (n)-[:SUPERSEDES]->(o)",
                a=f"{ws}/{e['id']}", b=f"{ws}/{e['supersedes']}")
    return {"people": len(people), "authored": authored, "decisions": decisions, "cites": cited}
