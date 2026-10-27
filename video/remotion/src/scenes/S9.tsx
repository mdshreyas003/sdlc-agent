import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SOURCE_CHATS_LABEL, W } from "../theme";
import { easeInOut, pop, sec, SPRING_ACCENT } from "../motion";
import { Box, Chip, Line, Scene, T } from "../primitives";
import { Ambient, breathe, every, glowShadow, Header, Phase, Pulse, ramp, Underline, useBeats } from "../fx";

/**
 * S9 — Future and close (script.md v4.2, memory-softened)
 * A: bigger than one Q&A bot → present now = graph + cites → a central knowledge base where sources relate.
 * B: NOW graph + cites · NEXT versioned memory · AHEAD shared base for research / review / planning agents.
 * C: close — "answers you can check, or an honest Not established" + repo + live URL.
 */
const ORBIT = [SOURCE_CHATS_LABEL, "Tickets", "Code", "Decisions"];
const KB = { x: 960, y: 640, r: 130, orbit: 300 };
const COLS = [
  { k: "NOW", title: "Graph + cites", sub: ["linked evidence +", "verified answers"], x: 160 },
  { k: "NEXT", title: "Versioned memory", sub: ["newer decisions supersede older", "ones when the trail says so"], x: 700 },
  { k: "AHEAD", title: "Shared base", sub: ["different agents work together,", "drawing from + writing back"], x: 1240 },
];
const CW = 520;

export const S9: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const ROAD = b(0.42);
  const CLOSE = b(0.845);
  const now = frame / 30;
  // Strictly increasing keyframes (avoid ties when D≈50s collapses ROAD+1.0 onto b(0.44))
  const colAt = [b(0.43), b(0.52), b(0.62)];
  const trackKeys = [sec(colAt[0]), sec(colAt[0] + 0.6), sec(colAt[1]), sec(colAt[1] + 0.6), sec(colAt[2]), sec(colAt[2] + 0.6)];
  const trackP = interpolate(frame, trackKeys, [0, 0.17, 0.17, 0.5, 0.5, 0.83], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: easeInOut,
  });
  const orbitA = Math.max(0, now - b(0.29)) * 0.18;

  return (
    <Scene>
      <Ambient />

      {/* A — bigger than one Q&A bot → central knowledge base */}
      <Phase to={ROAD - 0.3}>
        <Header at={0.05} tag="Future and close" title="Bigger than one Q&A bot" sub={<>Present now: <span style={{ color: C.FG }}>graph + cites</span> — linked evidence and verified answers</>} />
        <Chip at={b(0.04)} x={KB.x} y={KB.y - 30} label="one agent · why-questions" size={34} outline={C.AC} motion={{ config: SPRING_ACCENT }} dim={1 - ramp(frame, b(0.26), 0.5)} />
        {/* knowledge base core */}
        {ramp(frame, b(0.275), 0.6) > 0 ? (
          <div
            style={{
              position: "absolute",
              left: KB.x - KB.r,
              top: KB.y - KB.r,
              width: KB.r * 2,
              height: KB.r * 2,
              borderRadius: "50%",
              background: "radial-gradient(circle, rgba(124,180,255,0.35), rgba(124,180,255,0.08) 70%)",
              border: `2px solid ${C.AC}`,
              boxShadow: glowShadow(0.6 + 0.4 * breathe(frame, 2.6), 60),
              opacity: ramp(frame, b(0.275), 0.6),
              transform: `scale(${0.6 + 0.4 * ramp(frame, b(0.275), 0.8) + pop(frame, b(0.275) + 0.8, 0.06, 18)})`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              fontSize: 30,
              fontWeight: 700,
              lineHeight: 1.2,
            }}
          >
            central
            <br />
            knowledge base
          </div>
        ) : null}
        <Pulse at={b(0.3)} x={KB.x} y={KB.y} r={KB.r} period={2.8} />
        {ORBIT.map((s, i) => {
          const at = b(0.3 + i * 0.015);
          const o = ramp(frame, at, 0.5);
          if (o <= 0) return null;
          const a = orbitA + (i * Math.PI * 2) / ORBIT.length - Math.PI / 4;
          const x = KB.x + KB.orbit * 1.5 * Math.cos(a);
          const y = KB.y + KB.orbit * 0.72 * Math.sin(a);
          return (
            <React.Fragment key={s}>
              <svg style={{ position: "absolute", left: 0, top: 0, opacity: 0.5 * o }} width={1920} height={1080}>
                <line x1={KB.x} y1={KB.y} x2={x} y2={y} stroke={C.AC} strokeWidth={2} strokeDasharray="6 8" />
              </svg>
              <div
                style={{
                  position: "absolute",
                  left: x,
                  top: y,
                  transform: `translate(-50%, -50%) scale(${0.7 + 0.3 * o})`,
                  opacity: o,
                  padding: "12px 28px",
                  borderRadius: 40,
                  background: C.CARD,
                  border: `2px solid ${C.LINE}`,
                  fontSize: 30,
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                }}
              >
                {s}
              </div>
            </React.Fragment>
          );
        })}
        <T at={b(0.36)} x={W / 2} y={960} size={32} color={C.DIM} anchor="mm">
          one place where the team’s engineering history already relates
        </T>
      </Phase>

      {/* B — roadmap */}
      <Phase to={CLOSE - 0.3}>
        <Header at={ROAD} tag="Where it goes" title="One base, growing deeper" />
        <Line at={ROAD + 0.1} x1={160} y1={300} x2={1760} y2={300} width={3} dur={0.9} />
        <div style={{ position: "absolute", left: 160, top: 298, height: 4, width: 1600 * trackP, background: C.AC, boxShadow: "0 0 14px rgba(124,180,255,0.6)" }} />
        {COLS.map((c, i) => {
          const at = colAt[i];
          const on = now >= at;
          const isNow = i === 0;
          return (
            <React.Fragment key={c.k}>
              {on ? <Pulse at={at} x={c.x + CW / 2} y={300} r={14} period={2} until={i < 2 ? colAt[i + 1] + 1.5 : Infinity} /> : null}
              <div
                style={{
                  position: "absolute",
                  left: c.x + CW / 2 - 12,
                  top: 288,
                  width: 24,
                  height: 24,
                  borderRadius: 12,
                  background: on ? C.AC : C.LINE,
                  transform: `scale(${1 + pop(frame, at, 0.5, 16)})`,
                }}
              />
              <Box
                at={at}
                x={c.x}
                y={350}
                w={CW}
                h={360}
                fill={isNow ? C.CARD : C.WELL}
                outline={isNow ? C.AC : C.DIM}
                dashed={!isNow}
                glow={isNow ? 0.35 + 0.2 * breathe(frame, 2.6) : pop(frame, at + 0.5, 0.6, 20)}
                motion={{ config: SPRING_ACCENT, dist: 34, arc: (i - 1) * 40 }}
              >
                <div style={{ position: "absolute", left: 40, top: 40, fontSize: 24, fontWeight: 750, letterSpacing: "0.16em", color: isNow ? C.AC : C.DIM }}>{c.k}</div>
                <div style={{ position: "absolute", left: 40, top: 92, fontSize: 48, fontWeight: 750 }}>{c.title}</div>
                <div style={{ position: "absolute", left: 40, top: 176, fontSize: 28, color: C.DIM, lineHeight: 1.4 }}>
                  {c.sub[0]}
                  <br />
                  {c.sub[1]}
                </div>
              </Box>
            </React.Fragment>
          );
        })}
        {["research", "review", "planning"].map((a, i) => {
          const x = 1240 + 40 + i * 160;
          return (
            <React.Fragment key={a}>
              <Chip
                at={b(0.695 + i * 0.012)}
                x={x}
                y={630}
                label={a}
                size={22}
                pad={14}
                center={false}
                outline={C.AC}
                color={C.AC}
                motion={{ config: SPRING_ACCENT, dist: 20 }}
                pulseAt={every(b(0.73) + i * 0.4, CLOSE, 2.4)}
              />
            </React.Fragment>
          );
        })}
        <T at={b(0.795)} x={W / 2} y={800} size={36} weight={600} anchor="mm" motion={{ config: SPRING_ACCENT }}>
          From here: <span style={{ color: C.AC }}>grow the sources</span> · <span style={{ color: C.AC }}>measure harder against baselines</span>
        </T>
      </Phase>

      {/* C — close */}
      <Phase>
        <T
          at={CLOSE}
          x={W / 2}
          y={330}
          size={116}
          weight={800}
          anchor="mm"
          motion={{ config: SPRING_ACCENT, dist: 40, windup: 12, squash: 0.035 }}
          style={{ textShadow: glowShadow(ramp(frame, CLOSE + 0.4, 1) * (0.55 + 0.45 * breathe(frame, 2.8)), 48) }}
        >
          Engineering Memory
        </T>
        <Underline at={b(0.86)} x={W / 2} y={410} w={760} h={5} />
        <T at={b(0.865)} x={W / 2} y={480} size={42} anchor="mm" motion={{ delay: 2 }}>
          A central knowledge base you can trust
        </T>
        <T at={b(0.885)} x={W / 2} y={590} size={50} weight={650} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 20 }}>
          Answers you can check — or an honest{" "}
          <span style={{ color: C.AC, fontWeight: 750, textShadow: glowShadow(ramp(frame, b(0.9), 0.6)) }}>“Not established.”</span>
        </T>
        <Box at={b(0.905)} x={W / 2 - 420} y={700} w={840} h={170} fill={C.INSET} motion={{ dist: 20 }}>
          <div style={{ position: "absolute", left: 0, right: 0, top: 34, textAlign: "center", fontFamily: MONO, fontSize: 32, color: C.FG }}>github.com/mdshreyas003/sdlc-agent</div>
          <div style={{ position: "absolute", left: 0, right: 0, top: 96, textAlign: "center", fontFamily: MONO, fontSize: 32, color: C.AC }}>sdlc-agent-five.vercel.app</div>
        </Box>
      </Phase>
    </Scene>
  );
};
