import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, SOURCE_CHATS_LABEL, W } from "../theme";
import { easeInOut, pop, sec, SPRING_ACCENT } from "../motion";
import { Box, Chip, Dot, Line, Scene, T, Tag } from "../primitives";
import { Ambient, breathe, Flow, glowShadow, Phase, Pulse, ramp, useBeats } from "../fx";

/**
 * S3 — What the MVPs are (script.md v4.2)
 * Persistent journey rail on top (MVP 1 · 2 · 3) with a focus stage below that swaps per MVP:
 * evidence graph (Neo4j, explicit links) → agent loop + guardrails → FastAPI + Next.js workbench / Sarvam
 * → Engineering Memory: TODAY graph + verified Q&A cites · NEXT versioned memory store.
 */
const RAIL_Y = 120;
const NODES = [
  { x: 420, label: "Evidence graph" },
  { x: 960, label: "Agent loop" },
  { x: 1500, label: "Workbench" },
];
const STEPS = ["understand", "seed", "plan", "retrieve", "evaluate", "synthesize", "verify"];
const PW = 206;
const PG = 22;
const PX0 = (W - (7 * PW + 6 * PG)) / 2;
const GRAPH: Array<[number, number]> = [
  [1010, 560],
  [1180, 470],
  [1350, 590],
  [1220, 700],
  [1520, 500],
  [1560, 690],
  [1060, 760],
];
const EDGES: Array<[number, number]> = [
  [0, 1],
  [1, 2],
  [2, 3],
  [0, 6],
  [2, 4],
  [2, 5],
  [3, 6],
];

export const S3: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const M1 = b(0.0);
  const M2 = b(0.195);
  const M3 = b(0.585);
  const MEM = b(0.75);
  const now = frame / 30;
  const activeIx = now < M2 ? 0 : now < M3 ? 1 : now < MEM ? 2 : 3;

  // rail progress: grows to each node as its MVP starts, full at MEM
  const railP = interpolate(frame, [sec(M1 + 0.4), sec(M2), sec(M2 + 0.8), sec(M3), sec(M3 + 0.8), sec(MEM), sec(MEM + 0.8)], [0, 0, 0.5, 0.5, 1, 1, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeInOut,
  });

  // agent loop highlight cycles through the pills (continuous secondary motion)
  const cycleStart = b(0.34);
  const cyc = Math.floor(Math.max(0, now - cycleStart) / 0.55) % STEPS.length;

  return (
    <Scene>
      <Ambient />

      {/* Journey rail */}
      <Tag at={0.05} x={140} y={40} label="The journey" />
      <Line at={0.1} x1={NODES[0].x} y1={RAIL_Y} x2={NODES[2].x} y2={RAIL_Y} width={3} dur={0.8} />
      <div
        style={{
          position: "absolute",
          left: NODES[0].x,
          top: RAIL_Y - 2,
          width: (NODES[2].x - NODES[0].x) * railP,
          height: 4,
          background: C.AC,
          boxShadow: "0 0 14px rgba(124,180,255,0.6)",
        }}
      />
      {NODES.map((n, i) => {
        const on = activeIx >= i;
        const t = i === 0 ? 0.2 : i === 1 ? M2 : M3;
        return (
          <React.Fragment key={n.label}>
            <Dot at={i === 0 ? 0.2 : 0.3 + i * 0.15} x={n.x} y={RAIL_Y} r={14} color={on ? C.AC : C.LINE} pulseAt={[t + 0.3]} />
            {activeIx === i ? <Pulse at={t} x={n.x} y={RAIL_Y} r={18} until={i === 0 ? M2 : i === 1 ? M3 : MEM} /> : null}
            <T at={0.3 + i * 0.15} x={n.x} y={RAIL_Y + 46} size={26} weight={on ? 650 : 500} color={on ? C.FG : C.DIM} anchor="mm">
              <span style={{ color: on ? C.AC : C.DIM }}>MVP {i + 1}</span>&nbsp; {n.label}
            </T>
          </React.Fragment>
        );
      })}

      {/* MVP 1 — evidence graph */}
      <Phase to={M2 - 0.3}>
        <T at={0.4} x={140} y={240} size={64} weight={700} motion={{ dist: 24 }}>
          An <span style={{ color: C.AC }}>evidence graph</span>
        </T>
        <T at={b(0.04)} x={140} y={325} size={30} color={C.DIM}>
          Connectors pull every source · each item becomes a node
        </T>
        {["GitHub", "Jira", SOURCE_CHATS_LABEL].map((s, i) => (
          <React.Fragment key={s}>
            <Chip at={b(0.04) + i * 0.3} x={340} y={460 + i * 120} label={s} size={34} w={340} motion={{ arc: -50 }} />
            <Line at={b(0.085) + i * 0.15} x1={520} y1={492 + i * 120} x2={940} y2={620} color={C.AC} width={3} arrow bend={i === 1 ? 0 : (i - 1) * -40} />
            <Flow at={b(0.1) + i * 0.3} x1={520} y1={492 + i * 120} x2={940} y2={620} period={1.5} until={M2} />
          </React.Fragment>
        ))}
        {EDGES.map(([a, z], i) => (
          <Line key={i} at={b(0.11) + i * 0.18} x1={GRAPH[a][0]} y1={GRAPH[a][1]} x2={GRAPH[z][0]} y2={GRAPH[z][1]} color={C.AC} width={2.5} dim={0.75} />
        ))}
        {GRAPH.map(([x, y], i) => (
          <Dot key={i} at={b(0.095) + i * 0.15} x={x} y={y} r={i === 2 ? 20 : 14} pulseAt={[b(0.16) + i * 0.12]} />
        ))}
        <Chip at={b(0.12)} x={1290} y={840} label={<>Neo4j · <span style={{ color: C.AC }}>explicit links only</span></>} size={30} />
      </Phase>

      {/* MVP 2 — agent loop + guardrails */}
      <Phase to={M3 - 0.3}>
        <T at={M2} x={140} y={240} size={64} weight={700} motion={{ dist: 24 }}>
          A specialized <span style={{ color: C.AC }}>agent loop</span>
        </T>
        {STEPS.map((s, i) => {
          const t = b(0.245 + i * 0.012);
          const x = PX0 + i * (PW + PG);
          const hot = now >= cycleStart && cyc === i;
          return (
            <React.Fragment key={s}>
              <Box at={t} x={x} y={420} w={PW} h={92} outline={hot ? C.AC : C.LINE} glow={hot ? 0.8 : 0} motion={{ dist: 22, config: SPRING_ACCENT }} extraScale={hot ? 0.04 : 0}>
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26, fontWeight: 600, color: hot ? C.AC : C.FG }}>
                  {s}
                </div>
              </Box>
              {i > 0 ? <Line at={t - 0.1} x1={x - PG + 2} y1={466} x2={x - 4} y2={466} color={C.AC} width={3} arrow /> : null}
            </React.Fragment>
          );
        })}
        <Line at={b(0.36)} x1={PX0 + 6 * (PW + PG) + PW / 2} y1={518} x2={PX0 + 3 * (PW + PG) + PW / 2} y2={518} color={C.AC} width={2.5} dashed arrow bend={-70} dur={0.9} />
        <T at={b(0.375)} x={PX0 + 4.6 * (PW + PG)} y={600} size={26} color={C.DIM} anchor="mm">
          a few bounded rounds when evidence is thin
        </T>
        <Tag at={b(0.425)} x={140} y={700} label="Guardrails in code" />
        {["read-only tools", "ID guard: open only what it has seen", "quote verifier"].map((g, i) => (
          <Chip
            key={g}
            at={b(0.445 + i * 0.04)}
            x={[330, 890, 1500][i]}
            y={760}
            label={g}
            size={32}
            outline={i === 2 ? C.AC : C.LINE}
            color={i === 2 ? C.AC : C.FG}
            motion={{ config: SPRING_ACCENT }}
            pulseAt={[b(0.55) + i * 0.2]}
          />
        ))}
      </Phase>

      {/* MVP 3 — workbench */}
      <Phase to={MEM - 0.3}>
        <T at={M3} x={140} y={240} size={64} weight={700} motion={{ dist: 24 }}>
          A <span style={{ color: C.AC }}>workbench</span> you can use
        </T>
        {[
          ["Next.js", "the workbench on top"],
          ["FastAPI", "API + agent behind it"],
          ["Any OpenAI-compatible model", "plug in your provider"],
        ].map(([k, v], i) => (
          <Box key={k} at={b(0.6 + i * 0.03)} x={360} y={390 + i * 140} w={1200} h={112} outline={i === 2 ? C.AC : C.LINE} motion={{ dist: 30, arc: i % 2 ? 40 : -40 }}>
            <div style={{ position: "absolute", left: 44, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 40, fontWeight: 700 }}>{k}</div>
            <div style={{ position: "absolute", right: 44, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 28, color: C.DIM }}>{v}</div>
          </Box>
        ))}
        <Chip
          at={b(0.715)}
          x={W / 2}
          y={840}
          label={<>we run <b style={{ color: C.AC }}>Sarvam</b></>}
          size={40}
          outline={C.AC}
          motion={{ config: SPRING_ACCENT, dist: 30, windup: 10 }}
          pulseAt={[b(0.73)]}
        />
      </Phase>

      {/* Engineering Memory — today vs next */}
      <Phase>
        <T at={MEM} x={W / 2} y={290} size={40} color={C.DIM} anchor="mm">
          Across every MVP runs
        </T>
        <T
          at={MEM + 0.4}
          x={W / 2}
          y={370}
          size={84}
          weight={750}
          anchor="mm"
          motion={{ config: SPRING_ACCENT, dist: 30, windup: 12 }}
          style={{ textShadow: glowShadow(0.6 + 0.4 * breathe(frame, 2.4)) }}
        >
          Engineering Memory
        </T>
        <Box at={b(0.795)} x={160} y={490} w={780} h={300} outline={C.AC} glow={ramp(frame, b(0.8), 0.6) * (0.6 + 0.3 * breathe(frame, 2))} motion={{ config: SPRING_ACCENT, arc: -40 }}>
          <div style={{ position: "absolute", left: 44, top: 40, fontSize: 24, fontWeight: 700, letterSpacing: "0.14em", color: C.AC }}>TODAY</div>
          <div style={{ position: "absolute", left: 44, top: 96, fontSize: 46, fontWeight: 700 }}>Evidence graph</div>
          <div style={{ position: "absolute", left: 44, top: 160, fontSize: 46, fontWeight: 700 }}>+ verified Q&amp;A</div>
          <div style={{ position: "absolute", left: 44, top: 234, fontSize: 28, color: C.DIM }}>with citations you can open</div>
        </Box>
        <Box at={b(0.895)} x={980} y={490} w={780} h={300} fill={C.WELL} outline={C.DIM} dashed motion={{ arc: 40 }}>
          <div style={{ position: "absolute", left: 44, top: 40, fontSize: 24, fontWeight: 700, letterSpacing: "0.14em", color: C.DIM }}>NEXT</div>
          <div style={{ position: "absolute", left: 44, top: 96, fontSize: 46, fontWeight: 700 }}>Versioned</div>
          <div style={{ position: "absolute", left: 44, top: 160, fontSize: 46, fontWeight: 700 }}>memory store</div>
          <div style={{ position: "absolute", left: 44, top: 234, fontSize: 28, color: C.DIM }}>keeps lasting facts current</div>
        </Box>
        <T at={b(0.905)} x={W / 2} y={870} size={30} color={C.DIM} anchor="mm" extraScale={pop(frame, b(0.92), 0.05, 16)}>
          present now · <span style={{ color: C.FG }}>comes next</span>
        </T>
      </Phase>
    </Scene>
  );
};
