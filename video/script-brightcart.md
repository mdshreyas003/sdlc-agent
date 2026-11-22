# Brightcart explainer - voice-over script

Silent video, black background, white bold text. You read the lines under each heading.
Pace: calm, about 140 words per minute. Each scene lasts words / 2.3 seconds + 1 second.
Brightcart is simulated. Say so.
Total: about 624 words (4:27 at 140 words per minute). Video length: 4:43 (283.4 s).

## BC1 - Hook (17.5s)

Your code has rules nobody remembers. A number sits in a file. It looks wrong. Nobody knows why it is there. The person who knew has left. The ticket is buried. This video shows how we fix that.

ON SCREEN: Your code has rules nobody remembers. / max_attempts = 3 / Why 3? Nobody knows.

## BC2 - The problem (23.2s)

A new engineer joins the team. Or an AI agent starts a task. It reads one line: try a payment at most 3 times. That looks too low. So it raises the number. But the reason is gone. The team loses hours. They hunt through tickets, team chat and pull requests.

ON SCREEN: A new engineer. Or an AI agent. / Try a payment at most 3 times. / Looks too low. Raise it. / The reason is gone. / Hours lost in tickets, team chat and pull requests.

## BC3 - The story (19.7s)

Meet Brightcart. It is a simulated online store. Everything here is invented. One day a payment outage hits. 214 customers are charged twice. The team sets a rule. A payment may be tried at most 3 times. Now the reason has a home.

ON SCREEN: Brightcart / A simulated online store. / 214 customers charged twice. / The team sets a limit: 3 / (screenshot: incident map)

## BC4 - What we built (21.9s)

Here is what we built. You connect your tools. You sync them. We build a connected map. You ask why, and you get quotes. A person approves a decision note. That is a short page: what the team chose, and why. Agents read the note before they edit.

ON SCREEN: 1 Connect your tools / 2 Sync / 3 We build a connected map / 4 Ask why. Get quotes. / 5 A person approves a decision note / 6 Agents read it before they edit

## BC5 - Easy start and sync (16.7s)

Starting is easy. One click opens a demo workspace. Or you connect GitHub, Jira and team chat. You test each connection. Then you press sync. Each source shows a live timeline. A log shows every step.

ON SCREEN: One click. A demo workspace. / Connect GitHub, Jira and team chat. / Test the connection. / Sync: a live timeline for each source / A log shows every step. (screenshots: sync, ingestion, if present)

## BC6 - Ask why (21.9s)

Now ask why. Click a line of code. You see who changed it. You see the ticket and the chat that explain it. Every claim comes with an exact quote. Our code checks that the quote is real. If there is no proof, the answer says Not established.

ON SCREEN: Click a line of code. / Who changed it. / Which ticket. / Which chat. / Every claim has an exact quote. Code checks the quote. / No proof? Not established. (screenshot: blame, if present)

## BC7 - The decision note and its life (24s)

A decision note has a life. First it is a draft. A person approves it. Then agents can read it. Later, a new pull request adds evidence. The update waits for review. The old version stays live. One day a newer decision replaces it. The old note is retired. It keeps the reason.

ON SCREEN: Draft / A person approves / Agents read it / A later pull request updates it / Waits for review. The old version stays live. / A newer decision retires the old one. With the reason. (screenshots: overview, staged update, retired)

## BC8 - The catch (27.5s)

Here is the catch. A coding agent opens a pull request. It wants to raise the limit from 3 to 8. Before it edits, it asks our memory tool. The tool says three approved notes apply. One rule says this change needs a reliability review. One decision says at most 3 times. One rule says every payment needs a unique ID.

ON SCREEN: A coding agent opens a pull request. / Raise the limit from 3 to 8. / Before it edits, it asks memory. / 3 approved notes apply: rule: reliability review needed / decision: at most 3 times / rule: every payment has a unique ID

## BC9 - It keeps up (22.7s)

The map keeps up. A new chat thread arrives. It joins the map. Records grow from 36 to 40. Links grow from 63 to 69. Two days later, someone corrects a ticket. Every note that cites that ticket shows: source changed. A person checks it. Nothing goes stale in silence.

ON SCREEN: A new chat thread joins the map. / Records: 36 to 40 / Links: 63 to 69 / Two days later: a ticket is corrected. / Source changed. / A person checks it. (screenshots: before, after, source changed)

## BC10 - Who it is for (24.5s)

Who is this for? Engineering managers, who want to see why. Platform teams that roll out coding agents. Security and compliance leads, who need proof. Support leads, who ask why a rule exists. New engineers, who must learn fast. The price is 1,999 rupees per repo per month. Agents are never counted as seats.

ON SCREEN: Engineering managers: see why. / Platform teams: roll out coding agents. / Security and compliance leads: get proof. / Support leads: know why a rule exists. / New engineers: learn fast. / 1,999 rupees per repo per month. Agents are never seats.

## BC11 - Proof and honesty (45.8s)

Now the proof. We used real Kafka data: 1,201 items and 2,194 links. Out of 18 questions, plain search could fully answer 1. With the connected map: 9. No model was used for that count. A first check with a real model passed 5 of 7 cases. We have 75 gold questions. No person has checked them yet. So we give no accuracy number. 366 tests pass. If there is no proof, we say Not established. Every quote is checked word for word. Nothing goes live without a person. A changed source is flagged. The shared demo is read-only. Agent tools are read-only.

ON SCREEN: Real Kafka data. 1,201 items. 2,194 links. / 18 questions, no model: plain search 1, connected map 9 / Real model, first check: 5 of 7 cases / 75 gold questions. Not checked by people yet. No accuracy number. / 366 tests pass / No proof: Not established. / Every quote checked word for word. / Nothing goes live without a person. / A changed source is flagged. / Shared demo: read-only. Agent tools: read-only.

## BC12 - Close (18s)

Memory your team can check. And your agents can obey. Think of a software factory. Agents write the code. We guard it, and we remember why. That memory feeds the next agent. Brightcart is simulated. The idea is real.

ON SCREEN: Memory your team can check. / And your agents can obey. / Agents write. / We guard and remember. / Memory feeds the next agent. / Brightcart is simulated.
