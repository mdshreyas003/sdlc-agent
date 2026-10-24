import Link from "next/link";
import type { ReactNode } from "react";
import { AgentFlowDiagram, ArchitectureDiagram, DataFlowDiagram } from "./Diagrams";
import Reveal from "./Reveal";
import { btnAccent, btnGhost } from "./ui";

// Guided, visual-first landing page at "/" (the workspace list lives at /workspaces). Static content; the three
// main diagrams animate once with CSS. Numbers are early, single-run results on a gold set not yet human-verified.

const SECTIONS = [
  ["overview", "What it is"],
  ["model", "The mental model"],
  ["architecture", "Architecture"],
  ["linking", "How data gets linked"],
  ["agent", "The agent's flow"],
  ["guardrails", "Does and refuses"],
  ["different", "Why it stands out"],
  ["tests", "How we test it"],
  ["results", "Results so far"],
  ["next", "Status and what's next"],
  ["glossary", "Glossary"],
] as const;

type Id = (typeof SECTIONS)[number][0];
const nn = (i: number) => String(i + 1).padStart(2, "0");

function Section({ id, caption, children }: { id: Id; caption: ReactNode; children: ReactNode }) {
  const i = SECTIONS.findIndex(([s]) => s === id);
  const next = SECTIONS[i + 1];
  return (
    <section id={id} className="scroll-mt-8 border-b border-line py-12">
      <p className="font-mono text-[12px] text-accent">{nn(i)}</p>
      <h2 className="mt-1 text-[24px] font-semibold tracking-tight">{SECTIONS[i][1]}</h2>
      <p className="mt-2 max-w-[680px] text-[14.5px] leading-relaxed text-mute">{caption}</p>
      <div className="mt-6 space-y-4 text-[13.5px] leading-relaxed text-mute">{children}</div>
      {next && (
        <a href={`#${next[0]}`} className="card card-link mt-8 flex items-center justify-between px-5 py-3">
          <span className="text-[12px] text-dim">Next</span>
          <span className="text-[14px] font-medium text-fg">{nn(i + 1)} · {next[1]} {"\u2192"}</span>
        </a>
      )}
    </section>
  );
}

const B = ({ children }: { children: ReactNode }) => <b className="font-semibold text-fg">{children}</b>;
const C = ({ children }: { children: ReactNode }) => <code className="rounded bg-raised px-1 font-mono text-[12px] text-fg">{children}</code>;
const More = ({ children, label = "Details" }: { children: ReactNode; label?: string }) => (
  <details className="more card px-4 py-3"><summary>{label}</summary><div className="mt-3 space-y-2">{children}</div></details>
);
const Figure = ({ children }: { children: ReactNode }) => <Reveal className="card overflow-hidden">{children}</Reveal>;

function Tile({ icon, title, text, tone = "text-accent" }: { icon: string; title: string; text: ReactNode; tone?: string }) {
  return (
    <div className="card p-4">
      <span className={`font-mono text-[20px] leading-none ${tone}`}>{icon}</span>
      <p className="mt-3 text-[14px] font-semibold text-fg">{title}</p>
      <div className="mt-1 text-[12.5px] text-dim">{text}</div>
    </div>
  );
}

const TIERS: [string, number, string, string][] = [
  ["A", 16, "answer is in one item", "bg-accent"],
  ["B", 24, "needs several linked items", "bg-accent/70"],
  ["C", 20, "evidence removed → must abstain", "bg-warn/80"],
  ["T", 10, "close in time, not linked → must abstain", "bg-warn/50"],
  ["N", 5, "nothing in the data answers it", "bg-unk/60"],
];

export default function Landing() {
  return (
    <div className="theme-dark h-full overflow-auto bg-bg text-fg">
      <header className="sticky top-0 z-10 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between px-8">
          <span className="text-[14px] font-semibold">Engineering Memory <span className="ml-2 font-normal text-dim">prototype guide</span></span>
          <nav className="flex items-center gap-2">
            <a href="https://github.com/mdshreyas003/sdlc-agent" className={btnGhost}>GitHub</a>
            <Link href="/workspaces" className={btnGhost}>Workspaces</Link>
            <Link href="/w/kafka" className={btnAccent}>Try the demo</Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1180px] gap-12 px-8">
        <aside className="sticky top-14 h-[calc(100vh-3.5rem)] w-[210px] shrink-0 overflow-auto py-10">
          <p className="label mb-3">Guided path</p>
          <ol className="space-y-0.5">
            {SECTIONS.map(([id, t], i) => (
              <li key={id}>
                <a href={`#${id}`} className="flex gap-3 rounded-md px-2 py-1.5 text-[13px] text-mute hover:bg-hover hover:text-fg">
                  <span className="w-5 font-mono text-[11.5px] text-dim">{nn(i)}</span>{t}
                </a>
              </li>
            ))}
          </ol>
        </aside>

        <main className="min-w-0 max-w-[840px] flex-1 pb-24">
          <Section id="overview" caption="For engineers about to change or debug code they didn't write.">
            <p className="text-[26px] font-semibold leading-snug tracking-tight text-fg">
              Ask <span className="text-accent">&ldquo;why is this code like this?&rdquo;</span> Get an answer from your team&rsquo;s GitHub, Jira and chat history, with a word-for-word quote for every claim, or an honest <span className="text-accent">&ldquo;Not established.&rdquo;</span>
            </p>
            <div className="flex gap-3 pt-2">
              <Link href="/w/kafka" className={`${btnAccent} h-10 px-5 text-[13.5px]`}>Try the demo</Link>
              <a href="#model" className={`${btnGhost} h-10 px-5 text-[13.5px]`}>Start the guide {"\u2193"}</a>
            </div>
          </Section>

          <Section id="model" caption="A librarian who only answers with exact quotes from the shelves.">
            <div className="grid grid-cols-4 gap-3">
              <Tile icon="▤" title="Shelves" text="commits, PRs, tickets, chat threads" />
              <Tile icon="↔" title="Strings" text="only links a person wrote down" />
              <Tile icon="❝" title="Every answer" text="points to a real, word-for-word quote" tone="text-ok" />
              <Tile icon="∅" title="No proof?" text="“Not established”, never a guess" tone="text-warn" />
            </div>
            <p className="text-[12.5px] text-dim">The AI model may suggest an answer; plain code checks it and makes the final call.</p>
          </Section>

          <Section id="architecture" caption="Five layers, one platform: sources plug in on one side, people and services ask on the other.">
            <Figure><ArchitectureDiagram /></Figure>
            <More>
              <p><B>Sources:</B> connectors pull pull requests, commits, Jira tickets and comments, and Slack threads. <B>Evidence graph:</B> each item is one node; a link exists only where a source says so.</p>
              <p><B>Memory</B> (next): repeated evidence becomes a decision with a history; a newer version replaces an older one without deleting it. <B>Agent:</B> answers why / debug / is-it-safe-to-change questions with fixed read-only tools. <B>App / API:</B> the web workbench, or the same thing as a service.</p>
            </More>
          </Section>

          <Section id="linking" caption="Items are collected, then linked only by what is written in them: three link types, never guessed from similar words or timing.">
            <Figure><DataFlowDiagram /></Figure>
            <More label="How each link is found">
              <p><C>REPLIES_TO</C> a reply belongs to its thread (Slack <C>thread_ts</C>, GitHub <C>in_reply_to_id</C>). <C>CONTAINS</C> a PR contains a commit (GitHub&rsquo;s list of the PR&rsquo;s commits). <C>REFERENCES</C> one item mentions another: by structure (a comment belongs to its PR or ticket) or by an ID in the text (a Jira key, a PR or commit URL, <C>#123</C> inside GitHub, a Slack permalink).</p>
              <p>Matching is strict: <C>UTF-8</C>, <C>SHA-256</C> and <C>#333</C> are ignored, and each text link records the exact field and span it came from (e.g. <C>$.title#0-11</C>). The Kafka mailing list is stored in the Slack format as a stand-in for chat.</p>
            </More>
          </Section>

          <Section id="agent" caption="Seven steps. If the evidence isn't enough it plans again, at most 3 rounds; code has the last word.">
            <Figure><AgentFlowDiagram /></Figure>
            <More>
              <p><B>Seed</B> pulls exact IDs from the question (ticket keys, PR numbers, commit hashes, file paths) with no AI. <B>Plan</B> picks up to 5 tool calls per round. <B>Retrieve</B> runs read-only searches, then follows one hop of links from the best hits.</p>
              <p><B>Verify</B> checks every quote against the full source text and drops failures. The answer is established only if the evidence was judged enough <B>and</B> a claim still has a verified quote.</p>
            </More>
          </Section>

          <Section id="guardrails" caption="Read-only by construction. What it can do on the left, what code refuses on the right.">
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-4">
                <p className="label mb-3 text-ok">Does</p>
                <div className="flex flex-wrap gap-2">
                  {["find_text", "file_history", "neighbors", "evidence_chain", "get"].map((t) => <span key={t} className="rounded-md border border-line2 bg-raised px-2 py-1 font-mono text-[12px] text-fg">{t}</span>)}
                  <span className="rounded-md border border-dashed border-line2 px-2 py-1 font-mono text-[12px] text-dim">cypher_query (guarded)</span>
                </div>
                <p className="mt-3 text-[12.5px] text-dim">5 fixed read-only tools, plus one guarded escape hatch that may only find IDs.</p>
              </div>
              <ul className="card space-y-2.5 p-4">
                <p className="label mb-1 text-bad">Refuses</p>
                {[["No writes", "write words blocked; read-only route; queries time-limited"], ["No invented IDs", "only IDs already seen can be opened"], ["No paraphrased quotes", "quote must be word for word in that item"], ["No guessing", "no verified quote → “Not established”"]].map(([t, d]) => (
                  <li key={t} className="flex gap-2.5"><span className="text-bad">✕</span><span><B>{t}</B> <span className="text-dim">· {d}</span></span></li>
                ))}
              </ul>
            </div>
          </Section>

          <Section id="different" caption="Memory tools and coding agents solve other problems. Four things are different here.">
            <div className="grid grid-cols-4 gap-3">
              <Tile icon="↔" title="Trusted links" text="only explicit links, no made-up connections" />
              <Tile icon="❝" title="Code checks quotes" text="not the model" tone="text-ok" />
              <Tile icon="∅" title="“Can't prove it”" text="built in, enforced in code" tone="text-warn" />
              <Tile icon="⚑" title="Test set with traps" text="the right answer is to abstain" />
            </div>
            <More label="Comparison with Mem0, Zep/Graphiti, GraphRAG and coding agents">
              <table className="w-full text-left text-[12.5px]">
                <thead className="text-dim"><tr><th className="py-1.5" /><th>Engineering Memory</th><th>Mem0 · Zep/Graphiti · GraphRAG</th><th>Coding agents</th></tr></thead>
                <tbody>
                  {[["Links", "only links a person wrote down", "relations extracted or inferred by an LLM", "not about team history"],
                    ["Proof", "word-for-word quote, checked in code", "traceable sources or record IDs, not checked quotes", "tests and linters check code edits"],
                    ["When unsure", "“Not established”, enforced in code", "prompt-level or not measured", "not documented"],
                    ["Database access", "fixed read-only tools + ID guard", "not their focus (memory layers)", "sandbox or permission rules"]].map((r) => (
                    <tr key={r[0]} className="border-t border-line align-top">{r.map((c, j) => <td key={j} className={`py-2 pr-3 ${j === 0 ? "font-medium text-fg" : ""}`}>{c}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </More>
          </Section>

          <Section id="tests" caption="Three layers of checks: automated tests, a 7-question real-model gate, and 75 gold questions on real Kafka history.">
            <div className="card p-5">
              <div className="flex items-baseline justify-between"><p className="text-[14px] font-semibold text-fg">75 gold questions, by tier</p><p className="text-[12px] text-dim">19 for tuning · 56 held back for the final test</p></div>
              <div className="mt-3 flex h-9 overflow-hidden rounded-md">
                {TIERS.map(([t, n, , c]) => <div key={t} className={`${c} flex items-center justify-center font-mono text-[12px] font-semibold text-bg`} style={{ width: `${(n / 75) * 100}%` }}>{t} {n}</div>)}
              </div>
              <ul className="mt-3 grid grid-cols-5 gap-2 text-[11.5px] text-dim">{TIERS.map(([t, , d]) => <li key={t}><B>{t}</B> {d}</li>)}</ul>
            </div>
            <div className="card p-5">
              <p className="text-[14px] font-semibold text-fg">The 7-question gate <span className="font-normal text-dim">· real AI model, end to end, on a small made-up company</span></p>
              <div className="mt-3 flex gap-2">
                {[0, 1, 2, 3].map((k) => <span key={k} className="h-7 flex-1 rounded-md bg-ok/70" />)}
                {[0, 1].map((k) => <span key={k} className="h-7 flex-1 rounded-md bg-warn/70" />)}
                <span className="h-7 flex-1 rounded-md bg-unk/60" />
              </div>
              <p className="mt-2 text-[12px] text-dim"><span className="text-ok">■</span> 4 answerable · <span className="text-warn">■</span> 2 must say &ldquo;Not established&rdquo; · <span className="text-unk">■</span> 1 check that another workspace sees nothing</p>
            </div>
            <More label="Example tests and a gold question">
              <p><B>Links are strict:</B> a PR body with &ldquo;Fixes PAY-412 … see #190 and UTF-8, SHA-256, OTHER-9; color: #333&rdquo; must give exactly 3 links. <B>Bad IDs never reach the DB:</B> an unseen ID, or <C>x{"}"}) DETACH DELETE (n //</C>, is refused first. <B>Misquotes are dropped:</B> of three citations, only the exact quote &ldquo;Fixes PAY-412&rdquo; survives, and confidence drops to low.</p>
              <p><B>Q050 (tier B):</B> <i>&ldquo;Why does the broker retry AddPartitionsToTxn on its own when it hits CONCURRENT_TRANSACTIONS, with separate backoff settings, instead of just returning the error to the producer to retry?&rdquo;</i> The gold answer quotes Calvin Liu&rsquo;s mail, Jira KAFKA-18654 and a follow-up reply: the chain in section 04.</p>
            </More>
          </Section>

          <Section id="results" caption="Early numbers: one run each, on a question set not yet human-checked. Full 75-question benchmark is next.">
            <div className="grid grid-cols-3 gap-3">
              {[["1,191", "Kafka items", "1,786 links · 10 KIPs"], ["5 / 7", "real-model gate", "the 2 misses answered with low confidence"], ["26 / 27", "quotes kept on Q050", "Q030: 5 / 5"],
                ["Q006", "correctly “Not established”", "no answer in the data"], ["6 → 19", "of 33 gold sources reachable", "questions 1/18 → 9/18 · 0 regressions"], ["445", "automated tests passed", "7 skipped"]].map(([big, t, s]) => (
                <div key={t} className="card p-4">
                  <p className="text-[30px] font-semibold leading-none tracking-tight text-fg">{big}</p>
                  <p className="mt-2 text-[13px] text-mute">{t}</p>
                  <p className="mt-0.5 text-[12px] text-dim">{s}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section id="next" caption="The core runs end to end today; memory and the full benchmark come next.">
            <div className="grid grid-cols-2 gap-3">
              <div className="card p-4">
                <p className="label mb-3 text-ok">Running today</p>
                <ol className="space-y-1.5 text-fg">{["Sources", "Evidence graph with explicit links", "Guarded agent + quote checker", "API and web workbench", "Benchmark harness"].map((t) => <li key={t}><span className="text-ok">✓</span> {t}</li>)}</ol>
              </div>
              <div className="card p-4">
                <p className="label mb-3 text-accent">Next</p>
                <ol className="space-y-1.5 text-fg">{["Memory: versioned decisions", "decides / supersedes links", "Live sync from a saved position", "Human-check the 75 questions, then compare vs no-retrieval, BM25 and Graphiti", "Later: more sources, one identity per person, access for other agents"].map((t) => <li key={t}><span className="text-accent">→</span> {t}</li>)}</ol>
              </div>
            </div>
          </Section>

          <Section id="glossary" caption="Eight words, in plain terms.">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-2.5">
              {[["Agent", "an AI program that takes steps to answer a question"], ["Graph", "a map of items (dots) and links (lines)"], ["Link", "a connection a person actually wrote down"], ["Commit", "one saved change to the code"],
                ["Test", "an automatic check the code still works"], ["Gold question", "a question with its answer and quotes written in advance"], ["Citation", "the exact source and quote behind a sentence"], ["Abstain", "say “Not established” instead of guessing"]].map(([t, d]) => (
                <div key={t} className="flex gap-3"><dt className="w-[96px] shrink-0 font-medium text-fg">{t}</dt><dd>{d}</dd></div>
              ))}
            </dl>
            <div className="pt-4"><Link href="/w/kafka" className={`${btnAccent} h-10 px-5 text-[13.5px]`}>Try the demo {"\u2192"}</Link></div>
          </Section>
        </main>
      </div>
    </div>
  );
}
