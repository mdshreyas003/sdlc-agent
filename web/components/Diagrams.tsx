import type { CSSProperties, ReactNode } from "react";

// The three main landing diagrams as inline SVG (960x540, 16:9). Animation is CSS only: .dg-in fades in, .dg-lit
// lights up, ordered by --i. Facts follow /workspace/simple/story.md.

const at = (i: number) => ({ "--i": i }) as CSSProperties;
const T = { fg: "var(--fg)", mute: "var(--mute)", dim: "var(--dim)", acc: "var(--accent)", ok: "var(--ok)", warn: "var(--warn)", panel: "var(--panel)", raised: "var(--raised)", line: "var(--line2)" };

function Defs({ id }: { id: string }) {
  return (
    <defs>
      <marker id={`${id}-a`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0L10 5L0 10z" fill={T.dim} />
      </marker>
      <marker id={`${id}-b`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0L10 5L0 10z" fill={T.acc} />
      </marker>
    </defs>
  );
}

function Box({ x, y, w, h, title, sub, accent, dashed, tag }: { x: number; y: number; w: number; h: number; title: string; sub?: string; accent?: boolean; dashed?: boolean; tag?: string }) {
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={10} fill={accent ? T.raised : T.panel} stroke={accent ? T.acc : T.line} strokeWidth={accent ? 1.5 : 1} strokeDasharray={dashed ? "5 4" : undefined} />
      <text x={x + w / 2} y={y + (sub ? h / 2 - 3 : h / 2 + 5)} textAnchor="middle" fill={T.fg} fontSize={15} fontWeight={600}>{title}</text>
      {sub && <text x={x + w / 2} y={y + h / 2 + 17} textAnchor="middle" fill={T.dim} fontSize={12.5}>{sub}</text>}
      {tag && <text x={x + w - 10} y={y + 16} textAnchor="end" fill={T.acc} fontSize={10.5} fontFamily="var(--font-mono)">{tag}</text>}
    </g>
  );
}

const Line = ({ d, id, accent, label, lx, ly }: { d: string; id: string; accent?: boolean; label?: string; lx?: number; ly?: number }) => (
  <g>
    <path d={d} fill="none" stroke={accent ? T.acc : T.dim} strokeWidth={accent ? 1.6 : 1.2} markerEnd={`url(#${id}-${accent ? "b" : "a"})`} />
    {label && <text x={lx} y={ly} textAnchor="middle" fill={T.acc} fontSize={10.5} fontFamily="var(--font-mono)">{label}</text>}
  </g>
);

function Frame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <svg viewBox="0 0 960 540" role="img" aria-label={label} className="block h-auto w-full" style={{ fontFamily: "var(--font-sans)" }}>
      <rect width="960" height="540" rx="14" fill="var(--bg)" />
      {children}
    </svg>
  );
}

export function ArchitectureDiagram() {
  const L = [
    ["1 · Sources", "connectors pull PRs, commits, tickets, threads"],
    ["2 · Evidence graph", "one node per item · explicit links only (Neo4j)"],
    ["3 · Memory", "versioned decisions with history · next"],
    ["4 · Agent + quote checker", "fixed read-only tools · code checks every quote"],
    ["5 · App / API", "web workbench · HTTP API"],
  ];
  const x = 300, w = 360, h = 70, y0 = 40, gap = 23;
  return (
    <Frame label="Architecture: five layers">
      <Defs id="ar" />
      {L.map(([t, s], i) => {
        const y = y0 + i * (h + gap);
        return (
          <g key={t} className="dg-in" style={at(i)}>
            <Box x={x} y={y} w={w} h={h} title={t} sub={s} accent={i === 1 || i === 3} dashed={i === 2} />
            {i < 4 && <Line id="ar" d={`M${x + w / 2} ${y + h + 2} V${y + h + gap - 2}`} />}
          </g>
        );
      })}
      <g className="dg-in" style={at(0)}>
        <text x={40} y={60} fill={T.dim} fontSize={11.5} letterSpacing=".06em">DATA SOURCES</text>
        {["GitHub", "Jira", "Slack / mailing list"].map((s, i) => (
          <g key={s}>
            <Box x={40} y={74 + i * 52} w={180} h={40} title={s} />
            <Line id="ar" d={`M222 ${94 + i * 52} C260 ${94 + i * 52} 262 75 ${x - 3} 75`} />
          </g>
        ))}
      </g>
      <g className="dg-in" style={at(5)}>
        <text x={740} y={386} fill={T.dim} fontSize={11.5} letterSpacing=".06em">WHO ASKS</text>
        {[["Engineers", "in the web workbench"], ["Other services", "through the HTTP API"]].map(([t, s], i) => (
          <g key={t}>
            <Box x={740} y={400 + i * 64} w={180} h={52} title={t} sub={s} />
            <Line id="ar" d={`M738 ${426 + i * 64} C700 ${426 + i * 64} 700 447 ${x + w + 3} 447`} />
          </g>
        ))}
      </g>
      <text x={480} y={528} textAnchor="middle" fill={T.dim} fontSize={12}>Memory only points the agent to evidence; it is never quoted itself.</text>
    </Frame>
  );
}

export function DataFlowDiagram() {
  const top = 60;
  const srcs = ["GitHub", "Jira", "Slack", "Mailing list"];
  return (
    <Frame label="Data flow and a real linked chain from Kafka">
      <Defs id="df" />
      <g className="dg-in" style={at(0)}>
        {srcs.map((s, i) => (
          <g key={s}>
            <Box x={30} y={top + i * 44} w={140} h={34} title={s} />
            <Line id="df" d={`M172 ${top + 17 + i * 44} C205 ${top + 17 + i * 44} 205 126 232 126`} />
          </g>
        ))}
      </g>
      <g className="dg-in" style={at(1)}><Box x={235} y={91} w={160} h={70} title="Collect" sub="one node per item" /><Line id="df" d="M397 126 H448" /></g>
      <g className="dg-in" style={at(2)}>
        <Box x={450} y={66} w={250} h={120} title="" accent />
        <text x={575} y={90} textAnchor="middle" fill={T.fg} fontSize={15} fontWeight={600}>Link (only what is written)</text>
        {["REPLIES_TO", "REFERENCES", "CONTAINS"].map((k, i) => (
          <g key={k}>
            <rect x={490} y={102 + i * 26} width={170} height={20} rx={5} fill={T.panel} stroke={T.line} />
            <text x={575} y={116 + i * 26} textAnchor="middle" fill={T.acc} fontSize={11.5} fontFamily="var(--font-mono)">{k}</text>
          </g>
        ))}
        <Line id="df" d="M702 126 H753" />
      </g>
      <g className="dg-in" style={at(3)}><Box x={755} y={91} w={175} h={70} title="Evidence graph" sub="Neo4j" /></g>

      <line x1={30} x2={930} y1={244} y2={244} stroke={T.line} strokeDasharray="3 5" />
      <text x={30} y={272} fill={T.dim} fontSize={11.5} letterSpacing=".06em">A REAL CHAIN FROM THE KAFKA DATA (KIP-890)</text>

      <g className="dg-in" style={at(4)}><Box x={30} y={410} w={200} h={78} title="Calvin Liu's mail" sub="Feb 2025" /></g>
      <g className="dg-in" style={at(5)}>
        <Box x={30} y={292} w={290} h={64} title="Mail thread" sub="[DISCUSS] KIP-890 Server Side Defense" />
        <Line id="df" accent d="M130 408 V360" label="REPLIES_TO" lx={178} ly={388} />
      </g>
      <g className="dg-in" style={at(6)}>
        <Line id="df" accent d="M232 449 H297" label="REFERENCES" lx={265} ly={438} />
        <Box x={300} y={410} w={170} h={78} title="Jira KAFKA-18654" sub="the ticket" accent />
      </g>
      <g className="dg-in" style={at(7)}>
        <Line id="df" accent d="M538 449 H473" label="REFERENCES" lx={505} ly={438} />
        <Box x={540} y={410} w={170} h={78} title="PR #18720" sub="“KAFKA-18654 [1/2]: …”" />
      </g>
      <g className="dg-in" style={at(8)}>
        <Line id="df" accent d="M712 449 H767" label="CONTAINS" lx={740} ly={438} />
        <Box x={770} y={410} w={170} h={78} title="Commit ab8ef87" sub="“KAFKA-18654 … (#18720)”" />
      </g>
      <text x={480} y={520} textAnchor="middle" fill={T.dim} fontSize={12}>Mail discussion → ticket → code change: each step a link someone wrote down.</text>
    </Frame>
  );
}

export function AgentFlowDiagram() {
  const S: [string, string, boolean][] = [
    ["Understand", "AI restates", false], ["Seed", "code: exact IDs", true], ["Plan", "AI picks tools", false],
    ["Retrieve", "read-only tools", true], ["Evaluate", "AI: enough?", false], ["Synthesize", "AI writes claims", false],
    ["Verify", "code decides", true],
  ];
  const w = 116, gap = 15, x0 = 22, y = 200, h = 76;
  const cx = (i: number) => x0 + i * (w + gap);
  return (
    <Frame label="Agent flow: seven steps">
      <Defs id="ag" />
      <g className="dg-in" style={at(0)}>
        <rect x={30} y={30} width={14} height={14} rx={3} fill={T.panel} stroke={T.line} /><text x={52} y={42} fill={T.dim} fontSize={12}>AI model step</text>
        <rect x={170} y={30} width={14} height={14} rx={3} fill={T.raised} stroke={T.acc} strokeWidth={1.5} /><text x={192} y={42} fill={T.dim} fontSize={12}>plain code / fixed tools</text>
      </g>
      {S.map(([t, s, code], i) => (
        <g key={t} className="dg-lit" style={at(i)}>
          <Box x={cx(i)} y={y} w={w} h={h} title={t} sub={s} accent={code} />
          {i < 6 && <Line id="ag" d={`M${cx(i) + w + 1} ${y + h / 2} H${cx(i + 1) - 2}`} />}
        </g>
      ))}
      <g className="dg-lit" style={at(5)}>
        <path d={`M${cx(4) + w / 2} ${y - 2} C${cx(4) + w / 2} 110 ${cx(2) + w / 2} 110 ${cx(2) + w / 2} ${y - 4}`} fill="none" stroke={T.warn} strokeWidth={1.4} strokeDasharray="5 4" markerEnd="url(#ag-a)" />
        <text x={(cx(2) + cx(4)) / 2 + w / 2} y={118} textAnchor="middle" fill={T.warn} fontSize={12.5}>not enough? back to Plan · max 3 rounds</text>
      </g>
      <g className="dg-lit" style={at(7)}>
        <path d={`M${cx(6) + w / 2} ${y + h + 2} C${cx(6) + w / 2} 360 640 340 560 372`} fill="none" stroke={T.ok} strokeWidth={1.4} markerEnd="url(#ag-a)" />
        <path d={`M${cx(6) + w / 2} ${y + h + 2} V392`} fill="none" stroke={T.dim} strokeWidth={1.4} markerEnd="url(#ag-a)" />
        <rect x={330} y={352} width={228} height={92} rx={10} fill={T.panel} stroke={T.ok} />
        <text x={444} y={390} textAnchor="middle" fill={T.ok} fontSize={15} fontWeight={600}>Answer with quotes</text>
        <text x={444} y={412} textAnchor="middle" fill={T.dim} fontSize={12}>every claim cites a verbatim quote</text>
        <rect x={690} y={394} width={250} height={92} rx={10} fill={T.panel} stroke={T.line} />
        <text x={815} y={432} textAnchor="middle" fill={T.fg} fontSize={15} fontWeight={600}>“Not established”</text>
        <text x={815} y={454} textAnchor="middle" fill={T.dim} fontSize={12}>no verified quote, or evidence not enough</text>
      </g>
      <text x={480} y={522} textAnchor="middle" fill={T.dim} fontSize={12}>The AI model proposes; plain code checks every quote and makes the final call.</text>
    </Frame>
  );
}
