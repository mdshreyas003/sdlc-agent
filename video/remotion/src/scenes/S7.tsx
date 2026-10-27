import React from "react";
import { useCurrentFrame } from "remotion";
import { C, W } from "../theme";
import { pop, SPRING_ACCENT, stage } from "../motion";
import { Box, Chip, Dot, Line, Scene, T, Tag } from "../primitives";
import { Ambient, breathe, countUp, every, glowShadow, Header, Phase, Pulse, ramp, Strike, Underline, useBeats } from "../fx";

/**
 * S7 — Proof, in plain words (script.md v4.2)
 * Numbers from script SoT only: demo 1,201 / 2,194 · eval 1,191 / 1,786 · one strong investigation
 * (claims from KIP thread, PR, commit; one point Unknown) · intended outcome hours → minutes (NOT measured)
 * · Sarvam gate 5/7 · 1 → 9/18, 0 regressions · 445 passed / 7 skipped · 75 gold with traps · no fake accuracy.
 * Four focused pages instead of one dense grid; every beat is a fraction of the VO.
 */
type Card = { big: React.ReactNode; label: string; sub: string; t: number; accent?: boolean; size?: number };

const CW = 380;
const CG = 40;
const CX0 = (W - (4 * CW + 3 * CG)) / 2;

export const S7: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const INV = b(0.255);
  const OUT = b(0.425);
  const PROOF = b(0.572);
  const now = frame / 30;

  const cards: Card[] = [
    { big: <>{countUp("5", b(0.585) + 0.3, frame)} / 7</>, label: "Sarvam end-to-end gate", sub: "preliminary · real model", t: b(0.58) },
    {
      big: (
        <>
          1 → <span style={{ color: C.AC }}>{countUp("9", b(0.645) + 0.5, frame)}</span> / 18
        </>
      ),
      label: "fully reachable questions",
      sub: "no model · zero regressions",
      t: b(0.64),
      size: 58,
    },
    { big: <>{countUp("445", b(0.76) + 0.3, frame)}</>, label: "tests passed", sub: "7 skipped · automated suite", t: b(0.755) },
    { big: <>{countUp("75", b(0.8) + 0.3, frame)}</>, label: "gold questions", sub: "with traps built in", t: b(0.795), accent: true },
  ];
  const activeCard = cards.filter((c) => now >= c.t).length - 1;

  return (
    <Scene>
      <Ambient />
      <Header at={0.05} tag="Proof, in plain words" title="Numbers only where we can stand behind them" />
      <Chip
        at={0.3}
        x={W - 140 - 240}
        y={60}
        label="PRELIMINARY"
        color={C.AC}
        size={24}
        pad={18}
        outline={C.AC}
        center={false}
        w={240}
        weight={700}
        pulseAt={every(2, b(1), 9)}
      />

      {/* A — workspace scale */}
      <Phase to={INV - 0.3}>
        <Tag at={b(0.04)} x={160} y={300} label="Kafka demo workspace" />
        <T at={b(0.05)} x={160} y={340} size={168} weight={800} color={C.AC} style={{ fontVariantNumeric: "tabular-nums", textShadow: glowShadow(0.4 + 0.3 * breathe(frame, 3)) }} motion={{ config: SPRING_ACCENT }}>
          {countUp("1,201", b(0.05) + 0.2, frame, 1.6)}
        </T>
        <T at={b(0.06)} x={170} y={540} size={40} weight={600}>
          items
        </T>
        <T at={b(0.09)} x={1000} y={340} size={168} weight={800} color={C.AC} style={{ fontVariantNumeric: "tabular-nums", textShadow: glowShadow(0.4 + 0.3 * breathe(frame, 3, 1.5)) }} motion={{ config: SPRING_ACCENT }}>
          {countUp("2,194", b(0.09) + 0.2, frame, 1.6)}
        </T>
        <T at={b(0.1)} x={1010} y={540} size={40} weight={600}>
          explicit links
        </T>
        <Underline at={b(0.13)} x={160} y={610} w={1600} from="left" h={3} dur={1.2} />
        <Tag at={b(0.165)} x={160} y={680} label="Eval corpus alone" color={C.DIM} />
        <T at={b(0.17)} x={160} y={720} size={96} weight={750} style={{ fontVariantNumeric: "tabular-nums" }}>
          {countUp("1,191", b(0.17) + 0.2, frame)}
          <span style={{ fontSize: 36, color: C.DIM, fontWeight: 500 }}>&nbsp; artifacts</span>
        </T>
        <T at={b(0.2)} x={1000} y={720} size={96} weight={750} style={{ fontVariantNumeric: "tabular-nums" }}>
          {countUp("1,786", b(0.2) + 0.2, frame)}
          <span style={{ fontSize: 36, color: C.DIM, fontWeight: 500 }}>&nbsp; links</span>
        </T>
      </Phase>

      {/* B — one strong investigation */}
      <Phase to={OUT - 0.3}>
        <Tag at={INV} x={160} y={290} label="One strong investigation" />
        <T at={INV + 0.3} x={160} y={335} size={52} weight={700} motion={{ dist: 22 }} style={{ whiteSpace: "normal", width: 1600, lineHeight: 1.2 }}>
          Why did Kafka producers in 3.0 and 3.1 stay <span style={{ color: C.AC }}>non-idempotent by default</span>?
        </T>
        {["KIP thread", "Pull request", "Commit"].map((s, i) => {
          const t = b(0.335 + i * 0.02);
          const x = 160 + i * 420;
          return (
            <React.Fragment key={s}>
              <Line at={t - 0.2} x1={W / 2} y1={500} x2={x + 190} y2={580} color={C.AC} width={2.5} dim={0.7} />
              <Box at={t} x={x} y={580} w={380} h={170} outline={C.AC} glow={pop(frame, t + 0.4, 0.8, 18)} motion={{ config: SPRING_ACCENT, dist: 30 }}>
                <div style={{ position: "absolute", left: 30, top: 30, fontSize: 22, letterSpacing: "0.14em", color: C.AC, fontWeight: 700 }}>CLAIM + SOURCE</div>
                <div style={{ position: "absolute", left: 30, top: 72, fontSize: 40, fontWeight: 700 }}>{s}</div>
                <div style={{ position: "absolute", left: 30, top: 124, fontSize: 24, color: C.DIM }}>quote verified ✓</div>
              </Box>
            </React.Fragment>
          );
        })}
        <Line at={b(0.395)} x1={W / 2} y1={500} x2={1450} y2={580} color={C.DIM} width={2.5} dashed />
        <Box at={b(0.4)} x={1420} y={580} w={340} h={170} fill={C.WELL} outline={C.DIM} dashed motion={{ config: SPRING_ACCENT, dist: 30 }}>
          <div style={{ position: "absolute", left: 30, top: 30, fontSize: 22, letterSpacing: "0.14em", color: C.DIM, fontWeight: 700 }}>ONE POINT</div>
          <div style={{ position: "absolute", left: 30, top: 72, fontSize: 40, fontWeight: 700 }}>Unknown</div>
          <div style={{ position: "absolute", left: 30, top: 124, fontSize: 24, color: C.DIM }}>marked honestly</div>
        </Box>
        <Dot at={b(0.33)} x={W / 2} y={500} r={12} pulseAt={every(b(0.36), OUT, 1.4)} />
      </Phase>

      {/* C — intended outcome (not measured) */}
      <Phase to={PROOF - 0.3}>
        <Tag at={OUT} x={160} y={290} label="Intended outcome for the engineer" />
        <T at={OUT + 0.3} x={W / 2} y={470} size={128} weight={800} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 34, windup: 12 }}>
          <Strike p={ramp(frame, b(0.465), 0.6)} color={C.DIM}>
            <span style={{ color: C.DIM }}>Hours</span>
          </Strike>
          {"  →  "}
          <span style={{ color: C.AC, textShadow: glowShadow(ramp(frame, b(0.47), 0.6) * (0.6 + 0.4 * breathe(frame, 2.4))) }}>minutes</span>
        </T>
        <T at={b(0.47)} x={W / 2} y={590} size={36} color={C.FG} anchor="mm">
          digging and tool-hopping → one workbench
        </T>
        {["less time", "less effort", "less context switching"].map((s, i) => (
          <Chip key={s} at={b(0.49 + i * 0.015)} x={W / 2 - 440 + i * 440} y={680} label={s} size={34} motion={{ config: SPRING_ACCENT }} pulseAt={[b(0.53) + i * 0.2]} />
        ))}
        <Chip at={b(0.55)} x={W / 2} y={820} label="not a measured before-and-after yet" size={30} color={C.DIM} outline={C.DIM} dashed motion={{ config: SPRING_ACCENT, dist: 20 }} />
      </Phase>

      {/* D — proof cards + traps + honesty close */}
      <Phase>
        {cards.map((c, i) => {
          const x = CX0 + i * (CW + CG);
          const on = activeCard === i;
          const dim = stage(frame, [[b(0.885), Infinity]], 0.55) * (on || activeCard < i ? 1 : 0.72);
          return (
            <React.Fragment key={c.label}>
              <Box
                at={c.t}
                x={x}
                y={300}
                w={CW}
                h={280}
                outline={on || c.accent ? C.AC : C.LINE}
                glow={on ? 0.5 + 0.35 * breathe(frame, 2) : 0}
                dim={dim}
                motion={{ config: SPRING_ACCENT, dist: 34 }}
                extraScale={pop(frame, c.t + 0.5, 0.05, 16)}
              >
                <div style={{ position: "absolute", left: 34, top: c.size ? 52 : 36, fontSize: c.size ?? 84, fontWeight: 800, color: c.accent ? C.AC : C.FG, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", letterSpacing: "-0.02em" }}>
                  {c.big}
                </div>
                <div style={{ position: "absolute", left: 34, top: 158, fontSize: 30, fontWeight: 650 }}>{c.label}</div>
                <div style={{ position: "absolute", left: 34, top: 206, fontSize: 24, color: C.DIM }}>{c.sub}</div>
              </Box>
              {on ? <Pulse at={c.t + 0.6} x={x + CW - 40} y={340} r={10} period={1.6} /> : null}
            </React.Fragment>
          );
        })}
        <Tag at={b(0.825)} x={160} y={650} label="Traps in the gold set" />
        {["evidence removed", "looks related — but isn’t", "no answer in the data"].map((s, i) => (
          <Chip key={s} at={b(0.835 + i * 0.015)} x={160 + i * 540} y={700} label={s} size={32} center={false} dashed outline={C.DIM} motion={{ config: SPRING_ACCENT }} />
        ))}
        <T at={b(0.9)} x={W / 2} y={880} size={48} weight={700} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 26, windup: 10 }}>
          Accuracy waits on human review — <span style={{ color: C.AC }}>we won’t fake that number.</span>
        </T>
        <Underline at={b(0.92)} x={W / 2} y={930} w={900} />
      </Phase>
    </Scene>
  );
};
