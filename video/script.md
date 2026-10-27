# Engineering Memory — hackathon video script (v4.2)
Voice: Sarvam Bulbul v3 speaker **ratan** (en-IN), pace ~1.05. Pause between beats. Soft bed music under narration; lift on demo beats. One paragraph = one segment. On-screen: never say "mail", "email", or "Slack" — always "discussion chats".

Target length: about 5:30–6:00 (active journey; longer than the 4-minute draft; not the short Acme-only cut).

## YouTube chapters (~5:50)
```
0:00 The problem of lost reasoning
0:40 No-guessed-links design
1:10 The MVPs
1:55 Why search falls short
2:30 Verification as the differentiator
3:10 Live product demo
3:55 Proof with numbers
4:45 Architecture: the linkage engine
5:30 The future vision
```

## S1 — The problem we discovered
When the person who knew why leaves, the answer is often sitting in a discussion thread from two years ago — and nobody can find it. Every team has someone who knows why the code is the way it is — why the retry limit is three, why a configuration flag must stay enabled, why a service was never migrated. The code stays. The reasoning disappears into old pull requests, tickets, and discussion chats. A developer can read what the code does. Reading the code does not tell them why the team made that decision. So they burn hours hopping Jira, then GitHub, then discussion chats — reloading context each switch, holding half a dozen tabs in their head just to answer one why. That is wasted time, wasted effort, and heavy context switching. Scattered history is the problem. Lost "why" is the cost — paid in engineer hours.

## S2 — How we headed toward a solution
We did not start by building another chatbot. We asked: what would make a why-answer trustworthy? First, only use links people already wrote down — a reply in a thread, a ticket key in a message, a pull request that contains a commit. No guessing edges. Second, every claim must carry a word-for-word quote, checked by plain code. If the proof is missing, the system must say "Not established". That direction shaped every MVP that followed.

## S3 — What the MVPs are (the journey)
MVP one: an evidence graph. Connectors pull GitHub, Jira, and discussion chats. Ingest turns each item into a node, with only its explicit links, in Neo4j. MVP two: a specialized agent loop. Understand the question, seed exact IDs, plan, retrieve, evaluate, synthesize, then verify — up to a few bounded rounds when evidence is thin. Guardrails in code: read-only tools, an ID guard so the agent only opens what it has seen, and a quote verifier. MVP three: a workbench you can use. FastAPI behind it, Next.js on top, any OpenAI-compatible model — we run Sarvam. Across these MVPs runs Engineering Memory: today that means the evidence graph plus verified Q&A with citations you can open — a versioned memory store that keeps lasting facts current comes next.

## S4 — How this differs from what already exists
Search finds documents. Chatbots talk. Generic RAG retrieves chunks and hopes. Coding agents write and edit code — they do not rebuild the team's decision history. Engineering Memory is different on three points. Links are explicit, not inferred. Answers must cite quotable evidence, or they abstain. The agent is a checked loop, not a single prompt. Wrong links are worse than missing ones — so we refuse to invent them. That is the critical problem we solved: trustworthy engineering "why", not just fluent text.

## S5 — The difference is in the verification
Even a well-connected graph can return incomplete evidence. And even a model with the right documents can get the explanation wrong. So we added a separate verification layer. The model proposes claims with their sources and quotations. Ordinary code checks whether each quotation appears word for word in the actual source. Unsupported claims and invalid citations are rejected. The model does not get to declare its own answer correct. If the evidence does not establish the answer, we say "Not established". The AI can suggest what happened. The evidence determines what we can claim.

## S6 — Live product: landing, onboard, ask
Open the hosted app and move with the journey — not a slide tour of the system. The landing page leads with architecture and how linking works, then tests and results together. Onboard is simple: connect data sources, land in a workspace, see items and the graph of links. Then ask a real why-question, watch the trace, and open every citation. Demo data today is live Apache Kafka — discussion chats, Jira, GitHub, and KIP pages — already linked, with saved investigations ready to open. Not a toy Acme sample.

## S7 — Proof, in plain words
Numbers only where we can stand behind them. Kafka demo workspace: over twelve hundred items, over two thousand explicit links — one thousand two hundred one items, two thousand one hundred ninety-four links. Eval corpus alone is one thousand one hundred ninety-one artifacts and one thousand seven hundred eighty-six links. One strong investigation: why Kafka producers in 3.0 and 3.1 stayed non-idempotent by default — claims with sources from a KIP thread, a pull request, a commit; one unproven point marked Unknown. Intended outcome for the engineer: hours of digging and tool-hopping cut to minutes in one workbench — less time, less effort, less context switching — not a measured before-and-after yet. Our preliminary Sarvam-powered end-to-end model gate passed five of seven cases. Without a model in the loop, fully reachable developer questions improved from one of eighteen to nine of eighteen, with zero regressions. Automated tests: four hundred forty-five passed, seven skipped. Our seventy-five-question gold set includes traps — evidence removed, records that look related but are not, or no answer in the data. Full accuracy waits on human review of that gold set — we will not fake that number.

## S8 — Architecture that makes it effective
Two architectures work together — this is the linkage engine as a category, plus the agent, not a passive walkthrough of boxes. First, the linkage engine: how commits, discussion chats, tickets, pull requests, and docs relate. A reply becomes REPLIES_TO. A ticket key in a message becomes REFERENCES. A pull request that holds a commit becomes CONTAINS. Only relationships people already wrote down — no guessed edges. That linkage capability is what turns scattered tools into one evidence graph. We see it as a new category: engineering evidence linking, not another search index. Second, the agent architecture: understand, seed, plan, retrieve, evaluate, synthesize, verify — with code guardrails so supported claims end in a quote you can open, and unknowns stay unmarked by fake cites. Together: a trail from question to linked evidence. That is effectiveness — not a black box score, but a relationship map you can audit.

## S9 — Future and close
Today you meet a single agent that answers why-questions from that graph — but the product is already bigger than one Q&A bot. Engineering Memory is present now as that graph-plus-cites system: linked evidence and verified answers, not a separate lasting-facts store. Underneath is a central knowledge base for the team's engineering history — one place where discussion chats, tickets, code, and decisions already relate. Next we deepen that base with a versioned memory layer — so newer decisions can supersede older ones when the trail says so. Ahead, that same base becomes the ground where different kinds of agents work together — research, review, and planning — each drawing from and writing back into one shared base. From here we grow the sources and measure harder against baselines. Engineering Memory: a central knowledge base you can trust — answers you can check, or an honest "Not established".
