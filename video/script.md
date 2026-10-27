# Engineering Memory — hackathon video script (v5, compressed)
Voice: Sarvam Bulbul v3, default speaker **ratan** (en-IN), NO voice cloning. Pace 0.92 (slower than the old 1.05). Each segment gets ~0.8 s of breathing room at the end; the video for every segment is cut to the exact voice length, so nothing races or stalls. Soft bed music under narration (rebuild.sh).
Rules: never say "mail", "email" or "Slack" — always "discussion chats". Numbers only from deck-content/numbers-canonical.md + the locked demo numbers. No accuracy %.
Play order (alist.txt / vlist.txt): S1 S2 S3 S5 S4 S7 S8 S9. IDs are tied to their visuals: S4 = Playwright live demo (seg/S4.mp4 via build_s4.py); S1 S2 S3 S5 S7 S8 S9 = Remotion compositions with the same id. S6 (old Remotion mock-browser scene) is retired — the real app footage in S4 replaces it.
Only narration goes under each `## Sk` heading (tts.py reads everything up to the next heading).
Target length: about 4:00–4:30.

## S1 — The problem
Every team has code nobody can explain. Why is the retry limit three? Why does this flag have to stay on? The person who knew has moved on. The code is still here. But the reason behind it is gone, buried in old pull requests, tickets, and discussion chats. So an engineer goes hunting. Jira, then GitHub, then discussion chats, tab after tab. Hours lost, just to answer one why. That lost why is the real cost.

## S2 — Our direction
So we didn't build another chatbot. We asked a simpler question: what makes a why-answer trustworthy? Two rules. One: only use links people already wrote down. A reply, a ticket number in a message, a pull request holding a commit. No guessing. Two: every claim must carry an exact quote from the source, and plain code checks it, word for word. If the proof isn't there, we say: not established.

## S3 — How we built it
We built it in three steps. First, an evidence graph: GitHub, Jira, and discussion chats, each item stored with only its written links. Second, an agent that works like a careful engineer: understand, plan, gather, check, then answer, and go back for more when the evidence is thin. Its tools are read-only, and it can only open what it has seen. Third, a workbench anyone on the team can use, on any compatible model. We run it on Sarvam. Put together, that's Engineering Memory: one linked graph of your team's history, and answers that cite it.

## S5 — Why it's different
So how is this different from what's already out there? Search finds documents. Chatbots sound confident. RAG grabs chunks and hopes. None of them can show you why. Even with good links, the evidence can be incomplete. And a model can still explain the right documents wrong. So we added a separate check. The model proposes claims, each with a source and a quote. Then plain code checks that every quote really appears, word for word, in the source. Anything unsupported is thrown out. If nothing holds up, the answer is simply: not established. AI can suggest what happened. The evidence decides what we can claim.

## S4 — Live demo
Here's the real product, a local build of the same app we host. Its front page leads with the architecture and how linking works, then the tests and results, right next to each other. Everything we claim, you can check. This is the Kafka demo workspace: 1,201 items from discussion chats, Jira, GitHub, and ten KIP pages, joined by 2,194 links. Let's open a saved investigation. Why did Kafka producers in 3.0 and 3.1 stay non-idempotent by default? Each claim carries its sources: a KIP thread, a pull request, a commit. The one point it couldn't prove is marked Unknown, not guessed. And the trace shows every step.

## S7 — Proof, in plain words
The demo workspace has 1,201 items and 2,194 links. The evaluation set on its own: 1,191 items and 1,786 links. Our headline question is that idempotence investigation. Its claims trace to a KIP thread, a pull request, and a commit. The aim: hours of digging, down to minutes in one place. That's a goal, not yet measured. A first end-to-end check with Sarvam passed five of seven cases. Without any model, fully reachable questions went from one of eighteen to nine of eighteen. Four hundred forty-five tests pass, seven skipped. And our seventy-five-question gold set has traps built in. It isn't human-reviewed yet, so we won't quote an accuracy number.

## S8 — Architecture: the linkage engine
Under the hood, two pieces work together. The first is the linkage engine. It reads how engineers already connect their work. A reply becomes REPLIES_TO. A ticket key in a message becomes REFERENCES. A pull request holding a commit becomes CONTAINS. Only links people wrote down, never guessed. We call it engineering evidence linking. The second is the agent: understand, plan, retrieve, check, answer, and verify, with guardrails in code. Together, they give you a trail from question to evidence that you can audit.

## S9 — What's next
Today, you meet one agent answering why-questions. But underneath, it's already a shared memory for the team: discussion chats, tickets, code, and decisions, linked in one graph, with answers that cite it. Next, we make that memory versioned, so newer decisions can replace older ones when the trail says so. Later, agents for research, review, and planning can all share that same base. Engineering Memory: answers you can check, or an honest "not established".
