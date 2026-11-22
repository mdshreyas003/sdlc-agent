import Link from "next/link";
import type { ReactNode } from "react";
import Reveal from "./Reveal";
import { Logo } from "./Logo";
import StageNav from "./StageNav";
import { ArchDiagram, FactoryDiagram, HeroArt, MarketDiagram, SyncDiagram, TriageDiagram } from "./StageDiagrams";
import { btnAccent } from "./ui";

// Landing page at "/": a stage deck for judges. One idea per screen, few words, and every screen ends in a "why it wins"
// line. Order: the moment -> who and money -> agent-ready (MCP) -> the software factory loop -> Karpathy's LLM wiki
// pattern, made reviewable -> triage (what is worth remembering) -> the graph -> reliability and reproducibility -> scorecard + sign in.
// Facts follow the Finale Build Plan (step 0). Claims about other tools are only the ones the plan makes.

const SLIDES = [
  ["top", "Start"],
  ["case", "The moment"],
  ["who", "Who and money"],
  ["agents", "Agent-ready"],
  ["factory", "Software factory"],
  ["wiki", "LLM wiki pattern"],
  ["triage", "Triage"],
  ["graph", "The graph"],
  ["safe", "Reliability"],
  ["start", "Scorecard"],
] as const;

function Slide({ id, kicker, title, win, children }: { id: string; kicker: string; title: ReactNode; win?: ReactNode; children?: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="relative flex min-h-[100svh] snap-start items-center overflow-hidden border-b border-line/60 px-6 pb-14 pt-24 md:px-16">
      <div aria-hidden className="px-grid pointer-events-none absolute inset-0 opacity-70 [mask-image:radial-gradient(75%_65%_at_50%_45%,#000,transparent)]" />
      <div className="relative mx-auto w-full max-w-[1080px]">
        <p className="font-mono text-[12px] uppercase tracking-[.14em] text-accent">{kicker}</p>
        <h2 id={`${id}-h`} className="mt-3 max-w-[860px] text-[32px] font-semibold leading-[1.08] tracking-tight md:text-[46px]">{title}</h2>
        {children && <div className="mt-8">{children}</div>}
        {win && (
          <p className="mt-6 flex items-start gap-3 text-[16px] leading-snug text-mute md:text-[17px]">
            <span aria-hidden className="mt-px font-mono text-accent">{"▸"}</span><span>{win}</span>
          </p>
        )}
      </div>
    </section>
  );
}

const Figure = ({ children }: { children: ReactNode }) => <Reveal className="overflow-hidden rounded-2xl border border-line">{children}</Reveal>;
const Em = ({ children }: { children: ReactNode }) => <span className="text-accent">{children}</span>;
const Fg = ({ children }: { children: ReactNode }) => <span className="text-fg">{children}</span>;
const Tag = ({ children }: { children: ReactNode }) => <span className="font-mono text-[11.5px] uppercase tracking-[.14em] text-accent">{children}</span>;
const Code = ({ children }: { children: ReactNode }) => <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-[0.9em] text-fg">{children}</code>;
const Card = ({ children, className = "" }: { children: ReactNode; className?: string }) => <div className={`rounded-2xl border border-line bg-panel p-5 md:p-6 ${className}`}>{children}</div>;
const Chip = ({ children, tone = "ok" }: { children: ReactNode; tone?: "ok" | "acc" }) => (
  <li className="flex items-center gap-2 rounded-full border border-line2 bg-raised px-3 py-1.5 text-[13px] text-mute"><span aria-hidden className={tone === "ok" ? "text-ok" : "text-accent"}>{"✓"}</span>{children}</li>
);

const USERS: [string, string, string][] = [
  ["Tech lead", "BUYER", "Approves once. The guard keeps watching."],
  ["Engineer", "NEW OR JUNIOR", "Asks why. Gets a quote and a person."],
  ["Coding agent", "MCP", "Asks why before editing."],
  ["IT services", "HANDOVERS", "The why survives the handover."],
];

const WIKI: [string, string, string][] = [
  ["Raw sources", "PRs, issues, commits", "read-only, never rewritten"],
  ["The wiki", "Decision graph", "linked, versioned, live or dead"],
  ["The schema", "Decision + quote rules", "no quote, no claim"],
  ["Ingest", "Every merge drafts", "a tech lead approves"],
  ["Query", "why · check_change", "web, PR and MCP"],
  ["Lint", "Overrides supersede", "contradictions become history"],
];

const SCORE: [string, string][] = [
  ["Scalable", "Per repo. One graph query, not a crawl."],
  ["Multi-use", "One graph, three doors: PR, web, MCP."],
  ["Market grip", "₹1,999 / repo. Agents are never seats."],
  ["Reliable", "Queues and retries. Never silent."],
  ["Reproducible", "Exact quotes. Evals you can replay."],
  ["Graph-native", "Knows which decision won."],
  ["Agentic", "Author, guard, advisor. MCP-native."],
  ["Measured", "5 real-outage tasks: alone vs guard."],
];

export default function Landing() {
  return (
    <div id="stage" className="theme-dark h-full snap-y snap-proximity overflow-auto scroll-smooth bg-bg text-fg">
      <header className="fixed inset-x-0 top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between px-6 md:px-10">
          <span className="flex items-center gap-2.5 text-[15px] font-semibold"><Logo size={20} />whycode</span>
          <Link href="/login" className={btnAccent}>Sign in</Link>
        </div>
      </header>
      <StageNav slides={SLIDES} />

      <main>
        {/* 01 · Hero */}
        <section id="top" className="relative flex min-h-[100svh] snap-start items-center overflow-hidden border-b border-line/60 px-6 pb-14 pt-24 md:px-16">
          <div aria-hidden className="px-grid px-halo pointer-events-none absolute inset-0" />
          <div className="relative mx-auto grid w-full max-w-[1180px] items-center gap-10 lg:grid-cols-[1.05fr_1fr]">
            <div>
              <p className="font-mono text-[12px] uppercase tracking-[.14em] text-accent">The PR guard that remembers why</p>
              <h1 className="mt-4 text-[40px] font-semibold leading-[1.04] tracking-tight md:text-[64px]">
                Your team forgets <Em>why.</Em><br />Your agents never knew.
              </h1>
              <p className="mt-5 max-w-[520px] text-[18px] leading-relaxed text-mute md:text-[20px]">
                We catch the pull request that undoes a decision, with the quote, the incident and who to ask.
              </p>
              <p className="mt-10 flex items-center gap-2 font-mono text-[12px] text-dim"><span className="px-caret" aria-hidden />press <kbd className="rounded border border-line2 px-1.5 py-0.5 text-fg">{"↓"}</kbd> to begin</p>
            </div>
            <Reveal className="overflow-hidden rounded-2xl border border-line"><HeroArt /></Reveal>
          </div>
        </section>

        {/* 02 · The moment (use case) */}
        <Slide id="case" kicker="02 · Use case" title={<>Agents ship faster than teams <Em>remember.</Em></>} win={<>Linters check the code. <Fg>We check the intent.</Fg></>}>
          <div className="grid items-stretch gap-4 lg:grid-cols-2">
            <Card>
              <p className="font-mono text-[11.5px] uppercase tracking-[.14em] text-dim">Pull request</p>
              <p className="mt-2 text-[20px] font-semibold tracking-tight">Simplify commit retry</p>
              <pre className="mt-4 overflow-x-auto rounded-lg border border-line bg-bg p-4 font-mono text-[13.5px] leading-7" aria-label="Code diff">
                <span className="block text-bad">- retryOnConflict(tx, 3)</span>
                <span className="block text-ok">+ return tx.Commit()</span>
              </pre>
              <p className="mt-3 text-[12px] text-dim">Illustrative example.</p>
            </Card>
            <div className="px-glow rounded-2xl bg-panel p-5 md:p-6">
              <p className="flex items-center justify-between font-mono text-[11.5px] uppercase tracking-[.14em]"><span className="text-accent">whycode · advisory</span><span className="text-dim">a human decides</span></p>
              <p className="mt-2 flex items-center gap-2 text-[20px] font-semibold tracking-tight"><span aria-hidden className="text-warn">{"▲"}</span>This undoes a live Decision</p>
              <dl className="mt-4 space-y-3 text-[15px]">
                <div className="flex gap-3"><dt className="w-20 shrink-0 font-mono text-[12px] uppercase tracking-wider text-dim">Quote</dt><dd className="border-l-2 border-accent pl-3 text-fg">{"“"}Retry on conflict. A single attempt caused the outage.{"”"}</dd></div>
                <div className="flex gap-3"><dt className="w-20 shrink-0 font-mono text-[12px] uppercase tracking-wider text-dim">Incident</dt><dd className="text-fg">The outage this rule came from</dd></div>
                <div className="flex gap-3"><dt className="w-20 shrink-0 font-mono text-[12px] uppercase tracking-wider text-dim">Ask</dt><dd className="text-fg">The person who decided it</dd></div>
              </dl>
            </div>
          </div>
        </Slide>

        {/* 03 · Who and money */}
        <Slide id="who" kicker="03 · User and business impact" title={<>Four users. <Em>One price per repo.</Em></>} win={<>Unblocked answers why ($29 / user). <Fg>We also track reversals and guard the PR.</Fg></>}>
          <div className="grid items-center gap-5 lg:grid-cols-[1fr_1.3fr]">
            <ul className="grid gap-3">
              {USERS.map(([who, tag, line]) => (
                <li key={who} className="rounded-xl border border-line bg-panel px-4 py-3.5">
                  <div className="flex items-baseline justify-between gap-3"><h3 className="text-[19px] font-semibold tracking-tight">{who}</h3><Tag>{tag}</Tag></div>
                  <p className="mt-1 text-[15px] text-mute">{line}</p>
                </li>
              ))}
            </ul>
            <div>
              <Figure><MarketDiagram /></Figure>
              <ul className="mt-3 flex flex-wrap gap-2">
                <Chip tone="acc">Free: 1 public repo</Chip>
                <Chip tone="acc">{"₹"}1,999 / repo / month</Chip>
                <Chip tone="acc">Agents are never seats</Chip>
              </ul>
            </div>
          </div>
        </Slide>

        {/* 04 · Agent-ready (MCP) */}
        <Slide id="agents" kicker="04 · Agent readiness" title={<>Make every repo <Em>agent-ready.</Em></>} win={<>AGENTS.md says how to build. <Fg>whycode says what not to undo.</Fg></>}>
          <div className="grid items-stretch gap-4 lg:grid-cols-[1.25fr_1fr]">
            <div className="overflow-hidden rounded-2xl border border-line bg-bg">
              <div className="flex items-center gap-1.5 border-b border-line px-4 py-2.5" aria-hidden>
                <span className="h-2.5 w-2.5 rounded-full bg-line2" /><span className="h-2.5 w-2.5 rounded-full bg-line2" /><span className="h-2.5 w-2.5 rounded-full bg-line2" />
                <span className="ml-3 font-mono text-[11.5px] text-dim">coding agent · MCP</span>
              </div>
              <pre className="overflow-x-auto p-5 font-mono text-[13.5px] leading-7 text-mute" aria-label="Coding agent calling why and check_change over MCP">
                <span className="block text-fg">{"> "}simplify the commit retry</span>
                <span className="block text-accent">{"→ "}why(<span className="text-fg">&quot;txn/commit.go&quot;</span>)</span>
                <span className="block pl-4">Decision <span className="text-ok">live</span></span>
                <span className="block pl-4 text-fg">{"“"}Retry on conflict.{"”"}</span>
                <span className="block text-accent">{"→ "}check_change(<span className="text-fg">diff</span>)</span>
                <span className="block pl-4"><span className="text-warn">{"▲"}</span> undoes a live Decision</span>
                <span className="block pl-4 text-dim">ask: the person who decided it</span>
              </pre>
            </div>
            <div className="grid gap-4">
              <Card>
                <Tag>Skill file</Tag>
                <p className="mt-2 text-[16px] text-mute">Hand-written. Rots.</p>
              </Card>
              <Card className="px-glow !border-transparent">
                <Tag>whycode over MCP</Tag>
                <p className="mt-2 text-[16px] text-fg">Drafted from history. Quoted. Expires when the team reverses itself.</p>
              </Card>
              <ul className="flex flex-wrap gap-2">
                <Chip>read-only</Chip><Chip>token-scoped</Chip><Chip>approved Decisions only</Chip>
              </ul>
            </div>
          </div>
        </Slide>

        {/* 05 · Software factory */}
        <Slide id="factory" kicker="05 · Software factory" title={<>The factory gets <Em>a memory.</Em></>} win={<>More agents means more speed. <Fg>Only memory keeps that speed from re-opening old outages.</Fg></>}>
          <Figure><FactoryDiagram /></Figure>
        </Slide>

        {/* 06 · Karpathy's LLM wiki */}
        <Slide id="wiki" kicker="06 · Memory design" title={<>Karpathy&rsquo;s LLM wiki, <Em>made reviewable.</Em></>} win={<>A wiki compiled once, not re-derived per question. <Fg>Plus a human gate, exact quotes and a guard.</Fg></>}>
          <div className="overflow-hidden rounded-2xl border border-line bg-panel">
            <div className="grid grid-cols-[1fr_auto_1.4fr] gap-x-4 border-b border-line px-5 py-3 font-mono text-[11.5px] uppercase tracking-[.14em] text-dim md:px-6">
              <span>LLM wiki pattern</span><span aria-hidden />
              <span className="text-accent">whycode</span>
            </div>
            <ul className="divide-y divide-line">
              {WIKI.map(([a, b, c]) => (
                <li key={a} className="grid grid-cols-[1fr_auto_1.4fr] items-baseline gap-x-4 px-5 py-3 md:px-6">
                  <span className="text-[16px] text-mute">{a}</span>
                  <span aria-hidden className="text-accent">{"→"}</span>
                  <span className="text-[16px] text-fg">{b} <span className="ml-1 text-[14px] text-dim">{c}</span></span>
                </li>
              ))}
            </ul>
          </div>
          <p className="mt-3 text-[12px] text-dim">Pattern from Andrej Karpathy&rsquo;s <a className="underline underline-offset-2 hover:text-fg" href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f">LLM Wiki</a> note (April 2026).</p>
        </Slide>

        {/* 07 · Triage */}
        <Slide id="triage" kicker="07 · Triage" title={<>Not everything is worth remembering. <Em>Triage decides.</Em></>} win={<>Anyone can make an agent write memory. <Fg>Triage drafts only what the evidence says, and you approve it.</Fg></>}>
          <Figure><TriageDiagram /></Figure>
          <p className="mt-3 text-[13px] text-dim">A PR or ticket goes in. One of three kinds comes out: a Decision, a Rule or an Episode. Or nothing, when the evidence holds none of them.</p>
        </Slide>

        {/* 08 · The graph */}
        <Slide id="graph" kicker="08 · Architecture" title={<>Simple parts. <Em>One graph.</Em></>} win={<>Vector search finds text. <Fg>Only the graph knows which decision won.</Fg></>}>
          <Figure><ArchDiagram /></Figure>
          <div className="mt-5 flex flex-wrap items-center gap-2 font-mono text-[12.5px]">
            <span className="mr-2 text-dim">The guard is one graph query</span>
            {["diff", "function", "live Decision", "incident", "person"].map((t, i) => (
              <span key={t} className="flex items-center gap-2">
                {i > 0 && <span aria-hidden className="text-accent">{"→"}</span>}
                <span className={`rounded-full border px-3 py-1 ${i === 2 ? "border-accent text-accent" : "border-line2 bg-raised text-fg"}`}>{t}</span>
              </span>
            ))}
          </div>
        </Slide>

        {/* 09 · Reliability and reproducibility */}
        <Slide id="safe" kicker="09 · Reliability and reproducibility" title={<>Built to fail safely. <Em>Built to replay.</Em></>} win={<>A silent failure is worse than a loud one. <Fg>So the PR always says something.</Fg></>}>
          <Figure><SyncDiagram /></Figure>
          <ul className="mt-4 flex flex-wrap gap-2">
            <Chip>no quote, no claim: {"“"}Not established{"”"}</Chip>
            <Chip>quotes checked in code</Chip>
            <Chip>same 5 outage tasks, replayable</Chip>
            <Chip>never clones, never stores source</Chip>
            <Chip>Sarvam, India-hosted, no training</Chip>
          </ul>
        </Slide>

        {/* 10 · Scorecard + sign in */}
        <section id="start" aria-labelledby="start-h" className="relative flex min-h-[100svh] snap-start items-center overflow-hidden px-6 pb-14 pt-24 md:px-16">
          <div aria-hidden className="px-grid px-halo pointer-events-none absolute inset-0" />
          <div className="relative mx-auto w-full max-w-[1080px]">
            <p className="font-mono text-[12px] uppercase tracking-[.14em] text-accent">10 · Scorecard</p>
            <h2 id="start-h" className="mt-3 max-w-[860px] text-[34px] font-semibold leading-[1.06] tracking-tight md:text-[52px]">Built to scale. <Em>Built to be trusted.</Em></h2>
            <ul className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {SCORE.map(([t, d]) => (
                <li key={t} className="rounded-xl border border-line bg-panel p-4">
                  <p className="flex items-center gap-2 text-[17px] font-semibold tracking-tight"><span aria-hidden className="text-ok">{"✓"}</span>{t}</p>
                  <p className="mt-1.5 text-[14.5px] leading-snug text-mute">{d}</p>
                </li>
              ))}
            </ul>
            <div className="mt-10 flex flex-wrap items-center gap-5">
              <Link href="/login" className={`${btnAccent} h-12 px-8 text-[15px]`}>Sign in</Link>
              <p className="text-[17px] text-mute">Connect a repo. <Fg>Never lose the why.</Fg></p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
