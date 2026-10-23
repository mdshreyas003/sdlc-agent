# Data folder in pictures

Beginner guide. Four small ideas, one picture each. (Mermaid diagrams: open in VS Code with a Markdown preview, or on GitHub.)

## 0. The whole flow

```mermaid
flowchart LR
    A["Real public sources<br/>Kafka KIPs, Python PEPs"] -->|"pull_pilot.py"| B["data/raw/<br/>downloaded files + linked pages"]
    M["Kafka mailing list<br/>(monthly archives)"] -->|"pull_kafka_threads.py"| B
    B -->|"sha256 of every file"| H["raw/hashes.json<br/>proof of what we downloaded"]
    B --> G["gold/pilot_questions.jsonl<br/>20 questions + exact quote"]
    G -->|"verify_gold.py"| V{"Quote really<br/>in the source?"}
    V -->|"yes, all 20"| R["You review each question<br/>human_verified = true"]
    R --> E["Final test set<br/>to score your system"]
```

## 1. What a KIP and a PEP are

They are the "why" documents. A team writes one before a big change.

```mermaid
flowchart LR
    I["An idea<br/>'remove ZooKeeper'<br/>'add match statement'"] --> D["Proposal document<br/>explains WHY"]
    D --> T["Team discusses it<br/>(mail, forum)"]
    T --> Dec["Decision<br/>accepted or rejected"]
    Dec --> W["Work happens<br/>(tickets, PRs, commits)"]
```

| Name | Project | Meaning |
|---|---|---|
| **KIP** | Apache Kafka | Kafka Improvement Proposal |
| **PEP** | Python | Python Enhancement Proposal |

The product answers "why is the code like this?". The KIP or PEP is where the reason is written down on purpose, so it is the **answer key** for testing.

## 2. Your data model next to the dataset

```mermaid
flowchart TB
    subgraph yours["Your model (SPEC.md)"]
      direction LR
      C["Commit"] --- PR["Pull request"] --- IS["Issue ticket"] --- TH["Discussion thread"]
    end
    subgraph new["New in the dataset"]
      DOC["Decision document<br/>KIP / PEP"]
    end
    DOC -. "links to" .-> IS
    DOC -. "links to" .-> TH
    DOC -. "links to" .-> PR
```

Your four artifact types stay the same. The one addition is the **decision document**: it holds the gold answer and is not a graph node yet.

## 3. Which downloaded file is which of your types

```mermaid
flowchart LR
    F1["KIP-N/page.json<br/>PEP-N/pep.rst"] --> DOC["Decision document<br/>(answer key)"]
    F2["hop*.bin from issues.apache.org<br/>(Jira JSON)"] --> IS["Issue ticket"]
    F3["hop*.bin from github.com<br/>(issue/PR JSON)"] --> PR["Pull request / issue"]
    F4["hop*.bin from mail.python.org,<br/>discuss.python.org"] --> TH["Discussion thread"]
    F5["KIP-N/dev_thread.jsonl<br/>(Kafka mailing list)"] --> TH
    F6["links.json"] --> L["Explicit links found<br/>in the document"]
```

Counts after the Kafka mailing-list rebuild:

| What | How many |
|---|---|
| Decision docs | 20 (10 KIP, 10 PEP) |
| Jira issue tickets | 16 |
| GitHub issues or PRs | 10 |
| Python mail / forum threads | 30 |
| Kafka mailing messages (`dev_thread.jsonl`) | 1,070 across 10 KIPs |
| **Commits** | **0** |

## 4. What is missing

```mermaid
flowchart LR
    ok["Have:<br/>doc, ticket, discussion,<br/>a few PRs"] --> gap1["Missing: commits<br/>(none downloaded)"]
    ok --> gap2["Thin: PRs<br/>(only 10)"]
    ok --> gap3["Substitute: mailing lists<br/>instead of real Slack"]
```

Questions about the decision doc plus a discussion can be tested now. Questions about commits or code lines (like clicking `MAX_RETRIES = 3`) cannot, because no commits were pulled yet. Next step: pull the commits and PRs that the Jira tickets and GitHub links point to.

## 5. How a test will work later

```mermaid
flowchart LR
    Q["Question<br/>Why remove ZooKeeper from Kafka?"] --> S["Your system"]
    S --> A["Answer + citation + quote"]
    A --> C{"Quote matches the gold<br/>quote in the source?"}
    C -->|"yes"| P["Pass"]
    C -->|"no or made up"| F["Fail"]
    X["Question with no answer in the data<br/>(PEP-634 'why match statement')"] --> S2["Your system"]
    S2 --> N{"Says 'not established'?"}
    N -->|"yes"| P2["Pass"]
    N -->|"guesses"| F2["Fail"]
```

The bottom row is what makes the system different: most tools answer even when they should not.

## File map

| Path | What it is |
|---|---|
| `RESEARCH.md` | What datasets exist online, and the plan to compose one |
| `MANIFEST.md` | Sources, terms, results so far |
| `GUIDE.md` | This file |
| `raw/` | Downloaded originals (gitignored; `raw/hashes.json` is kept) |
| `gold/pilot_questions.jsonl` | 20 draft questions with exact quotes, awaiting your review |
| `tools/` | `pull_pilot.py`, `pull_kafka_threads.py`, `verify_gold.py` |
