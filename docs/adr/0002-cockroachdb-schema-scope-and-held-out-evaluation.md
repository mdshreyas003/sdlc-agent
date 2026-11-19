---
status: accepted
---

# CockroachDB, scoped to SQL schema changes, evaluated against a held-out window

We ingest only the SQL schema-change area of cockroachdb/cockroach: `pkg/sql/schemachanger` and its neighbours, schema-related RFCs from `docs/RFCS/`, and `A-schema-*` issues. History up to 2024-06-30 is ingested. Everything after that date is the Held-out Window, used to test whether answers that later changed are reported as changed, and as the source of tasks for the agent comparison.

We chose CockroachDB because judges reward proof, and it has the richest ground truth already written by its own authors:
- RFCs with machine-readable `Status:` headers that link their PR and tracking issue
- about 28k PRs that link issues with "Fixes #"
- about 600 revert PRs
- cluster settings that work like "config flags nobody understands"

## Considered Options

- **openedx-platform.** More ADRs (144) and more reverts (955), but thin GitHub issue linking because older work was tracked in Jira.
- **mozilla/fxa, Backstage, Vitess, Thanos.** Cleaner but smaller, with almost no explicit supersession labels.
- **Whole-repo ingestion.** 119k commits is too much for a hackathon, and a narrow, deep slice demos better.

## Consequences

- Explicit supersession labels are few (about 4–5), so the held-out window, not RFC status, carries the supersession evaluation.
- The repo has no postmortems, so Incidents are stood in for by regression, release-blocker and bug issues closed by a Change.
