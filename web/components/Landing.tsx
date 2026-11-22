import Image from "next/image";
import type { ReactNode } from "react";
import Reveal from "./Reveal";
import { Logo } from "./Logo";
import StageNav from "./StageNav";
import { ArchDiagram, FlowDiagram, GraphDiagram, HeroArt, MarketDiagram, TriageDiagram, WhoDiagram } from "./StageDiagrams";
import LandingCta from "./LandingCta";
import { btnAccent } from "./ui";

// Landing page at "/": a stage deck, one idea per screen, few words. Order is the pitch order: business impact (who,
// market) -> what makes it different -> the flow and one concrete moment -> internals (architecture, graph) -> sign in.
// Content follows the Finale Build Plan (step 0): product "whycode", PR guard, Decisions with quotes, Neo4j graph.

const SLIDES = [
  ["top", "Start"],
  ["who", "Who it is for"],
  ["market", "Where we sit"],
  ["edge", "What is different"],
  ["flow", "The flow"],
  ["triage", "Triage"],
  ["moment", "The moment"],
  ["real", "Real data"],
  ["inside", "Architecture"],
  ["graph", "The graph"],
  ["start", "Sign in"],
] as const;

function Slide({ id, kicker, title, note, children }: { id: string; kicker: string; title: ReactNode; note?: ReactNode; children?: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="relative flex min-h-[100svh] snap-start items-center overflow-hidden border-b border-line/60 px-6 pb-14 pt-24 md:px-16">
      <div className="relative mx-auto w-full max-w-[1080px]">
        <p className="font-mono text-[12px] uppercase tracking-[.14em] text-accent">{kicker}</p>
        <h2 id={`${id}-h`} className="mt-3 max-w-[820px] text-[32px] font-semibold leading-[1.08] tracking-tight md:text-[46px]">{title}</h2>
        {note && <p className="mt-3 max-w-[640px] text-[16px] leading-relaxed text-mute md:text-[18px]">{note}</p>}
        {children && <div className="mt-8">{children}</div>}
      </div>
    </section>
  );
}

const Figure = ({ children }: { children: ReactNode }) => <Reveal className="overflow-hidden rounded-2xl border border-line">{children}</Reveal>;
function Shot({ src, w, h, alt, tag, cap }: { src: string; w: number; h: number; alt: string; tag: string; cap: string }) {
  return (
    <Reveal className="overflow-hidden rounded-2xl border border-line bg-panel">
      <figure>
        <Image src={src} width={w} height={h} alt={alt} sizes="(min-width: 768px) 520px, 100vw" className="h-auto w-full" />
        <figcaption className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-[14px] text-mute">
          <span className="font-mono text-[11.5px] uppercase tracking-[.14em] text-accent">{tag}</span>
          <span>{cap} <span className="text-dim">· simulated data</span></span>
        </figcaption>
      </figure>
    </Reveal>
  );
}

const Em = ({ children }: { children: ReactNode }) => <span className="text-accent">{children}</span>;

function Glyph({ kind }: { kind: "quote" | "live" | "guard" }) {
  const c = "var(--accent)", d = "var(--dim)";
  return (
    <svg width="44" height="44" viewBox="0 0 44 44" fill="none" aria-hidden>
      {kind === "quote" && <><path d="M8 13h28M8 22h28M8 31h16" stroke={d} strokeWidth="2" strokeLinecap="round" /><rect x="5" y="19" width="34" height="6" rx="3" stroke={c} strokeWidth="1.6" /></>}
      {kind === "live" && <><circle cx="11" cy="22" r="6" stroke={d} strokeWidth="1.8" strokeDasharray="3 3" /><path d="M19 22h7" stroke={c} strokeWidth="1.8" strokeLinecap="round" /><circle cx="33" cy="22" r="6" fill={c} /></>}
      {kind === "guard" && <><path d="M22 6 36 11v10c0 9-6 15-14 18C14 36 8 30 8 21V11z" stroke={c} strokeWidth="1.8" strokeLinejoin="round" /><path d="m16 22 4 4 8-9" stroke={c} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></>}
    </svg>
  );
}

const EDGE: ["quote" | "live" | "guard", string, string][] = [
  ["quote", "Quoted", "Every claim has a quote. No quote, no answer."],
  ["live", "Live or dead", "Knows which decision still stands."],
  ["guard", "Guards the PR", "A warning before the merge. Never a block."],
];

export default function Landing() {
  return (
    <div id="stage" className="theme-dark h-full snap-y snap-proximity overflow-auto scroll-smooth bg-bg text-fg">
      <header className="fixed inset-x-0 top-0 z-20 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1180px] items-center justify-between px-6 md:px-10">
          <span className="flex items-center gap-2.5 text-[15px] font-semibold"><Logo size={20} />whycode</span>
          <LandingCta className={btnAccent} />
        </div>
      </header>
      <StageNav slides={SLIDES} />

      <main>
        {/* 01 · Hero */}
        <section id="top" className="relative flex min-h-[100svh] snap-start items-center overflow-hidden border-b border-line/60 px-6 pb-14 pt-24 md:px-16">
          <div aria-hidden className="px-halo pointer-events-none absolute inset-0" />
          <div className="relative mx-auto grid w-full max-w-[1180px] items-center gap-10 lg:grid-cols-[1.05fr_1fr]">
            <div>
              <p className="font-mono text-[12px] uppercase tracking-[.14em] text-accent">The PR guard that remembers why</p>
              <h1 className="mt-4 text-[40px] font-semibold leading-[1.04] tracking-tight md:text-[64px]">
                Your team forgets <Em>why.</Em><br />Your agents never knew.
              </h1>
              <p className="mt-5 max-w-[520px] text-[18px] leading-relaxed text-mute md:text-[20px]">
                We catch the pull request that undoes a decision, with the quote, the incident and who to ask.
              </p>
              <p className="mt-10 flex items-center gap-2 font-mono text-[12px] text-dim"><span className="px-caret" aria-hidden />press <kbd className="rounded border border-line2 px-1.5 py-0.5 text-fg">↓</kbd> to begin</p>
            </div>
            <Reveal className="overflow-hidden rounded-2xl border border-line"><HeroArt /></Reveal>
          </div>
        </section>

        {/* 02 · Who: business impact starts with the people */}
        <Slide id="who" kicker="02 · Who it is for" title={<>Built for teams that ship <Em>with agents.</Em></>}>
          <Figure><WhoDiagram /></Figure>
        </Slide>

        {/* 03 · Market */}
        <Slide id="market" kicker="03 · Where we sit" title={<>Others answer why. <Em>We guard it.</Em></>}>
          <div className="grid items-center gap-6 lg:grid-cols-[1.5fr_1fr]">
            <Figure><MarketDiagram /></Figure>
            <dl className="grid gap-3">
              {[["Pain", "An agent “simplifies” code and re-opens a past outage."], ["Value", "One prevented repeat incident pays for years."], ["Price", "₹1,999 / repo / month. Agents are never seats."]].map(([t, d]) => (
                <div key={t} className="rounded-xl border border-line bg-panel p-4">
                  <dt className="font-mono text-[11.5px] uppercase tracking-[.14em] text-accent">{t}</dt>
                  <dd className="mt-1 text-[16px] leading-snug text-fg">{d}</dd>
                </div>
              ))}
            </dl>
          </div>
        </Slide>

        {/* 04 · Difference */}
        <Slide id="edge" kicker="04 · What is different" title={<>Three things that <Em>set us apart.</Em></>}>
          <div className="grid gap-4 md:grid-cols-3">
            {EDGE.map(([g, t, d]) => (
              <div key={t} className="rounded-2xl border border-line bg-panel p-6">
                <Glyph kind={g} />
                <h3 className="mt-5 text-[24px] font-semibold tracking-tight">{t}</h3>
                <p className="mt-2 text-[16px] leading-snug text-mute">{d}</p>
              </div>
            ))}
          </div>
          <p className="mt-8 text-[18px] text-mute">Vector search finds text. <span className="text-fg">Only the graph knows which decision won.</span></p>
        </Slide>

        {/* 05 · Flow */}
        <Slide id="flow" kicker="05 · The flow" title={<>One loop. <Em>Memory stays fresh.</Em></>} note="Updating is a side effect of reviewing, not a chore.">
          <Figure><FlowDiagram /></Figure>
        </Slide>

        {/* 06 · Triage */}
        <Slide id="triage" kicker="06 · Triage" title={<>Not everything is worth remembering. <Em>Triage decides.</Em></>} note="Triage drafts only what the evidence says. You approve it.">
          <Figure><TriageDiagram /></Figure>
        </Slide>

        {/* 07 · The moment: what the judges will see */}
        <Slide id="moment" kicker="07 · The moment" title={<>A PR undoes a decision. <Em>We say so.</Em></>}>
          <div className="grid items-stretch gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-line bg-panel p-5">
              <p className="font-mono text-[11.5px] uppercase tracking-[.14em] text-dim">Pull request</p>
              <p className="mt-2 text-[20px] font-semibold tracking-tight">Simplify commit retry</p>
              <pre className="mt-4 overflow-x-auto rounded-lg border border-line bg-bg p-4 font-mono text-[13.5px] leading-7" aria-label="Code diff">
                <span className="block text-bad">- retryOnConflict(tx, 3)</span>
                <span className="block text-ok">+ return tx.Commit()</span>
              </pre>
            </div>
            <div className="px-glow rounded-2xl bg-panel p-5">
              <p className="flex items-center justify-between font-mono text-[11.5px] uppercase tracking-[.14em]"><span className="text-accent">whycode · advisory</span><span className="text-dim">a human decides</span></p>
              <p className="mt-2 flex items-center gap-2 text-[20px] font-semibold tracking-tight"><span aria-hidden className="text-warn">▲</span>This undoes a live Decision</p>
              <dl className="mt-4 space-y-3 text-[15px]">
                <div className="flex gap-3"><dt className="w-20 shrink-0 font-mono text-[12px] uppercase tracking-wider text-dim">Quote</dt><dd className="border-l-2 border-accent pl-3 text-fg">“Retry on conflict. A single attempt caused the outage.”</dd></div>
                <div className="flex gap-3"><dt className="w-20 shrink-0 font-mono text-[12px] uppercase tracking-wider text-dim">Incident</dt><dd className="text-fg">The outage this rule came from</dd></div>
                <div className="flex gap-3"><dt className="w-20 shrink-0 font-mono text-[12px] uppercase tracking-wider text-dim">Ask</dt><dd className="text-fg">The person who decided it</dd></div>
              </dl>
            </div>
          </div>
          <p className="mt-3 text-[12px] text-dim">Illustrative example.</p>
        </Slide>

        {/* 08 · Real data: live screens of the product, run on the simulated Brightcart story (docs/story.md) */}
        <Slide id="real" kicker="08 · Real data" title={<>This is a real run, <Em>on simulated data.</Em></>} note="Brightcart is a made-up store. The screens below are live output of the real product.">
          <div className="grid gap-4 md:grid-cols-2">
            <Shot src="/story/03-incident-cluster-before.jpg" w={800} h={537} tag="Before" alt="Neo4j graph of the Brightcart incident ticket with its threads, pull requests and commits: 36 records, 63 links." cap="36 records, 63 links" />
            <Shot src="/story/04-incident-cluster-after-stage1.jpg" w={800} h={537} tag="After a new ticket and Slack thread" alt="The same graph after a new ticket and Slack thread joined the incident: 40 records, 69 links." cap="40 records, 69 links" />
            <Shot src="/story/05-staged-update-and-source-changed.jpg" w={800} h={450} tag="Decision note" alt="A decision note in the review screen, with a staged update and a source changed banner showing old text struck through next to new text." cap="A ticket was edited. The note says “source changed”." />
            <Shot src="/story/07-who-decided-what.jpg" w={800} h={450} tag="Who decided what" alt="Graph of people and decisions: Daniel approved three decisions, Mei approved two, and one decision replaces another." cap="Daniel approved three. Mei approved two." />
          </div>
          <ul className="mt-5 grid gap-3 text-[15px] md:grid-cols-3">
            {["The Brightcart store, people and numbers are simulated.", "The graph, triage, notes and checks are the real code.", "The graph grew. Nothing was imported again."].map((t) => (
              <li key={t} className="rounded-xl border border-line bg-panel p-4 leading-snug text-fg">{t}</li>
            ))}
          </ul>
        </Slide>

        {/* 09 · Architecture */}
        <Slide id="inside" kicker="09 · Under the hood" title={<>Simple parts. <Em>One graph.</Em></>}>
          <Figure><ArchDiagram /></Figure>
          <ul className="mt-5 flex flex-wrap gap-2 text-[13px]">
            {["GitHub: read-only", "Never stores source files", "No endpoint returns code", "Models never trained on your data"].map((t) => (
              <li key={t} className="flex items-center gap-2 rounded-full border border-line2 bg-raised px-3 py-1.5 text-mute"><span aria-hidden className="text-ok">✓</span>{t}</li>
            ))}
          </ul>
        </Slide>

        {/* 10 · Graph */}
        <Slide id="graph" kicker="10 · Why a graph" title={<>“Is this still live?” is a <Em>path.</Em></>} note="The guard is one query: diff, function, live Decision, incident, person.">
          <Figure><GraphDiagram /></Figure>
          <p className="mt-4 font-mono text-[12px] text-dim">Graph database: Neo4j</p>
        </Slide>

        {/* 11 · Close */}
        <section id="start" aria-labelledby="start-h" className="relative flex min-h-[100svh] snap-start items-center overflow-hidden px-6 pb-14 pt-24 md:px-16">
          <div aria-hidden className="px-halo pointer-events-none absolute inset-0" />
          <div className="relative mx-auto w-full max-w-[1080px] text-center">
            <h2 id="start-h" className="text-[38px] font-semibold leading-[1.06] tracking-tight md:text-[60px]">Connect a repo.<br /><Em>Never lose the why.</Em></h2>
            <div className="mt-10"><LandingCta className={`${btnAccent} h-12 px-8 text-[15px]`} /></div>
          </div>
        </section>
      </main>
    </div>
  );
}
