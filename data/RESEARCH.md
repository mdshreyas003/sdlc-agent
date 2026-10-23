# Dataset research — evidence-grounded engineering memory

Status: research deliverable 1 (2026-10-19). No dataset has been built yet. This file says what exists, what does not, and the plan to compose a real evaluation set.

Evidence labels: **[verified]** = confirmed from a fetched page or search result in this session. **[unverified]** = from memory or a secondary source. Check licenses and versions on the primary page before use.

## 1. What the system must be proven to do

From `SPEC.md`: answer "why is this code like this?" over GitHub + Jira + Slack with claim-level answers, verbatim-verified citations (FR-13, FR-16), explicit "not established" when evidence is missing (AC-7), edges only from explicit identifiers (FR-9), and workspace isolation (AC-15).

So the dataset has to test four things:

| # | Capability | What a dataset needs |
|---|---|---|
| C1 | Link recovery from explicit identifiers | Real artifacts with real cross-references, plus gold links |
| C2 | Rationale QA (answerable) | Real "why" questions with a gold rationale and gold evidence |
| C3 | Abstention (unanswerable) | Questions whose rationale is absent from the graph |
| C4 | Citation fidelity | Gold evidence ids and quotes to score cited quotes against |

## 2. What already exists

### 2.1 Directly relevant

| Dataset | What it gives | Gap for us | Status |
|---|---|---|---|
| **SEOSS 33** (Rath & Mader, 2019) | 33 projects; Jira issues, links, comments, commits, commit→issue links, code changes. SQLite per project. Hosted on Harvard Dataverse, DOI 10.7910/DVN/PDDZ4Q | No PRs, no chat, no rationale labels. Links are explicit-ID only. Static (circa 2018) | [verified] DOI via search; contents from the repo's own `research/SEOSS33_summary.md` |
| **Public Jira Dataset** (Montgomery, Lüders, Maalej, MSR 2022) | 16 public Jira instances, 1,822 projects, ~2.7M issues, 32M changes, 9M comments, 1M issue links. MongoDB dump, 5.8 GB, Zenodo v7 (2025-06-23), DOI 10.5281/zenodo.5882881. Anonymised | No code or PRs. Anonymisation removes people (fine for us) | [verified] |
| **TUM ILADD** | 1,500+ Jira issues manually labelled for architectural design decisions, 2 repos | Small, 2 projects, issue-only | [verified] |
| **DRMiner dataset** (ASE 2024) | Annotated design rationale from Jira issue logs, Cassandra / Flink / Solr | Issue-only; availability and license not checked | [verified] existence; [unverified] release |
| **Software-related Slack chats** (MSR 2020 data showcase) | 38,955 disentangled conversations, 437,893 utterances, 3 public Slack communities (python, clojure, elm) | Not linked to any repository or tracker; Q&A chat, not engineering decisions | [verified] |
| **GitterCom / Gitter study** | 1.4M disentangled utterances; F2Chat: 2,959 threads labelled by information category (Angular, Spring Boot, DL4J) | Chat only, no links to code or issues | [verified] |
| **DevGPT** (MSR 2024) | ~29.8k ChatGPT prompt/response pairs linked to commits, issues, PRs, discussions. CC BY 4.0 paper | Developer–LLM chat, not team rationale | [verified] |

### 2.2 Repository-QA benchmarks (closest to the task, not the same task)

| Benchmark | Built from | Size | Gap |
|---|---|---|---|
| **RepoProbe** (arXiv 2608.04783) | GitHub Discussions; "how/why" architecture questions; checklist-based answer scoring | size not stated on abstract page | Discussion-sourced, not issue/PR/Jira/Slack. Replication package at Tencent-Hunyuan/RepoProbe. Useful as a **scoring protocol** to copy |
| **Code-QA-Bench** (arXiv 2605.29277) | 10 SWE-bench Python repos, answer-first generation | 628 tasks (528 code-derivable, 100 doc-dependent) | Shows "why" questions score highest closed-book, i.e. **memorisation risk**. Use its closed-book / code-only / documented ablation idea |
| **SWE-QA** (arXiv 2509.14635) | 77,100 GitHub issues, 11–12 repos | 576–720 QA pairs depending on version | Code comprehension, not decision history |
| **CoReQA** (arXiv 2501.03447) | GitHub issues and comments, 176 repos, 4 languages | ~1,563 QA pairs [unverified count] | Issue-resolution oriented; no cross-tool linking |
| **SWE-bench / Verified / Multilingual** | PR + issue → patch tasks. Verified = 500; Multilingual = 300 tasks, 42 repos, 9 languages | 500 / 300 | Patch generation, not rationale. Useful as a **source of repos and issue↔PR pairs**, not as a score to report |

### 2.3 Neighbouring tasks (for method, baselines, scoring)

| Resource | Use for us |
|---|---|
| **LinkRank** (arXiv 2607.23610) and "Revisiting issue-commit linking with LLM-assisted retrieval" (arXiv 2605.00447) | Recent issue-commit linking work. One reports an Apache set with 208,858 true links, 130,538 issues, 166,460 commits (2006–2025) [verified from search snippet; confirm on the paper]. Gold links here are themselves ID-mined, so they test C1 only |
| **AbstentionBench** (arXiv 2506.09038, NeurIPS 2025) | 20 datasets for unanswerable, underspecified and false-premise questions. Finding: reasoning models abstain worse. Supports C3 as a real, unsolved problem [verified]. Code: facebookresearch/AbstentionBench |
| **ALCE** (attributed generation) | Citation recall / precision method for C4. Not confirmed in this session [unverified] |
| **GH Archive / GHTorrent / Software Heritage** | Raw event and history sources. GHTorrent data ends ~2019–2020; Software Heritage is code and history, not review comments. License terms were **not** confirmed [unverified] |

### 2.4 Finding

**No public dataset links GitHub + Jira + Slack with rationale ground truth.** A targeted search found issue↔commit sets, Jira dumps and Slack chat sets separately, and vendor integration pages, but no joint research corpus. Treat this as "not found in this search", not as proof of absence. The work therefore is to **compose**, not download.

## 3. Verdict: what to compose

### 3.1 Principle: never score on links your own extractor produces

If gold = explicit references (the same signal FR-9 uses), the system wins by construction and proves nothing. Gold must come from a **human-authored statement of a decision and its reason** that exists independently of the cross-references.

### 3.2 Source recipe (all public, real, citable)

Public projects where decisions are documented *and* the discussion that produced them is public and cross-linked:

| Project family | Decision record (gold rationale) | Tracker + code | Chat/discussion substitute for Slack |
|---|---|---|---|
| **Apache** (Kafka KIPs, Flink FLIPs, Cassandra CEPs, Spark SPIPs) | The KIP / FLIP / CEP page states the motivation | Jira issues + GitHub PRs (explicit `KAFKA-123` keys in PR titles) | `dev@` mailing list threads (public archive) — plays the Slack role |
| **Kubernetes** KEPs | KEP "motivation / alternatives" sections | GitHub issues + PRs | Public Slack/mailing lists; Slack archive availability **unverified** |
| **Rust** RFCs | RFC text, "rationale and alternatives" | GitHub issues/PRs | Zulip (public) [unverified archive terms] |
| **Python** PEPs | PEP "rationale / rejected ideas" | GitHub issues/PRs | discuss.python.org threads |
| **Any repo with ADRs** (`docs/adr/`) | ADR "context / decision / consequences" | GitHub issues/PRs | Discussions |

Mailing lists, Discourse and Zulip are the honest stand-in for Slack: same shape (threaded informal discussion, permalinks, no formal tracker structure), public, redistributable under project terms. The adapter stays the Slack-shaped envelope (FR-2). Real Slack is covered separately by the synthetic-but-native-shaped demo already in `src/` plus one **owned** workspace if the owner can export one with consent.

Keep **both** layers: the real corpus (credibility) and the existing synthetic demo (controlled, deterministic regression).

### 3.3 Gold construction (human-grounded, no LLM-only labels)

1. Pick decision records authored before the artifacts that the system will ingest are cut off, from 6–10 projects across 3 families.
2. For each record, a person writes the question ("Why does X use Y instead of Z?") and marks the **gold evidence set**: the issue/PR/thread ids and the verbatim quote that states the reason.
3. Two annotators on a 20% sample; report Cohen's kappa (the Gitter study reports 0.81 for its labelling [verified], a reasonable bar).
4. LLM may *draft* questions (Code-QA-Bench's answer-first idea) but a human verifies every gold quote against the source.

### 3.4 Test sets (each isolates one claim)

| Set | Construction | Scores | Proves |
|---|---|---|---|
| **S1 Answerable-why** | Questions with human gold evidence, 100–150 | Claim support rate, evidence recall/precision, quote exactness | C2, C4 |
| **S2 Evidence-ablated** | Same questions, with the gold artifacts **deleted** from the graph | Abstention rate; false-answer rate | C3 — the differentiator |
| **S3 Time-adjacency traps** | A commit lands near an unrelated discussion with no reference | System must not link them | The "no inferred causality" claim (FR-9, Risks) |
| **S4 Cross-scope isolation** | Questions asked in workspace A about content only in B | Zero leakage | AC-15 |
| **S5 Fabrication probes** | Inject a fake citation id / altered quote into model output | 0 unverified citations reach user | AC-8, AC-12 |
| **S6 Link recovery** | Held-out Jira key ↔ PR/commit links in SEOSS 33 / Apache sets | Precision/recall of edges | C1 only; sanity, not headline |

Size is a starting plan. Report confidence intervals; with ~100 items per set, differences under ~8–10 points are not reliable.

### 3.5 Baselines (what "different" must be measured against)

| Baseline | Purpose |
|---|---|
| B0 closed-book LLM | Memorisation floor. Code-QA-Bench found "why" questions score highest closed-book, so also keep a **post-cutoff** slice (artifacts newer than the model's training cutoff) |
| B1 `git log`/`blame` + LLM | What an engineer does today |
| B2 Vector RAG over the same raw artifacts, no graph, no verification | Isolates the graph + verification contribution |
| B3 General coding agent with repo + tracker tools (e.g. SWE-QA-Agent style) | Strong agentic competitor |
| System | Full pipeline |
| System − verifier | Ablation: shows the citation check is what matters |

Same LLM across rows; only the retrieval/verification differs.

### 3.6 Metrics

- Claim support rate: share of claims marked `supported` whose quote verifies verbatim and entails the claim (human or LLM-judge audited on a sample).
- Evidence recall / precision against gold set.
- **Hallucinated-citation rate** (target 0 reaching the user).
- **Abstention F1** on S1 + S2 together (answer when answerable, refuse when not). AbstentionBench shows this is where current models are weakest.
- Answer correctness via checklist of atomic gold facts (RepoProbe's protocol).
- Cost and latency per question.

### 3.7 How this proves "different and useful"

- **Different:** wins on S2/S3/S5 (honesty, no invented causality, no fabricated citations), where RAG and general agents are known to fail; matching them on S1 is enough there.
- **Useful:** S1 on real projects with humans-authored gold, plus a small time-to-answer study (engineer with/without tool on 10 real "why" questions) if resources allow.
- Do **not** headline SWE-bench: it measures patch generation, not this task. Use it only as a repo/issue↔PR source.

### 3.8 Risks and cautions

- Mailing list ≠ Slack: say so in any report.
- Contamination: public projects are in model training data; the post-cutoff slice and the closed-book baseline are mandatory, not optional.
- Licenses: Apache mail archives, GitHub content and Slack exports each have terms; Slack data from private workspaces must not be redistributed. Record license per source in a manifest.
- Gold effort is the cost: roughly 3–6 minutes per question for a careful annotator (estimate, [unverified]).
- Counts above from search snippets (CoReQA pairs, LinkRank sizes, SWE-QA 576 vs 720) vary by version; pin versions when downloading.

## 4. Proposed folder layout (not yet created)

```
data/
  RESEARCH.md          this file
  MANIFEST.md          per source: URL, version/DOI, license, retrieval date, hash
  raw/                 untouched downloads (gitignored if large)
  corpus/              normalised envelopes for ingestion
  gold/                questions + gold evidence + quotes (jsonl)
  eval/                runners and results
```

## 5. Next steps (needs your decision)

1. Choose the families to start with. Recommendation: **Apache Kafka (KIPs) + Python (PEPs)**, one Jira-style and one GitHub-only, because decisions are explicit and both have public discussion.
2. Approve this as spec input; add FR/AC items for the evaluation set (the repo is in the specification phase — `genesis` tracking, no implementation code written).
3. Then: download SEOSS 33 and the Public Jira Dataset for S6 first (cheapest, fully public), build the MANIFEST, then author S1 gold for ~20 questions as a pilot to measure annotation cost before scaling.

## Sources

- SEOSS 33: Harvard Dataverse DOI 10.7910/DVN/PDDZ4Q; see also https://sep.cs.ut.ee/Main/Datasets
- Public Jira Dataset: https://zenodo.org/doi/10.5281/zenodo.5882881 ; paper https://arxiv.org/abs/2201.08368
- Mining Issue Trackers survey: https://arxiv.org/pdf/2403.05716
- ILADD: https://wwwmatthes.in.tum.de/pages/9gvnwulxb4in/Issues-Labeled-Architectural-Design-Decisions-ILADD
- DRMiner: https://arxiv.org/pdf/2405.19623
- Slack disentangled chats: https://2020.msrconf.org/details/msr-2020-Data-showcase/10/Software-related-Slack-Chats-with-Disentangled-Conversations
- Gitter: https://arxiv.org/pdf/2107.05823 ; GitterCom https://2020.msrconf.org/details/msr-2020-Data-showcase/11/GitterCom-A-Dataset-of-Open-Source-Developer-Communications-in-Gitter ; F2Chat https://github.com/panshengyi/F2Chat
- DevGPT: https://arxiv.org/pdf/2309.03914
- RepoProbe: https://arxiv.org/abs/2608.04783
- Code-QA-Bench: https://arxiv.org/abs/2605.29277
- SWE-QA: https://arxiv.org/html/2509.14635v1 ; CoReQA https://arxiv.org/pdf/2501.03447
- SWE-bench: https://github.com/SWE-bench/SWE-bench
- LinkRank: https://arxiv.org/pdf/2607.23610 ; LLM-assisted issue-commit linking https://arxiv.org/pdf/2605.00447
- AbstentionBench: https://arxiv.org/abs/2506.09038
- GH Archive mirror (ODC-By, 2011–2015 only): https://huggingface.co/datasets/open-index/open-github
