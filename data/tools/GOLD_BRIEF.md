# Brief: draft gold questions for one KIP

You are drafting benchmark questions for a "why is the code like this?" system. Your KIP number is N (given in your task).

## Inputs
- Material file: `C:\Users\mohi_shr\AppData\Local\Temp\claude\C--Users-mohi-shr-source-repos-hackfront\662b8a82-20f1-4654-b521-9edaf785e8d4\scratchpad\kip\KIP-N.txt`
  - It is large. Read the top part (the ANSWER KEY, about 14k characters) first, then use Grep and ranged Reads to find the supporting artifacts. Do not read the whole file.
  - The ANSWER KEY is the KIP wiki page. It is NOT in the system's graph. It only tells you what the reasons are.
  - After `# CORPUS ARTIFACTS`, every artifact starts with `## <url>` (mailing-list message, Jira issue/comment, PR, commit). These urls are what the system cites.
- Verifier: `cd C:\Users\mohi_shr\source\repos\hackfront\data\tools && uv run --no-project python verify_gold.py <your file>.jsonl` checks every url and quote. Run it before you finish and fix every error.

## Output
Write `C:\Users\mohi_shr\AppData\Local\Temp\claude\C--Users-mohi-shr-source-repos-hackfront\662b8a82-20f1-4654-b521-9edaf785e8d4\scratchpad\draft\KIP-N.jsonl`, one JSON object per line:

```
{"kip": N, "tier": "A|B|T|N", "question": "...", "gold_facts": ["short atomic fact", ...],
 "gold_evidence": [{"url": "<corpus url>", "quote": "<verbatim text from that artifact, 40-250 chars>"}], "note": "why this is a good question"}
```
Create the `draft` folder if needed. Valid JSON only (escape quotes and newlines).

## What to write (per KIP)
- 4 answerable questions, at least 2 of tier B.
  - Tier A: the reason is stated in ONE corpus artifact. Tier B: you need two or more different artifacts (for example a Jira comment plus a mailing-list reply, or a commit message plus a mail thread) to state or confirm the reason.
- 1 tier T (time-adjacency trap). Find a commit/PR/Jira issue and a mail message that are close in time or topic but where neither names the other (check by grep: no shared Jira key, PR number or URL between them). Question form: "Was <the change, in words> made because of <the discussion, in words>?" `gold_evidence` holds both urls with a short verbatim quote from each. The correct system answer is "not established". Put in `note` what you checked.
- If your task says to include the extra N question: 1 tier N. A natural "why" question about this feature whose reason is NOT stated in any corpus artifact (and ideally not in the answer key either). `gold_evidence` is empty. Grep to be sure no artifact answers it.

## Rules for questions
- Write like an engineer reading the code or config: "Why does X do Y instead of Z?". Never include urls, Jira keys (KAFKA-123), PR numbers or commit hashes. Do not say "according to the thread".
- It must ask for the REASON, not just a fact. The answer must be a decision plus its rationale.
- The answer must be supported by the corpus artifacts you cite, not only by the answer key. If the reason exists only in the answer key, do not use it.
- `gold_facts`: 2-4 short atomic facts a correct answer must contain (for example "ZooKeeper metadata is a scaling bottleneck"). Each must be checkable against the quotes.
- Quotes: copy verbatim from the artifact text in the material file (spaces and newlines are normalised, but words and punctuation must match exactly). Pick the sentence that states the reason. Do not paraphrase. Do not use `...`.
- Prefer artifacts from different senders or different kinds. Avoid very short or off-topic messages.
- Do not invent anything. If you cannot find enough good questions, write fewer and say so.

## Finish
Reply with one line: the path you wrote, counts per tier, and the verifier's last line. Nothing else.
