import type { CSSProperties, ReactNode } from "react";

// Landing diagrams, drawn as inline SVG on a "gridland" dot-grid. Few words per node on purpose: they are talked over on
// stage, not read. Animation is CSS only (.dg-in fades in, .dg-flow moves dashes), started once by <Reveal>.

const at = (i: number) => ({ "--i": i }) as CSSProperties;
const T = { fg: "var(--fg)", mute: "var(--mute)", dim: "var(--dim)", acc: "var(--accent)", ok: "var(--ok)", warn: "var(--warn)", panel: "var(--panel)", raised: "var(--raised)", line: "var(--line2)" };
const MONO = "var(--font-mono)";

function Frame({ id, w = 960, h = 520, label, children }: { id: string; w?: number; h?: number; label: string; children: ReactNode }) {
  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} className="block h-auto w-full" style={{ fontFamily: "var(--font-sans)" }}>
      <defs>
        <pattern id={`${id}-grid`} width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="var(--gridline)" strokeWidth="1" /></pattern>
        <filter id={`${id}-glow`} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="14" /></filter>
        <marker id={`${id}-a`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={T.dim} /></marker>
        <marker id={`${id}-b`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={T.acc} /></marker>
      </defs>
      <rect width={w} height={h} rx="16" fill="var(--bg)" />
      <rect width={w} height={h} rx="16" fill={`url(#${id}-grid)`} />
      {children}
    </svg>
  );
}

type NodeProps = { x: number; y: number; w: number; h: number; title: string; sub?: string; accent?: boolean; dashed?: boolean; dim?: boolean; tag?: string; mono?: boolean; glow?: string };

function Node({ x, y, w, h, title, sub, accent, dashed, dim, tag, mono, glow }: NodeProps) {
  return (
    <g>
      {accent && glow && <rect x={x} y={y} width={w} height={h} rx={12} fill={T.acc} opacity={0.28} filter={`url(#${glow}-glow)`} />}
      <rect x={x} y={y} width={w} height={h} rx={12} fill={accent ? T.raised : T.panel} stroke={accent ? T.acc : T.line} strokeWidth={accent ? 1.6 : 1} strokeDasharray={dashed ? "5 4" : undefined} />
      <text x={x + w / 2} y={y + (sub ? h / 2 - 2 : h / 2 + 6)} textAnchor="middle" fill={dim ? T.dim : T.fg} fontSize={mono ? 16 : 18} fontWeight={600} fontFamily={mono ? MONO : undefined}>{title}</text>
      {sub && <text x={x + w / 2} y={y + h / 2 + 19} textAnchor="middle" fill={T.dim} fontSize={13}>{sub}</text>}
      {tag && <text x={x + w - 10} y={y + 17} textAnchor="end" fill={T.acc} fontSize={10.5} fontFamily={MONO} letterSpacing=".08em">{tag}</text>}
    </g>
  );
}

const Edge = ({ d, id, accent, flow, dashed }: { d: string; id: string; accent?: boolean; flow?: boolean; dashed?: boolean }) => (
  <path d={d} fill="none" stroke={accent ? T.acc : T.dim} strokeWidth={accent ? 1.8 : 1.3} strokeDasharray={dashed ? "4 5" : undefined} className={flow ? "dg-flow" : undefined} markerEnd={`url(#${id}-${accent ? "b" : "a"})`} />
);

const Lbl = ({ x, y, children, anchor = "middle", fill = T.acc }: { x: number; y: number; children: ReactNode; anchor?: "start" | "middle" | "end"; fill?: string }) => (
  <text x={x} y={y} textAnchor={anchor} fill={fill} fontSize={11.5} fontFamily={MONO}>{children}</text>
);

/* ── Hero art: a small constellation; one live decision pulsing, one superseded ───────────────────────────────────────── */
export function HeroArt() {
  const pts: [number, number, number][] = [[90, 300, 5], [190, 210, 6], [300, 330, 5], [330, 150, 7], [450, 250, 6], [520, 90, 5], [560, 340, 5], [420, 400, 5], [610, 210, 6], [150, 110, 4]];
  const links = [[0, 1], [1, 3], [1, 4], [2, 4], [4, 6], [4, 8], [3, 5], [4, 3], [2, 7], [9, 1], [8, 5]];
  return (
    <Frame id="hero" w={680} h={470} label="A graph of linked decisions, one of them live">
      {links.map(([a, b], i) => (
        <line key={i} x1={pts[a][0]} y1={pts[a][1]} x2={pts[b][0]} y2={pts[b][1]} stroke={T.line} strokeWidth={1.3} className="dg-in" style={at(i / 2)} />
      ))}
      {pts.map(([x, y, r], i) => (
        <circle key={i} cx={x} cy={y} r={r} fill={i === 4 ? T.acc : T.panel} stroke={i === 4 ? T.acc : T.dim} strokeWidth={1.4} className="dg-in" style={at(i / 3)} />
      ))}
      <circle cx={450} cy={250} r={18} fill="none" stroke={T.acc} strokeWidth={1.4} className="pulse2" />
      <circle cx={450} cy={250} r={34} fill="none" stroke={T.acc} strokeWidth={1} opacity={0.35} />
      <circle cx={190} cy={210} r={11} fill="none" stroke={T.dim} strokeWidth={1.2} strokeDasharray="3 3" />
      <Lbl x={450} y={298} fill={T.acc}>live Decision</Lbl>
      <Lbl x={190} y={190} fill={T.dim}>superseded</Lbl>
    </Frame>
  );
}

/* ── 02 Who: four kinds of user around the product ───────────────────────────────────────────────────────────────────── */
export function WhoDiagram() {
  return (
    <Frame id="who" label="whycode at the centre, used by tech leads, coding agents, new engineers and IT services firms">
      <g className="dg-in" style={at(0)}>
        <Edge id="who" flow d="M310 100 C350 100 340 235 380 245" accent />
        <Edge id="who" flow d="M650 100 C610 100 620 235 580 245" />
        <Edge id="who" flow d="M310 428 C350 428 340 285 380 275" />
        <Edge id="who" flow d="M650 428 C610 428 620 285 580 275" />
      </g>
      <g className="dg-in" style={at(1)}><Node x={380} y={210} w={200} h={100} title="whycode" sub="the why, on record" accent glow="who" /></g>
      <g className="dg-in" style={at(2)}><Node x={60} y={56} w={250} h={90} title="Tech leads" sub="approve · own the gate" accent tag="BUYER" /></g>
      <g className="dg-in" style={at(3)}><Node x={650} y={56} w={250} h={90} title="Coding agents" sub="Claude Code · Cursor · Copilot" tag="MCP" /></g>
      <g className="dg-in" style={at(4)}><Node x={60} y={384} w={250} h={90} title="New engineers" sub="ask why, get a quote" /></g>
      <g className="dg-in" style={at(5)}><Node x={650} y={384} w={250} h={90} title="IT services firms" sub="handovers keep the why" /></g>
    </Frame>
  );
}

/* ── 03 Market: where we sit ─────────────────────────────────────────────────────────────────────────────────────────── */
export function MarketDiagram() {
  return (
    <Frame id="mk" label="Positioning map: others answer why; whycode also tracks reversed decisions and guards pull requests">
      <rect x={500} y={30} width={390} height={200} rx={14} fill={T.acc} opacity={0.07} />
      <path d="M110 450 H900" stroke={T.dim} strokeWidth={1.4} markerEnd="url(#mk-a)" />
      <path d="M110 450 V24" stroke={T.dim} strokeWidth={1.4} markerEnd="url(#mk-a)" />
      <text x={505} y={490} textAnchor="middle" fill={T.mute} fontSize={15}>Knows which decision still stands</text>
      <text transform="translate(52 240) rotate(-90)" textAnchor="middle" fill={T.mute} fontSize={15}>Acts at the pull request</text>

      <g className="dg-in" style={at(0)}>
        <circle cx={270} cy={385} r={9} fill={T.panel} stroke={T.dim} strokeWidth={1.5} />
        <text x={290} y={382} fill={T.fg} fontSize={17} fontWeight={600}>Skill file</text>
        <text x={290} y={402} fill={T.dim} fontSize={13}>hand-written, rots</text>
      </g>
      <g className="dg-in" style={at(1)}>
        <circle cx={420} cy={300} r={9} fill={T.panel} stroke={T.dim} strokeWidth={1.5} />
        <text x={440} y={297} fill={T.fg} fontSize={17} fontWeight={600}>Unblocked</text>
        <text x={440} y={317} fill={T.dim} fontSize={13}>answers why · $29 / user</text>
      </g>
      <g className="dg-in" style={at(3)}>
        <Edge id="mk" dashed d="M470 288 C560 240 640 190 705 150" accent />
        <circle cx={740} cy={120} r={30} fill={T.acc} opacity={0.3} filter="url(#mk-glow)" />
        <circle cx={740} cy={120} r={14} fill={T.acc} />
        <circle cx={740} cy={120} r={24} fill="none" stroke={T.acc} strokeWidth={1.2} className="pulse2" />
        <text x={740} y={176} textAnchor="middle" fill={T.fg} fontSize={22} fontWeight={700}>whycode</text>
        <text x={740} y={198} textAnchor="middle" fill={T.mute} fontSize={13.5}>drafted · quoted · expires when reversed</text>
      </g>
    </Frame>
  );
}

/* ── 05 Flow: connect → draft → approve → guard → resolve, and the loop back ─────────────────────────────────────────── */
export function FlowDiagram() {
  const S: [string, string, string][] = [["Connect", "read-only GitHub app", "01"], ["Draft", "PRs → Decisions", "02"], ["Approve", "tech lead: yes / no", "03"], ["Guard", "warning on the PR", "04"], ["Resolve", "keep or override", "05"]];
  const w = 150, h = 96, y = 70, step = 186, x0 = 30;
  return (
    <Frame id="fl" h={310} label="Flow: connect a repo, draft Decisions, approve them, guard new pull requests, resolve; an override becomes the new Decision">
      {S.map(([t, s, n], i) => {
        const x = x0 + i * step;
        return (
          <g key={t} className="dg-in" style={at(i)}>
            {i > 0 && <Edge id="fl" accent={i === 3} d={`M${x - step + w + 4} ${y + h / 2} H${x - 4}`} />}
            <Node x={x} y={y} w={w} h={h} title={t} sub={s} accent={i === 3} />
            <text x={x + 14} y={y + 20} fill={T.acc} fontSize={11.5} fontFamily={MONO}>{n}</text>
          </g>
        );
      })}
      <g className="dg-in" style={at(6)}>
        <Edge id="fl" accent flow d={`M${x0 + 4 * step + w / 2} ${y + h + 4} V${y + h + 52} H${x0 + step + w / 2} V${y + h + 6}`} />
        <Lbl x={x0 + 2.5 * step + w / 2} y={y + h + 76}>the override becomes the new Decision</Lbl>
      </g>
    </Frame>
  );
}

/* ── 07 Architecture: sources → memory → answers → three doors ───────────────────────────────────────────────────────── */
/* ── Triage: one anchor in, one kind of memory out, or nothing ───────────────────────────────────────────────────────── */
export function TriageDiagram() {
  const K: [string, string, number][] = [["Decision", "decided · instead of · trade-off", 36], ["Rule", "always · never · must", 130], ["Episode", "regression · revert · root cause", 224]];
  return (
    <Frame id="tr" h={372} label="Triage: a PR, ticket or file is turned into evidence, scored as a decision, rule or episode, drafted with verbatim quotes, and approved by a person; no signal means nothing is drafted">
      <g className="dg-in" style={at(0)}><Node x={20} y={128} w={130} h={64} title="Anchor" sub="PR · ticket · file" /></g>
      <g className="dg-in" style={at(1)}><Edge id="tr" d="M154 160 H186" /><Node x={190} y={128} w={140} h={64} title="Gather" sub="cited evidence" /></g>
      {K.map(([t, sub, y], i) => (
        <g key={t} className="dg-in" style={at(2 + i)}>
          <Edge id="tr" d={`M334 160 C360 160 354 ${y + 31} 376 ${y + 31}`} />
          <Node x={380} y={y} w={210} h={62} title={t} sub={sub} accent={i === 0} glow={i === 0 ? "tr" : undefined} />
          <Edge id="tr" d={`M594 ${y + 31} C614 ${y + 31} 612 160 634 160`} />
        </g>
      ))}
      <g className="dg-in" style={at(5)}><Node x={638} y={128} w={150} h={64} title="Draft" sub="verbatim + TODO" /></g>
      <g className="dg-in" style={at(6)}><Edge id="tr" accent flow d="M792 160 H822" /><Node x={826} y={128} w={120} h={64} title="You" sub="approve or reject" accent glow="tr" /><Lbl x={886} y={116}>HUMAN GATE</Lbl></g>
      <g className="dg-in" style={at(7)}>
        <Edge id="tr" dashed d="M262 196 V326 H376" />
        <Node x={380} y={304} w={210} h={44} title="No signal: no draft" dashed dim />
        <Lbl x={20} y={236} anchor="start" fill={T.dim}>keywords, no model</Lbl>
        <Lbl x={638} y={230} anchor="start" fill={T.dim}>nothing goes live</Lbl>
        <Lbl x={638} y={248} anchor="start" fill={T.dim}>until you approve</Lbl>
      </g>
    </Frame>
  );
}

export function ArchDiagram() {
  const doors = ["PR guard", "Web page", "MCP"];
  const dy = [88, 164, 240];
  return (
    <Frame id="ar" h={400} label="Architecture: GitHub, drafting model, Decision graph in Neo4j, guard and agent, then PR comment, web page and MCP">
      {[["INGEST", 24], ["DRAFT", 196], ["REMEMBER", 392], ["CHECK", 618], ["DELIVER", 790]].map(([t, x]) => (
        <text key={t as string} x={x as number} y={44} fill={T.dim} fontSize={11} letterSpacing=".12em" fontFamily={MONO}>{t}</text>
      ))}
      <g className="dg-in" style={at(0)}><Node x={24} y={156} w={130} h={72} title="GitHub" sub="read-only" /></g>
      <g className="dg-in" style={at(1)}><Edge id="ar" flow d="M158 192 H192" /><Node x={196} y={156} w={160} h={72} title="Drafter" sub="Sarvam · India-hosted" /></g>
      <g className="dg-in" style={at(2)}><Edge id="ar" flow d="M360 192 H388" /><Node x={392} y={132} w={190} h={120} title="Decision graph" sub="Neo4j · live / dead" accent glow="ar" tag="MEMORY" /></g>
      <g className="dg-in" style={at(3)}><Edge id="ar" flow accent d="M586 192 H614" /><Node x={618} y={156} w={140} h={72} title="Guard + agent" sub="quote or refuse" accent /></g>
      {doors.map((t, i) => (
        <g key={t} className="dg-in" style={at(4 + i * 0.5)}>
          <Edge id="ar" d={`M762 192 C776 192 774 ${dy[i] + 26} 788 ${dy[i] + 26}`} />
          <Node x={790} y={dy[i]} w={150} h={52} title={t} />
        </g>
      ))}
      <g className="dg-in" style={at(6)}>
        <rect x={24} y={310} width={912} height={56} rx={12} fill="none" stroke={T.line} strokeDasharray="5 4" />
        <text x={480} y={344} textAnchor="middle" fill={T.mute} fontSize={15}>One graph. The same Decision guards the PR, answers the engineer and briefs the agent.</text>
      </g>
    </Frame>
  );
}

/* ── 08 Graph: why a graph; the guard is one path ────────────────────────────────────────────────────────────────────── */
export function GraphDiagram() {
  const cy = 250, w = 140, h = 64;
  const X = { v1: 100, v2: 340, fn: 580, pr: 820 };
  const box = (cx: number, y: number) => ({ x: cx - w / 2, y: y - h / 2, w, h });
  return (
    <Frame id="gr" h={470} label="Graph: an old Decision superseded by a live one, which governs a function; the live Decision links to an incident and a person; a PR diff touches the function">
      <g className="dg-in" style={at(0)}>
        <Edge id="gr" d={`M${X.v1 + w / 2 + 4} ${cy} H${X.v2 - w / 2 - 4}`} dashed />
        <Lbl x={(X.v1 + X.v2) / 2} y={cy - 12} fill={T.dim}>superseded-by</Lbl>
        <Node {...box(X.v1, cy)} title="Decision v1" sub="reversed" dashed dim />
      </g>
      <g className="dg-in" style={at(1)}>
        <Edge id="gr" accent d={`M${X.pr - w / 2 - 4} ${cy} H${X.fn + w / 2 + 4}`} />
        <Lbl x={(X.pr + X.fn) / 2} y={cy - 12}>touches</Lbl>
        <Node {...box(X.pr, cy)} title="PR diff" sub="the new change" />
      </g>
      <g className="dg-in" style={at(2)}>
        <Edge id="gr" accent d={`M${X.fn - w / 2 - 4} ${cy} H${X.v2 + w / 2 + 4}`} />
        <Lbl x={(X.fn + X.v2) / 2} y={cy - 12}>governed-by</Lbl>
        <Node {...box(X.fn, cy)} title="commitTxn()" mono sub="function" />
      </g>
      <g className="dg-in" style={at(3)}>
        <Edge id="gr" accent d={`M${X.v2} ${cy - h / 2 - 4} V${cy - 136 + h / 2 + 4}`} />
        <Lbl x={X.v2 + 12} y={cy - 70} anchor="start">because of</Lbl>
        <Edge id="gr" accent d={`M${X.v2} ${cy + h / 2 + 4} V${cy + 136 - h / 2 - 4}`} />
        <Lbl x={X.v2 + 12} y={cy + 76} anchor="start">decided by</Lbl>
        <Node {...box(X.v2, cy)} title="Decision v2" sub="live" accent glow="gr" tag="LIVE" />
        <Node {...box(X.v2, cy - 136)} title="Incident" sub="the outage" />
        <Node {...box(X.v2, cy + 136)} title="Person" sub="who to ask" />
      </g>
      <Lbl x={X.pr} y={cy + 66} fill={T.dim}>the guard path</Lbl>
    </Frame>
  );
}
