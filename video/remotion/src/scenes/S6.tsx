import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SOURCE_CHATS_LABEL } from "../theme";
import { easeInOut, pop, sec, SPRING_ACCENT } from "../motion";
import { Box, Chip, Dot, Line, Scene, T } from "../primitives";
import { Ambient, breathe, Header, Phase, Pulse, ramp, Strike, typed, useBeats } from "../fx";

/**
 * S6 — Live product: landing → onboard → ask (script.md v4.2)
 * One browser frame stays put; a stepper on top tracks the journey and the frame contents swap:
 * landing (architecture + linking, then tests + results) → onboard (connect → workspace → items + graph)
 * → ask a why, watch the trace, open cites. Footer: live Apache Kafka demo data, not a toy Acme sample.
 */
const FX = 260;
const FY = 300;
const FW = 1400;
const FH = 590;
const IN_Y = FY + 52;
const STEPS = ["Landing", "Onboard", "Ask"];
const SX = [660, 960, 1260];
const Q = "Why are Kafka producers non-idempotent by default in 3.0?";
const TRACE = ["understand", "seed", "plan", "retrieve", "evaluate", "synthesize", "verify"];
const NET: Array<[number, number]> = [
  [1240, 560],
  [1340, 480],
  [1440, 580],
  [1350, 680],
  [1520, 470],
  [1540, 700],
  [1250, 760],
  [1450, 790],
];

export const S6: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const LAND = b(0.04);
  const ONB = b(0.355);
  const ASK = b(0.535);
  const now = frame / 30;
  const stepIx = now < ONB ? 0 : now < ASK ? 1 : 2;
  const prog = interpolate(frame, [sec(ONB), sec(ONB + 0.7), sec(ASK), sec(ASK + 0.7)], [0, 0.5, 0.5, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeInOut,
  });
  const traceDone = Math.max(0, Math.min(TRACE.length, Math.floor((now - b(0.6)) / Math.max(0.2, b(0.06) / TRACE.length))));

  return (
    <Scene>
      <Ambient />
      <Header at={0.05} tag="Live product" title="Open the hosted app — follow the journey" />

      {/* stepper */}
      <Line at={0.4} x1={SX[0]} y1={252} x2={SX[2]} y2={252} width={3} />
      <div style={{ position: "absolute", left: SX[0], top: 250, height: 4, width: (SX[2] - SX[0]) * prog, background: C.AC, boxShadow: "0 0 12px rgba(124,180,255,0.6)" }} />
      {STEPS.map((s, i) => (
        <Chip
          key={s}
          at={0.5 + i * 0.15}
          x={SX[i]}
          y={228}
          label={s}
          size={26}
          pad={18}
          w={170}
          fill={stepIx === i ? "#1B2740" : C.CARD}
          outline={stepIx >= i ? C.AC : C.LINE}
          color={stepIx === i ? C.AC : stepIx > i ? C.FG : C.DIM}
          weight={650}
          pulseAt={[i === 1 ? ONB : i === 2 ? ASK : LAND]}
        />
      ))}

      {/* browser frame */}
      <Box at={0.3} x={FX} y={FY} w={FW} h={FH} fill="#121826" r={20} motion={{ dist: 40 }}>
        <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 52, borderBottom: `2px solid ${C.LINE}` }} />
        {[0, 1, 2].map((i) => (
          <div key={i} style={{ position: "absolute", left: 26 + i * 26, top: 19, width: 14, height: 14, borderRadius: 7, background: C.LINE }} />
        ))}
        <div style={{ position: "absolute", left: 130, top: 10, height: 32, width: 560, borderRadius: 16, background: C.INSET, display: "flex", alignItems: "center", paddingLeft: 20, fontFamily: MONO, fontSize: 18, color: C.DIM }}>
          sdlc-agent-five.vercel.app{stepIx === 1 ? "/onboard" : stepIx === 2 ? "/ask" : ""}
        </div>
      </Box>

      {/* 1 — landing */}
      <Phase to={ONB - 0.25} len={0.35}>
        <T at={LAND + 0.2} x={FX + 70} y={IN_Y + 50} size={56} weight={750}>
          Engineering Memory
        </T>
        <T at={LAND + 0.5} x={FX + 70} y={IN_Y + 125} size={28} color={C.DIM}>
          trustworthy answers to engineering “why”
        </T>
        <Box at={b(0.17)} x={FX + 70} y={IN_Y + 200} w={620} h={190} motion={{ arc: -30 }}>
          <div style={{ position: "absolute", left: 30, top: 24, fontSize: 20, letterSpacing: "0.14em", color: C.AC, fontWeight: 700 }}>ARCHITECTURE</div>
          <div style={{ position: "absolute", left: 30, top: 66, fontSize: 32, fontWeight: 650 }}>Graph → agent → verifier</div>
          <div style={{ position: "absolute", left: 30, top: 120, fontSize: 24, color: C.DIM }}>how linking works, up front</div>
        </Box>
        <Line at={b(0.2)} x1={FX + 820} y1={IN_Y + 300} x2={FX + 1000} y2={IN_Y + 240} color={C.AC} width={3} />
        <Line at={b(0.21)} x1={FX + 1000} y1={IN_Y + 240} x2={FX + 1180} y2={IN_Y + 320} color={C.AC} width={3} />
        {[
          [FX + 820, IN_Y + 300],
          [FX + 1000, IN_Y + 240],
          [FX + 1180, IN_Y + 320],
        ].map(([x, y], i) => (
          <Dot key={i} at={b(0.185) + i * 0.15} x={x} y={y} r={14} pulseAt={[b(0.25) + i * 0.2]} />
        ))}
        <T at={b(0.215)} x={FX + 1000} y={IN_Y + 380} size={22} mono color={C.AC} anchor="mm">
          REPLIES_TO · REFERENCES · CONTAINS
        </T>
        <T at={b(0.29)} x={FX + 70} y={IN_Y + 425} size={20} color={C.DIM} weight={650} style={{ letterSpacing: "0.14em" }}>
          TESTS + RESULTS, TOGETHER
        </T>
        {["445 tests passed", "gate 5 / 7", "1 → 9 / 18 reachable"].map((c, i) => (
          <Chip key={c} at={b(0.3) + i * 0.2} x={FX + 70 + i * 330} y={IN_Y + 460} label={c} size={26} pad={18} center={false} outline={i === 0 ? C.AC : C.LINE} motion={{ config: SPRING_ACCENT }} />
        ))}
      </Phase>

      {/* 2 — onboard */}
      <Phase to={ASK - 0.25} len={0.35}>
        <T at={ONB} x={FX + 70} y={IN_Y + 40} size={22} weight={700} color={C.AC} style={{ letterSpacing: "0.14em" }}>
          1 · CONNECT SOURCES
        </T>
        {["GitHub", "Jira", SOURCE_CHATS_LABEL, "KIP pages"].map((s, i) => {
          const on = ramp(frame, ONB + 0.5 + i * 0.25, 0.25);
          return (
            <Box key={s} at={ONB + 0.1 + i * 0.08} x={FX + 70} y={IN_Y + 90 + i * 84} w={500} h={68} motion={{ arc: -20, dist: 16 }}>
              <div style={{ position: "absolute", left: 24, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 28, fontWeight: 600 }}>{s}</div>
              <div style={{ position: "absolute", right: 22, top: 18, width: 60, height: 32, borderRadius: 16, background: on > 0.5 ? C.AC : C.LINE }}>
                <div style={{ position: "absolute", top: 4, left: 4 + 28 * on, width: 24, height: 24, borderRadius: 12, background: C.FG }} />
              </div>
            </Box>
          );
        })}
        <T at={b(0.415)} x={FX + 640} y={IN_Y + 40} size={22} weight={700} color={C.AC} style={{ letterSpacing: "0.14em" }}>
          2 · WORKSPACE
        </T>
        <Chip at={b(0.42)} x={FX + 640} y={IN_Y + 90} label="Apache Kafka" size={30} center={false} outline={C.AC} motion={{ config: SPRING_ACCENT }} />
        <T at={b(0.465)} x={FX + 640} y={IN_Y + 190} size={22} weight={700} color={C.AC} style={{ letterSpacing: "0.14em" }}>
          3 · ITEMS + GRAPH
        </T>
        {NET.map(([x, y], i) =>
          i > 0 ? <Line key={"l" + i} at={b(0.475) + i * 0.1} x1={NET[i - 1][0]} y1={NET[i - 1][1]} x2={x} y2={y} color={C.AC} width={2} dim={0.7} /> : null,
        )}
        {NET.map(([x, y], i) => (
          <Dot key={i} at={b(0.47) + i * 0.09} x={x} y={y} r={i % 3 === 0 ? 14 : 10} />
        ))}
        <T at={b(0.49)} x={FX + 640} y={IN_Y + 480} size={26} color={C.DIM}>
          items in, explicit links drawn
        </T>
      </Phase>

      {/* 3 — ask */}
      <Phase>
        <Box at={ASK} x={FX + 60} y={IN_Y + 36} w={FW - 120} h={84} fill={C.INSET} outline={C.AC} glow={0.3 + 0.2 * breathe(frame, 2)} motion={{ dist: 18 }}>
          <div style={{ position: "absolute", left: 28, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 30, fontWeight: 550 }}>
            {typed(Q, frame, ASK + 0.3, 34)}
            <span style={{ opacity: Math.floor(frame / 15) % 2 ? 0 : 1, color: C.AC, marginLeft: 4 }}>▍</span>
          </div>
        </Box>
        <T at={b(0.595)} x={FX + 70} y={IN_Y + 160} size={22} weight={700} color={C.AC} style={{ letterSpacing: "0.14em" }}>
          TRACE
        </T>
        {TRACE.map((s, i) => (
          <T key={s} at={b(0.595) + i * 0.08} x={FX + 70} y={IN_Y + 200 + i * 44} size={26} color={i < traceDone ? C.FG : C.DIM} mono>
            <span style={{ color: i < traceDone ? C.AC : C.LINE }}>{i < traceDone ? "✓" : "○"}</span> {s}
          </T>
        ))}
        <T at={b(0.635)} x={FX + 520} y={IN_Y + 160} size={22} weight={700} color={C.AC} style={{ letterSpacing: "0.14em" }}>
          CITATIONS — OPEN EVERY ONE
        </T>
        {[
          ["KIP thread", "discussion chat · quote ✓"],
          ["Pull request", "GitHub · quote ✓"],
          ["Commit", "GitHub · quote ✓"],
        ].map(([k, v], i) => {
          const t = b(0.645 + i * 0.022);
          return (
            <Box key={k} at={t} x={FX + 520} y={IN_Y + 200 + i * 104} w={800} h={86} outline={C.AC} glow={pop(frame, t + 0.4, 0.8, 18)} motion={{ config: SPRING_ACCENT, arc: 30 }}>
              <div style={{ position: "absolute", left: 26, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 30, fontWeight: 650 }}>{k}</div>
              <div style={{ position: "absolute", left: 270, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 24, color: C.DIM }}>{v}</div>
              <div style={{ position: "absolute", right: 26, top: 0, bottom: 0, display: "flex", alignItems: "center", fontSize: 26, color: C.AC, fontWeight: 650 }}>open ↗</div>
            </Box>
          );
        })}
        <Pulse at={b(0.71)} x={FX + 1270} y={IN_Y + 243} r={22} period={2} />
      </Phase>

      {/* footer — live Kafka data */}
      <Chip
        at={b(0.685)}
        x={520}
        y={925}
        label={<>Live <b style={{ color: C.AC }}>Apache Kafka</b> demo data</>}
        size={30}
        outline={C.AC}
        motion={{ config: SPRING_ACCENT }}
        pulseAt={[b(0.9)]}
      />
      <T at={b(0.72)} x={790} y={948} size={26} color={C.DIM} anchor="lm">
        discussion chats · Jira · GitHub · KIPs
      </T>
      <Chip
        at={b(0.9)}
        x={1620}
        y={925}
        label={<Strike p={ramp(frame, b(0.91), 0.5)} color={C.AC}>toy Acme sample</Strike>}
        size={26}
        color={C.DIM}
        dashed
        motion={{ config: SPRING_ACCENT, dist: 0, squash: 0.1 }}
      />
    </Scene>
  );
};
