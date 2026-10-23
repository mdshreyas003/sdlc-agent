# Data manifest — slice 1: Apache Kafka (KIPs) + Python (PEPs)

## Fetching the raw Kafka corpus (`data/raw/KIP-*`)

The raw KIP data is **not stored in git**: it is ASF content (Confluence KIP pages, Jira, dev@kafka archives, GitHub API objects) whose redistribution terms are unconfirmed, so it is gitignored and fetched from the original public sources:

```
uv run --no-project python data/tools/fetch_kip_raw.py   # ~2.5 min, 96 files, ~42 MB, no keys needed
```

`data/raw/hashes.json` (tracked) lists every expected file, how it is rebuilt and its sha256. The script verifies each file; Jira and GitHub responses carry live metadata (repo star counts, Jira colour names), so those are also checked with a `content_sha256` that ignores those fields and reported as "drift" when only they changed. Any real content change is reported as `CONTENT MISMATCH` and the script exits 1. Then `uv run hackfront eval-load` should load 1,191 artifacts. Set `GITHUB_TOKEN` if you hit GitHub's 60 calls/hour limit (a run needs 25). The PEP pilot data has been removed from the corpus.

Checked 2026-10-19 with live requests. Nothing is downloaded yet; this file records what is reachable and the terms to confirm before download. Update `retrieved` and `hash` columns when data is pulled.

## Sources

| Id | Source | Role | Access (verified reachable) | Terms | Retrieved | Hash |
|---|---|---|---|---|---|---|
| kafka-jira | issues.apache.org Jira, project KAFKA (20,015 issues at check time) | tracker | REST `/jira/rest/api/2/search?jql=project=KAFKA`, `/issue/KAFKA-N` incl. `issuelinks`; public, no auth | ASF content; confirm ASF terms of use before redistributing | — | — |
| kafka-kip | cwiki.apache.org Confluence, KIP index and pages | **gold rationale** | HTML pages; KIP-500 page contains Motivation, Rejected Alternatives, Discussion thread and JIRA links sections | Confluence content under ASF site terms — confirm | — | — |
| kafka-dev | `dev@kafka.apache.org` archive on lists.apache.org (2011-07 to 2026-10) | chat substitute | `api/stats.lua` returns monthly counts; `api/mbox.lua?list=dev&domain=kafka.apache.org&d=YYYY-MM` returns HTTP 200 | Public archive; confirm ASF list-archive terms | — | — |
| kafka-gh | github.com/apache/kafka PRs, commits | code + PR | GitHub API (token for rate limits) | Apache-2.0 for code; PR text per GitHub terms | — | — |
| pep-text | github.com/python/peps `peps/pep-NNNN.rst` | **gold rationale** | raw GitHub; header has `Post-History`, sections like Rationale; PEP 8 ends "placed in the public domain" | Public domain per each PEP's Copyright section (PEP 8 confirmed; check per PEP, some use CC0) | — | — |
| pep-discuss | discuss.python.org and python-dev/python-ideas archives, via each PEP's `Discussions-To` / `Post-History` | chat substitute | Discourse API (public categories); mailing archive on python.org | Confirm per site | — | — |
| pep-gh | github.com/python/cpython issues, PRs, commits | tracker + code | GitHub API | PSF license for code; issue text per GitHub terms | — | — |
| seoss33 | Harvard Dataverse DOI 10.7910/DVN/PDDZ4Q | link-recovery set S6 | Dataverse download | Check dataset page | — | — |
| public-jira | Zenodo DOI 10.5281/zenodo.5882881 (v7, 5.8 GB, MongoDB dump) | link-recovery set S6 | Zenodo | Check record license | — | — |

## Not yet verified

- Whether KIP pages expose a machine-readable discussion-thread link beyond the HTML section (needs one fetch of the Confluence REST API).
- Exact license text for ASF mailing archives and Confluence pages.
- Python-side chat: how many PEPs' `Post-History` link to a recoverable thread.
- Rate limits and whether a GitHub token is available for the owner.

## Pilot plan (next, small)

1. Pick 10 KIPs and 10 PEPs with a stated rationale and a resolvable discussion thread and linked issue or PR.
2. Pull only those artifacts plus one hop of links; write hashes here.
3. Author 2 questions per record by hand with gold evidence and verbatim quote (target 40 questions); time the annotation effort.
4. Decide scale-up from measured annotation cost.

## Pilot result (2026-10-19)

Script `data/tools/pull_pilot.py` (stdlib; run with `uv run --no-project python data/tools/pull_pilot.py`). 10 KIPs (98, 129, 405, 447, 500, 595, 630, 679, 848, 890) and 10 PEPs (557, 563, 572, 584, 604, 618, 634, 649, 695, 703), each plus up to 6 one-hop links. Result: **81 files, 2.7 MB**, sha256 + URL + retrieval time per file in `data/raw/hashes.json` (`data/raw/` itself is gitignored until terms are confirmed).

| Host | Files |
|---|---|
| raw.githubusercontent.com (PEP text) | 10 |
| cwiki.apache.org (KIP pages) | 10 |
| mail.python.org | 24 |
| issues.apache.org (Jira) | 16 |
| github.com (issues/PRs via API) | 10 |
| discuss.python.org | 6 |
| lists.apache.org (via links) | 2 |
| bugs.python.org | 2 |
| mail-archives.apache.org | 1 |

Findings that change the plan:

- **Kafka dev-list links did not resolve.** Older KIPs link to `lists.apache.org/thread.html/...` (JavaScript stub), so link-following retrieved only 2 mailing threads. Fixed below with the search API.
- Python side is richer: mail.python.org and discuss.python.org threads resolve.
- Caps: 6 hops per record; any record with more candidates is truncated (`links.json` keeps the full list). `bugs.python.org` returned 503 intermittently.
- PEP-634 is spec-only ("intentionally devoid of commentary"); its rationale is in PEP-635, which is not in the corpus. It is used as a natural **unanswerable** question (Q20).

## Gold questions (draft)

`data/gold/pilot_questions.jsonl`: 19 answerable "why" questions (one per record, except PEP-634) + 1 unanswerable. Each has a verbatim `gold_quote` from the record itself; `python data/tools/verify_gold.py` confirms all 20 quotes appear in the source (passes). `human_verified` is `false` everywhere: **you still need to confirm each question is a real, non-trivial "why" and that the quote states the reason**, and add `gold_hop_evidence` (the mail/Jira/PR threads that show the discussion). Known weakness: questions are phrased from the document title, so the answer sits in the same document; harder cross-artifact questions need the hop evidence.

``` mermaid
flowchart LR
    A["Real public sources<br/>Kafka KIPs, Python PEPs"] -->|"pull_pilot.py"| B["data/raw/<br/>81 files + links they point to"]
    M["Kafka mailing list<br/>(monthly archives)"] -->|"pull_kafka_threads.py<br/>(running now)"| B
    B -->|"sha256 of every file"| H["hashes.json<br/>proof of what we downloaded"]
    B --> G["data/gold/pilot_questions.jsonl<br/>20 questions + exact quote"]
    G -->|"verify_gold.py"| V{"Is the quote really<br/>in the source?"}
    V -->|"yes, all 20"| R["You review each question<br/>human_verified = true"]
    R --> E["Final test set<br/>to score your system"]
```

``` mermaid
flowchart LR
    Q["Question<br/>Why remove ZooKeeper from Kafka?"] --> S["Your system"]
    S --> A["Answer + citation + quote"]
    A --> C{"Quote matches the<br/>gold quote in the source?"}
    C -->|"yes"| P["Pass"]
    C -->|"no or made up"| F["Fail"]
    X["Question with no answer in the data<br/>(example: PEP-634 'why match statement')"] --> S2["Your system"]
    S2 --> N{"Says 'not established'?"}
    N -->|"yes"| P2["Pass"]
    N -->|"guesses"| F2["Fail"]
```
## Kafka dev-list rebuild (2026-10-19)

Monthly mbox downloads were abandoned (12-20 MB each; server cut connections, 503s, timeouts). `data/tools/pull_kafka_threads.py` now uses the Pony Mail search API (`stats.lua?q=KIP-N`, from the KIP page creation date to today) and keeps messages whose **subject** names the KIP, then fetches each full body (`email.lua`). Output `data/raw/KIP-N/dev_thread.jsonl` (id, message-id, in-reply-to, subject, from, epoch, thread url, body).

| KIP | Messages kept | Body hits (not kept) |
|---|---|---|
| 98 | 278 | 927 |
| 129 | 29 | 64 |
| 405 | 183 | 799 |
| 447 | 69 | 140 |
| 500 | 93 | 829 |
| 595 | 49 | 212 |
| 630 | 43 | 151 |
| 679 | 12 | 43 |
| 848 | 201 | 1139 |
| 890 | 113 | 450 |
| **Total** | **1,070** | |

Sha256 per file in `hashes.json` (91 entries total). Limits: subject match only, so replies that dropped the KIP tag from the subject are missed (the body hits not kept include mere mentions); messages are not yet grouped into threads (`in-reply-to` is stored for that). `gold_hop_evidence` in the gold file is still empty: next step is to pick, per question, the mail message that states or confirms the reason.
