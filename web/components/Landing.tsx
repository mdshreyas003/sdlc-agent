import Link from "next/link";
import type { ReactNode } from "react";
import { btnAccent, btnGhost } from "./ui";

// Guided, doc-style landing page at "/" (the workspace list lives at /workspaces). Static content only.
// Every number comes from the team's canonical numbers sheet: early, single-run results on a gold set
// that is not yet human-verified. Section order = the reading path in /workspace/simple/path.md.

const SECTIONS = [
  ["overview", "What it is"],
  ["model", "The mental model"],
  ["architecture", "Architecture"],
  ["linking", "How linking works"],
  ["agent", "The agent's flow"],
  ["guardrails", "Does and refuses"],
  ["different", "Why it stands out"],
  ["tests", "How we test it"],
  ["results", "Results so far"],
  ["next", "Status and what's next"],
  ["glossary", "Glossary"],
] as const;

type Id = (typeof SECTIONS)[number][0];

function Section({ id, children }: { id: Id; children: ReactNode }) {
  const i = SECTIONS.findIndex(([s]) => s === id);
  const next = SECTIONS[i + 1];
  return (
    <section id={id} className="scroll-mt-8 border-b border-line py-12">
      <p className="font-mono text-[12px] text-accent">{String(i + 1).padStart(2, "0")}</p>
      <h2 className="mt-1 text-[24px] font-semibold tracking-tight">{SECTIONS[i][1]}</h2>
      <div className="mt-5 space-y-4 text-[14.5px] leading-relaxed text-mute">{children}</div>
      {next && (
        <a href={`#${next[0]}`} className="card card-link mt-8 flex items-center justify-between px-5 py-3">
          <span className="text-[12px] text-dim">Next</span>
          <span className="text-[14px] font-medium text-fg">{String(i + 2).padStart(2, "0")} · {next[1]} {"\u2192"}</span>
        </a>
      )}
    </section>
  );
}

const B = ({ children }: { children: ReactNode }) => <b className="font-semibold text-fg">{children}</b>;
const C = ({ children }: { children: ReactNode }) => <code className="rounded bg-raised px-1 font-mono text-[12.5px] text-fg">{children}</code>;
const Arrow = ({ label }: { label?: string }) => (
  <span aria-hidden className="flex flex-col items-center justify-center px-1 text-dim">
    {label && <span className="font-mono text-[10px] text-accent">{label}</span>}{"\u2192"}
  </span>
);

function Strip({ items, labels }: { items: [string, string][]; labels?: string[] }) {
  return (
    <div className="flex items-stretch">
      {items.map(([t, d], i) => (
        <div key={t} className="contents">
          {i > 0 && <Arrow label={labels?.[i - 1]} />}
          <div className="card min-w-0 flex-1 p-3">
            <p className="text-[13px] font-semibold text-fg">{t}</p>
            <p className="mt-1 text-[12px] text-dim">{d}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="card overflow-hidden">
      <table className="w-full text-left text-[13px]">
        <thead className="bg-panel text-dim"><tr>{head.map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-line align-top">{r.map((c, j) => <td key={j} className={`px-4 py-2.5 ${j === 0 ? "font-medium text-fg" : ""}`}>{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

const Cards = ({ items, cols = 2 }: { items: [string, ReactNode][]; cols?: 2 | 3 }) => (
  <ul className={`grid gap-3 ${cols === 3 ? "grid-cols-3" : "grid-cols-2"}`}>
    {items.map(([t, d]) => <li key={t} className="card p-4"><p className="text-[14px] font-semibold text-fg">{t}</p><div className="mt-1.5 text-[13px]">{d}</div></li>)}
  </ul>
);

export default function Landing() {
  return (
    <div className="theme-dark h-full overflow-auto bg-bg text-fg">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between px-8">
          <span className="text-[14px] font-semibold">Engineering Memory <span className="ml-2 font-normal text-dim">prototype guide</span></span>
          <nav className="flex items-center gap-2">
            <a href="https://github.com/mdshreyas003/sdlc-agent" className={btnGhost}>GitHub</a>
            <Link href="/workspaces" className={btnGhost}>Workspaces</Link>
            <Link href="/w/acme-demo" className={btnAccent}>Try the demo</Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1180px] gap-12 px-8">
        <aside className="sticky top-14 h-[calc(100vh-3.5rem)] w-[220px] shrink-0 overflow-auto py-10">
          <p className="label mb-3">Guided path</p>
          <ol className="space-y-0.5">
            {SECTIONS.map(([id, t], i) => (
              <li key={id}>
                <a href={`#${id}`} className="flex gap-3 rounded-md px-2 py-1.5 text-[13px] text-mute hover:bg-hover hover:text-fg">
                  <span className="w-5 font-mono text-[11.5px] text-dim">{String(i + 1).padStart(2, "0")}</span>{t}
                </a>
              </li>
            ))}
          </ol>
        </aside>

        <main className="min-w-0 max-w-[820px] flex-1 pb-24">
          <Section id="overview">
            <p className="text-[26px] font-semibold leading-snug tracking-tight text-fg">
              Ask <span className="text-accent">&ldquo;why is this code like this?&rdquo;</span> and get an answer from your team&rsquo;s GitHub, Jira and chat history, with a word-for-word quote for every claim, or an honest <span className="text-accent">&ldquo;Not established.&rdquo;</span>
            </p>
            <p>Built for engineers about to change or debug code they didn&rsquo;t write. The reasons behind code are scattered across pull requests, tickets and chat threads; this prototype gathers them and answers only with proof.</p>
            <p>This page walks through everything in order. Each section ends with a <B>Next</B> link; the left sidebar jumps anywhere.</p>
            <div className="flex gap-3 pt-2">
              <Link href="/w/acme-demo" className={`${btnAccent} h-10 px-5 text-[13.5px]`}>Try the demo</Link>
              <Link href="/workspaces" className={`${btnGhost} h-10 px-5 text-[13.5px]`}>All workspaces</Link>
            </div>
          </Section>

          <Section id="model">
            <p className="text-[18px] text-fg">Think of a <B>librarian who only answers with exact quotes from the shelves</B>.</p>
            <Cards items={[
              ["The shelves", "Your team's history: commits, pull requests, tickets, chat threads."],
              ["The strings between books", "Links a person actually wrote down, like a ticket number in a chat message. Never added by guessing."],
              ["Every answer", "Every sentence points to a quote that really exists, word for word."],
              ["No proof?", <>The answer is <B>&ldquo;Not established.&rdquo;</B> It never guesses to fill the gap.</>],
            ]} />
            <p>The AI model may <i>suggest</i> an answer. Plain code checks it and makes the final call.</p>
          </Section>

          <Section id="architecture">
            <p>Five layers, one platform: data sources plug in on one side, people or other agents ask on the other.</p>
            <Strip items={[
              ["1 · Sources", "GitHub · Jira · Slack / mailing lists"],
              ["2 · Evidence graph", "every item + explicit links (Neo4j)"],
              ["3 · Memory", "versioned decisions with history"],
              ["4 · Agent", "read-only tools + quote checker"],
              ["5 · App / API", "web workbench · HTTP API"],
            ]} />
            <ul className="list-disc space-y-1.5 pl-5">
              <li><B>Sources.</B> Connectors pull pull requests, commits, Jira tickets and comments, and Slack threads.</li>
              <li><B>Evidence graph.</B> Each item becomes one node. A link exists only where a source says so.</li>
              <li><B>Memory.</B> Repeated evidence becomes a decision with a history (&ldquo;retries capped at 3, because…&rdquo;). A newer version replaces an older one without deleting it. Memory only points the agent to evidence; it is never quoted itself.</li>
              <li><B>Agent.</B> Answers <i>why / debug / is-it-safe-to-change</i> questions with fixed, read-only graph tools; a checker verifies every quote.</li>
              <li><B>App and API.</B> Use it as a web app (the workbench) or call the same thing as a service.</li>
            </ul>
          </Section>

          <Section id="linking">
            <p>Only <B>three kinds of link</B>, each from something written in the source:</p>
            <Table head={["Link", "Meaning", "Found from"]} rows={[
              ["REPLIES_TO", "a reply belongs to its thread", <>the source says so: Slack <C>thread_ts</C>, GitHub <C>in_reply_to_id</C></>],
              ["CONTAINS", "a pull request contains a commit", "GitHub's own list of the PR's commits"],
              ["REFERENCES", "one item mentions another", <>the source's structure (a comment belongs to its PR or ticket), or an ID typed in the text: a Jira key like <C>KAFKA-18654</C>, a PR or commit URL, <C>#123</C> inside GitHub, a Slack permalink</>],
            ]} />
            <p><B>Never</B> by similar words, similar meaning, or timing. Matching is strict: <C>UTF-8</C>, <C>SHA-256</C> and a colour like <C>#333</C> are ignored, and each text link records the exact field and character span it came from (e.g. <C>$.title#0-11</C>).</p>
            <p className="pt-2 text-fg">A real example from the Kafka data (KIP-890), run through the real extraction code:</p>
            <div className="card space-y-3 p-4">
              <Strip labels={["REPLIES_TO"]} items={[["Calvin Liu's mail, Feb 2025", "“…the performance issue in …/browse/KAFKA-18654…”"], ["Mail thread", "[DISCUSS] KIP-890 Server Side Defense"]]} />
              <Strip labels={["REFERENCES (key in text)"]} items={[["Calvin Liu's mail", "mentions KAFKA-18654"], ["Jira KAFKA-18654", "the ticket"]]} />
              <Strip labels={["REFERENCES (key in title)"]} items={[["PR #18720", "“KAFKA-18654 [1/2]: Transaction Version 2 performance regression…”"], ["Jira KAFKA-18654", "the same ticket"]]} />
              <Strip labels={["CONTAINS"]} items={[["PR #18720", "GitHub's list of the PR's commits"], ["Commit ab8ef87", "“KAFKA-18654 … (#18720)”"]]} />
            </div>
            <p>So a question about <i>why the broker retries on its own</i> can travel from the mailing-list discussion to the Jira ticket to the code change, each step a link someone wrote down. (The Kafka mailing list is stored in the Slack format as a stand-in for chat.)</p>
          </Section>

          <Section id="agent">
            <Strip items={[["Understand", "restate"], ["Seed", "exact IDs"], ["Plan", "pick tools"], ["Retrieve", "search + 1 hop"], ["Evaluate", "enough?"], ["Synthesize", "claims + quotes"], ["Verify", "code decides"]]} />
            <ol className="list-decimal space-y-1.5 pl-5">
              <li><B>Understand:</B> the AI model restates what is asked and which things it names.</li>
              <li><B>Seed:</B> code (no AI) pulls exact IDs from the question (ticket keys, PR numbers, commit hashes, file paths) and looks them up directly.</li>
              <li><B>Plan:</B> the AI model picks which fixed graph tools to call next (up to 5 per round).</li>
              <li><B>Retrieve:</B> the tools run read-only searches; code then follows one hop of links from the best hits (the <i>expand</i> step).</li>
              <li><B>Evaluate:</B> the AI model judges if the evidence is enough; if not, back to Plan, at most 3 rounds.</li>
              <li><B>Synthesize:</B> the AI model writes claims, each with a source ID and a word-for-word quote.</li>
              <li><B>Verify:</B> code checks every quote against the full source text, drops failures, and decides &ldquo;established&rdquo; or &ldquo;Not established&rdquo;.</li>
            </ol>
          </Section>

          <Section id="guardrails">
            <p><B>Does:</B> read-only searches through 5 fixed tools (<C>find_text</C>, <C>file_history</C>, <C>neighbors</C>, <C>evidence_chain</C>, <C>get</C>), plus one guarded escape hatch (<C>cypher_query</C>) whose generated query may only <i>find</i> IDs; rows are re-read through a fixed template.</p>
            <p className="text-fg">Refuses:</p>
            <Cards items={[
              ["No writes", <>Write words (<C>CREATE</C>, <C>DELETE</C>, <C>SET</C>…) blocked in code; read-only route; every template EXPLAIN-checked at startup; every query time-limited.</>],
              ["No invented IDs", "Only items already seen in evidence or named in the question can be opened. A made-up or malformed ID never reaches the database."],
              ["No paraphrased quotes", "A citation survives only if its quote is word for word in that item's own text. Made-up IDs, misquotes, quotes copied from a quoted parent, cut-off quotes and quotes from the wrong named person are dropped."],
              ["No guessing", <>Established only if the final evidence check says &ldquo;enough&rdquo; <B>and</B> a claim still has a verified quote. Otherwise: &ldquo;Not established&rdquo;, whatever the model wrote.</>],
            ]} />
          </Section>

          <Section id="different">
            <Table head={["", "Engineering Memory", "Mem0 · Zep/Graphiti · GraphRAG", "Coding agents"]} rows={[
              ["Links", "only links a person wrote down", "relations extracted or inferred by an LLM", "not about team history"],
              ["Proof", "word-for-word quote, checked in code", "traceable sources or record IDs, not checked quotes", "tests and linters check code edits"],
              ["When unsure", "“Not established”, enforced in code", "prompt-level or not measured", "not documented"],
              ["Database access", "fixed read-only tools + ID guard", "not their focus (memory layers)", "sandbox or permission rules"],
            ]} />
            <Cards items={[
              ["Links you can trust", "Only explicit links, so no made-up connections."],
              ["Quotes checked by code", "Not by the model."],
              ["“I can't prove it” is built in", "A real answer, not a hope written into a prompt."],
              ["A test set with traps", "Questions with the evidence removed, or that only look related in time. The right answer is to abstain."],
            ]} />
          </Section>

          <Section id="tests">
            <p><B>An automated test</B> runs a piece of code on a known input and checks the result, every time the code changes. Three real ones:</p>
            <Cards items={[
              ["Links are strict", <>A PR body with &ldquo;Fixes PAY-412 … see #190 and UTF-8, SHA-256, OTHER-9; color: #333&rdquo; must give exactly 3 links (PAY-412, the Slack thread, PR #190), never <C>UTF-8</C>, <C>SHA-256</C> or <C>#333</C>.</>],
              ["Bad IDs never reach the DB", <>An unseen ID, or <C>x{"}"}) DETACH DELETE (n //</C>, is refused before the database is touched.</>],
              ["Misquotes are dropped", "Of three citations, the made-up ID and the misquote are dropped; only the exact quote “Fixes PAY-412” survives, and confidence drops to low."],
            ]} cols={3} />
            <p><B>The 7-question gate:</B> a real AI model, end to end, on a small made-up company (&ldquo;Acme&rdquo;). 4 answerable questions (retries capped at 3, session TTL of 15 minutes, can I raise MAX_RETRIES to 10, a logged-out-mid-checkout traceback), 2 that must say &ldquo;Not established&rdquo; (why Redis, why Kafka), and 1 check that another workspace sees nothing.</p>
            <p><B>The 75 gold questions</B> over real Apache Kafka history, each with the exact quotes that answer it; 19 for tuning, 56 held back for the final test.</p>
            <Table head={["Tier", "Count", "What it checks"]} rows={[
              ["A", "16", "answer is in one item"],
              ["B", "24", "answer needs several linked items"],
              ["C", "20", "an A/B question with its evidence removed → must say “Not established”"],
              ["T", "10", "traps: two items close in time but not linked → must say “Not established”"],
              ["N", "5", "nothing in the data answers it"],
            ]} />
            <blockquote className="card border-l-2 border-l-accent p-4 text-[13.5px]">
              <span className="text-dim">Q050, tier B:</span> <i className="text-fg">&ldquo;Why does the broker retry AddPartitionsToTxn on its own when it hits CONCURRENT_TRANSACTIONS, with separate backoff settings, instead of just returning the error to the producer to retry?&rdquo;</i> The gold answer quotes Calvin Liu&rsquo;s mail, Jira KAFKA-18654 and a follow-up reply: the chain from section 04.
            </blockquote>
          </Section>

          <Section id="results">
            <p className="text-[13px] text-dim">Early numbers: one run each, on a question set not yet human-checked.</p>
            <Cards cols={3} items={[
              ["1,191 items · 1,786 links", "real Kafka data across 10 design proposals (KIPs)"],
              ["5 / 7", "real-model gate passed (Sarvam model); the 2 misses answered with low confidence"],
              ["5/5 · 26/27", "quotes kept on Kafka questions Q030 · Q050"],
              ["Q006", "no answer in the data: correctly “Not established”"],
              ["6/33 → 19/33", "gold sources reachable; questions fully reachable 1/18 → 9/18; 0 regressions (no AI involved)"],
              ["445 passed", "automated tests (7 skipped)"],
            ]} />
            <p>Benchmark on all 75 questions: <B>next</B>.</p>
          </Section>

          <Section id="next">
            <p><B>Built and running:</B> sources → evidence graph with explicit links → guarded agent and quote checker → API and web workbench, plus the benchmark harness.</p>
            <ul className="list-disc space-y-1.5 pl-5">
              <li><B>Memory:</B> versioned decisions with history (design accepted).</li>
              <li><B>Two more link types:</B> <C>decides</C> and <C>supersedes</C>.</li>
              <li><B>Live sync:</B> resume from a saved position instead of a full re-pull.</li>
              <li><B>Benchmark:</B> human-check all 75 questions, then compare against no-retrieval, keyword search (BM25) and an outside system (Graphiti).</li>
              <li><B>Later:</B> more sources (wikis, CI logs, incidents), one identity per person across tools, and access for other agents over the API.</li>
            </ul>
          </Section>

          <Section id="glossary">
            <dl className="grid grid-cols-[140px_1fr] gap-x-6 gap-y-2.5">
              {[
                ["Agent", "an AI program that takes steps (search, read, decide) to answer a question"],
                ["Graph", "a map of items (dots) and the links between them (lines)"],
                ["Link", "a connection between two items that a person actually wrote down"],
                ["Commit", "one saved change to the code"],
                ["Test", "a small automatic check that the code still does what it should"],
                ["Gold question", "a question whose correct answer and quotes were written in advance, used to grade the system"],
                ["Citation", "the exact source and word-for-word quote behind a sentence"],
                ["Abstain", "to say “Not established” instead of guessing"],
              ].map(([t, d]) => <div key={t} className="contents"><dt className="font-medium text-fg">{t}</dt><dd>{d}</dd></div>)}
            </dl>
            <div className="pt-4"><Link href="/w/acme-demo" className={`${btnAccent} h-10 px-5 text-[13.5px]`}>Try the demo {"\u2192"}</Link></div>
          </Section>
        </main>
      </div>
    </div>
  );
}
