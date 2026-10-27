import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SOURCE_CHATS_LABEL, W } from "../theme";
import { easeInOut, pop, sec, SPRING_ACCENT, stage } from "../motion";
import { Box, Chip, Line, Scene, T, Tag } from "../primitives";
import { Ambient, breathe, every, Flow, glowShadow, Header, Phase, Pulse, ramp, Underline, useBeats } from "../fx";

/**
 * S8 — Architecture that makes it effective (script.md v4.2)
 * 1) Linkage engine (new category): REPLIES_TO / REFERENCES / CONTAINS, no guessed edges, scattered
 *    tools snap into one evidence graph. 2) Agent loop + code guardrails as a living circle.
 * 3) Together: an audit trail from question to linked evidence.
 */
const RELS: Array<[string, string, string]> = [
  ["Reply", "REPLIES_TO", "Thread"],
  ["Ticket key in message", "REFERENCES", "Ticket"],
  ["Pull request", "CONTAINS", "Commit"],
];
const SRC = ["Commits", SOURCE_CHATS_LABEL, "Tickets", "Pull requests", "Docs"];
const RC = { x: 500, y: 640, r: 230 };
const SCATTER: Array<[number, number]> = [
  [230, 380],
  [760, 900],
  [300, 930],
  [820, 400],
  [520, 560],
];
const GEDGES: Array<[number, number]> = [
  [1, 2],
  [3, 0],
  [2, 3],
  [4, 2],
  [1, 3],
  [1, 1],
];
const STEPS = ["understand", "seed", "plan", "retrieve", "evaluate", "synthesize", "verify"];
const AC_ = { x: 620, y: 640, r: 270 };
const TRAIL = ["Question", "Ticket", "Discussion chat", "Pull request", "Commit", "Answer + quote"];
const TEDGE = ["seed ID", "REFERENCES", "REFERENCES", "CONTAINS", "quote ✓"];
const TX = (i: number) => 175 + i * 314;

export const S8: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const LINK = b(0.145);
  const SNAP = b(0.445);
  const AGENT = b(0.61);
  const TR = b(0.83);
  const now = frame / 30;
  const snap = interpolate(frame, [sec(SNAP), sec(SNAP + 0.9)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: easeInOut });
  const ringPos = (i: number): [number, number] => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / SRC.length;
    return [RC.x + RC.r * Math.cos(a), RC.y + RC.r * Math.sin(a)];
  };
  const rightDim = stage(frame, [[b(0.525), Infinity]], 0.6);

  // agent orb (continuous secondary motion)
  const orbStart = b(0.675);
  const period = 4.6;
  const orbA = -Math.PI / 2 + (Math.max(0, now - orbStart) / period) * Math.PI * 2;
  const stepA = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / STEPS.length;
  const hotStep = now >= orbStart ? Math.round((((orbA + Math.PI / 2) / (2 * Math.PI)) * STEPS.length)) % STEPS.length : -1;
  const ring = ramp(frame, b(0.615), 1.2);

  return (
    <Scene>
      <Ambient hue="left" />

      {/* Intro — two architectures */}
      <Phase to={LINK - 0.3}>
        <Header at={0.05} tag="Architecture that works" title="Two architectures, working together" />
        {[
          ["01", "Linkage engine", "how evidence relates"],
          ["02", "Agent loop", "how answers get checked"],
        ].map(([n, k, v], i) => (
          <Box key={n} at={b(0.03 + i * 0.045)} x={i ? 1000 : 160} y={330} w={760} h={320} outline={C.AC} glow={0.3 + 0.2 * breathe(frame, 2.4, i * 2)} motion={{ config: SPRING_ACCENT, arc: i ? 50 : -50 }}>
            <div style={{ position: "absolute", left: 50, top: 50, fontFamily: MONO, fontSize: 30, color: C.AC, fontWeight: 700 }}>{n}</div>
            <div style={{ position: "absolute", left: 50, top: 110, fontSize: 64, fontWeight: 750 }}>{k}</div>
            <div style={{ position: "absolute", left: 50, top: 200, fontSize: 34, color: C.DIM }}>{v}</div>
          </Box>
        ))}
        <T at={b(0.06)} x={W / 2} y={490} size={72} weight={800} color={C.AC} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 0, squash: 0.12 }}>
          +
        </T>
        <T at={b(0.1)} x={W / 2} y={760} size={40} weight={600} anchor="mm">
          not a passive walkthrough of boxes
        </T>
      </Phase>

      {/* 1 — Linkage engine */}
      <Phase to={AGENT - 0.3}>
        <Header at={LINK} tag="Architecture · part 1" title="The linkage engine" />
        <Chip
          at={LINK + 0.6}
          x={760}
          y={124}
          label="NEW CATEGORY"
          color={C.AC}
          size={24}
          pad={16}
          outline={C.AC}
          center={false}
          weight={700}
          pulseAt={[b(0.53), b(0.535) + 0.4]}
        />

        {/* scattered tools → one evidence graph */}
        {GEDGES.map(([a, z], i) => {
          if (a === z) return null;
          const [x1, y1] = ringPos(a);
          const [x2, y2] = ringPos(z);
          return (
            <React.Fragment key={i}>
              <Line at={SNAP + 0.8 + i * 0.25} x1={x1} y1={y1} x2={x2} y2={y2} color={C.AC} width={3} dim={0.8} />
              <Flow at={SNAP + 1.6 + i * 0.3} x1={x1} y1={y1} x2={x2} y2={y2} period={1.8 + i * 0.2} until={AGENT} />
            </React.Fragment>
          );
        })}
        {SRC.map((s, i) => {
          const at = b(0.155 + i * 0.012);
          const o = ramp(frame, at, 0.5);
          if (o <= 0) return null;
          const [rx, ry] = ringPos(i);
          const [sx, sy] = SCATTER[i];
          const jx = 14 * Math.sin(now * 1.1 + i * 1.7) * (1 - snap);
          const jy = 12 * Math.cos(now * 0.9 + i * 2.3) * (1 - snap);
          const x = sx + (rx - sx) * snap + jx;
          const y = sy + (ry - sy) * snap + jy;
          return (
            <div
              key={s}
              style={{
                position: "absolute",
                left: x,
                top: y,
                transform: `translate(-50%, -50%) scale(${0.7 + 0.3 * o + pop(frame, SNAP + 0.9, 0.08, 14)})`,
                opacity: o,
                padding: "12px 26px",
                borderRadius: 40,
                background: C.CARD,
                border: `2px solid ${snap > 0.5 ? C.AC : C.LINE}`,
                fontSize: 28,
                fontWeight: 600,
                whiteSpace: "nowrap",
                boxShadow: snap > 0.5 ? glowShadow(0.4, 24) : "none",
              }}
            >
              {s}
            </div>
          );
        })}
        <T at={SNAP + 1.0} x={RC.x} y={RC.y} size={30} weight={700} color={C.AC} anchor="mm" style={{ textAlign: "center", lineHeight: 1.2 }}>
          one evidence
          <br />
          graph
        </T>
        <Pulse at={SNAP + 1.2} x={RC.x} y={RC.y} r={80} period={2.4} until={AGENT} />
        <T at={b(0.2)} x={RC.x} y={RC.y} size={28} color={C.DIM} anchor="mm" dim={1 - snap}>
          scattered tools
        </T>

        {/* explicit relationships */}
        {RELS.map(([a, edge, z], i) => {
          const t = b([0.235, 0.27, 0.315][i]);
          const y = 300 + i * 110;
          return (
            <React.Fragment key={edge}>
              <Chip at={t} x={1000} y={y} label={a} size={24} pad={16} w={360} center={false} dim={rightDim} motion={{ arc: 30 }} />
              <Line at={t + 0.3} x1={1372} y1={y + 23} x2={1556} y2={y + 23} color={C.AC} width={3} arrow dim={rightDim} />
              <T at={t + 0.4} x={1464} y={y - 8} size={18} weight={700} mono color={C.AC} anchor="mm" dim={rightDim} extraScale={pop(frame, t + 0.7, 0.14, 14)} motion={{ config: SPRING_ACCENT, dist: 10 }}>
                {edge}
              </T>
              <Chip at={t + 0.5} x={1570} y={y} label={z} size={24} pad={16} w={200} center={false} dim={rightDim} motion={{ arc: 30 }} />
            </React.Fragment>
          );
        })}
        <Box at={b(0.375)} x={1000} y={640} w={780} h={130} fill={C.WELL} outline={C.DIM} dashed dim={rightDim} motion={{ arc: 40 }}>
          <div style={{ position: "absolute", left: 36, top: 22, fontSize: 38, fontWeight: 700 }}>
            No guessed edges <span style={{ color: C.AC }}>✕</span>
          </div>
          <div style={{ position: "absolute", left: 36, top: 78, fontSize: 26, color: C.DIM }}>only relationships people already wrote down</div>
        </Box>
        <Box
          at={b(0.525)}
          x={1000}
          y={800}
          w={780}
          h={150}
          outline={C.AC}
          glow={ramp(frame, b(0.53), 0.6) * (0.6 + 0.4 * breathe(frame, 2))}
          motion={{ config: SPRING_ACCENT, dist: 30, windup: 10 }}
          extraScale={pop(frame, b(0.525) + 0.5, 0.05, 16)}
        >
          <div style={{ position: "absolute", left: 36, top: 26, fontSize: 38, fontWeight: 750, color: C.AC }}>Engineering evidence linking</div>
          <div style={{ position: "absolute", left: 36, top: 88, fontSize: 28, color: C.DIM }}>a new category — not another search index</div>
        </Box>
      </Phase>

      {/* 2 — Agent loop + guardrails */}
      <Phase to={TR - 0.3}>
        <Header at={AGENT} tag="Architecture · part 2" title="The agent loop" />
        <svg style={{ position: "absolute", left: 0, top: 0 }} width={1920} height={1080}>
          <circle
            cx={AC_.x}
            cy={AC_.y}
            r={AC_.r}
            fill="none"
            stroke={C.LINE}
            strokeWidth={3}
            strokeDasharray={2 * Math.PI * AC_.r}
            strokeDashoffset={2 * Math.PI * AC_.r * (1 - ring)}
            transform={`rotate(-90 ${AC_.x} ${AC_.y})`}
          />
        </svg>
        {now >= orbStart ? (
          <div
            style={{
              position: "absolute",
              left: AC_.x + AC_.r * Math.cos(orbA) - 12,
              top: AC_.y + AC_.r * Math.sin(orbA) - 12,
              width: 24,
              height: 24,
              borderRadius: 12,
              background: "#E6F0FF",
              boxShadow: "0 0 24px 8px rgba(124,180,255,0.7)",
              opacity: ramp(frame, orbStart, 0.4),
            }}
          />
        ) : null}
        {STEPS.map((s, i) => {
          const a = stepA(i);
          const hot = hotStep === i;
          return (
            <Chip
              key={s}
              at={b(0.62 + i * 0.008)}
              x={AC_.x + AC_.r * Math.cos(a)}
              y={AC_.y + AC_.r * Math.sin(a) - 27}
              label={s}
              size={26}
              pad={16}
              color={hot ? C.AC : C.FG}
              outline={hot || i === 6 ? C.AC : C.LINE}
              fill={hot ? "#1B2740" : C.CARD}
              motion={{ config: SPRING_ACCENT, dist: 20 }}
            />
          );
        })}
        <T at={b(0.64)} x={AC_.x} y={AC_.y - 20} size={46} weight={750} anchor="mm">
          checked loop
        </T>
        <T at={b(0.65)} x={AC_.x} y={AC_.y + 36} size={26} color={C.DIM} anchor="mm">
          not a single prompt
        </T>
        <Tag at={b(0.695)} x={1080} y={320} label="Code guardrails" />
        {["read-only tools", "ID guard — opens only what it has seen", "quote verifier"].map((g, i) => (
          <Chip key={g} at={b(0.7 + i * 0.015)} x={1080} y={370 + i * 82} label={g} size={30} center={false} outline={i === 2 ? C.AC : C.LINE} motion={{ config: SPRING_ACCENT, arc: 40 }} pulseAt={every(b(0.76) + i * 0.4, TR, 3.5)} />
        ))}
        <T at={b(0.745)} x={1080} y={660} size={30} weight={650} motion={{ config: SPRING_ACCENT }}>
          <span style={{ color: C.AC }}>✓</span>&nbsp; supported claim → a quote you can open
        </T>
        <T at={b(0.775)} x={1080} y={730} size={30} weight={650} color={C.DIM} motion={{ config: SPRING_ACCENT }}>
          ?&nbsp; unknown → stays unknown, no fake cite
        </T>
      </Phase>

      {/* 3 — Together: an audit trail */}
      <Phase>
        <Header at={TR} tag="Together" title="A trail from question to linked evidence" />
        {TRAIL.map((s, i) => {
          const t = b(0.84 + i * 0.008);
          return (
            <React.Fragment key={s}>
              {i > 0 ? (
                <>
                  <Line at={t - 0.15} x1={TX(i - 1) + 104} y1={500} x2={TX(i) - 104} y2={500} color={C.AC} width={3} arrow />
                  <Flow at={t + 0.6} x1={TX(i - 1) + 104} y1={500} x2={TX(i) - 104} y2={500} period={1.2} />
                  <T at={t} x={(TX(i - 1) + TX(i)) / 2} y={460} size={16} weight={700} mono color={C.AC} anchor="mm">
                    {TEDGE[i - 1]}
                  </T>
                </>
              ) : null}
              <Chip
                at={t}
                x={TX(i)}
                y={473}
                label={s}
                size={22}
                pad={14}
                w={200}
                outline={i === 0 || i === TRAIL.length - 1 ? C.AC : C.LINE}
                color={i === TRAIL.length - 1 ? C.AC : C.FG}
                motion={{ config: SPRING_ACCENT, dist: 24 }}
                pulseAt={every(b(0.9) + i * 0.25, b(1), 2.2)}
              />
            </React.Fragment>
          );
        })}
        <T
          at={b(0.885)}
          x={W / 2}
          y={690}
          size={72}
          weight={750}
          anchor="mm"
          motion={{ config: SPRING_ACCENT, dist: 30, windup: 12 }}
          style={{ textShadow: glowShadow(0.4 + 0.4 * breathe(frame, 2.4)) }}
        >
          A relationship map you can <span style={{ color: C.AC }}>audit</span>
        </T>
        <Underline at={b(0.9)} x={W / 2} y={750} w={880} />
        <T at={b(0.915)} x={W / 2} y={830} size={36} color={C.DIM} anchor="mm">
          not a black-box score
        </T>
      </Phase>
    </Scene>
  );
};
