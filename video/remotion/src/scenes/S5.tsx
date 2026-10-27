import React from "react";
import { useCurrentFrame } from "remotion";
import { C, MONO, W } from "../theme";
import { pop, SPRING_ACCENT, stage } from "../motion";
import { Box, Chip, Line, Scene, T } from "../primitives";
import { Ambient, breathe, Flow, glowShadow, Header, Mark, Phase, ramp, Strike, Underline, useBeats } from "../fx";

/**
 * S5 — The difference is in the verification (script.md v4.2)
 * Pipeline: model proposes claims + sources + quotes → ordinary code checks word for word →
 * unsupported claims rejected → "Not established". Close: AI suggests, evidence decides.
 * The two claims are an illustrative walkthrough (labelled), not product data.
 */
const PIPE = ["Model proposes", "Code checks quotes", "Reject unsupported", "“Not established”"];
const NW = 370;
const NG = 46;
const NX0 = (W - (4 * NW + 3 * NG)) / 2;
const NY = 270;

export const S5: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const MAIN = b(0.215);
  const CLOSE = b(0.845);
  const pipeAt = [b(0.29), b(0.38), b(0.53), b(0.715)];
  const now = frame / 30;
  const active = pipeAt.filter((t) => now >= t).length - 1;
  const claim2Dim = stage(frame, [[b(0.56), Infinity]], 0.45);

  return (
    <Scene>
      <Ambient hue="right" />

      {/* A — why a separate layer */}
      <Phase to={MAIN - 0.3}>
        <Header at={0.05} tag="The difference is verification" title="Even good inputs can go wrong" />
        <Box at={b(0.02)} x={160} y={340} w={760} h={300} motion={{ arc: -40 }}>
          <div style={{ position: "absolute", left: 48, top: 46, fontSize: 26, letterSpacing: "0.14em", color: C.DIM, fontWeight: 650 }}>THE GRAPH</div>
          <div style={{ position: "absolute", left: 48, top: 100, fontSize: 48, fontWeight: 700, lineHeight: 1.15 }}>
            can return
            <br />
            incomplete evidence
          </div>
        </Box>
        <Box at={b(0.09)} x={1000} y={340} w={760} h={300} motion={{ arc: 40 }}>
          <div style={{ position: "absolute", left: 48, top: 46, fontSize: 26, letterSpacing: "0.14em", color: C.DIM, fontWeight: 650 }}>THE MODEL</div>
          <div style={{ position: "absolute", left: 48, top: 100, fontSize: 48, fontWeight: 700, lineHeight: 1.15 }}>
            can explain the
            <br />
            right documents wrong
          </div>
        </Box>
        <Chip
          at={b(0.165)}
          x={W / 2}
          y={730}
          label={<>so we added a <b style={{ color: C.AC }}>separate verification layer</b></>}
          size={42}
          pad={34}
          outline={C.AC}
          motion={{ config: SPRING_ACCENT, dist: 30, windup: 10 }}
          pulseAt={[b(0.18)]}
        />
      </Phase>

      {/* B — the pipeline + illustrative walkthrough */}
      <Phase to={CLOSE - 0.3}>
        <Header at={MAIN} tag="The difference is verification" title="The model never grades itself" />
        {PIPE.map((p, i) => {
          const x = NX0 + i * (NW + NG);
          const on = active === i;
          const last = i === 3;
          return (
            <React.Fragment key={p}>
              <Box
                at={pipeAt[i]}
                x={x}
                y={NY}
                w={NW}
                h={100}
                outline={on || (last && active === 3) ? C.AC : C.LINE}
                glow={on ? 0.55 + 0.35 * breathe(frame, 1.8) : 0}
                dim={active > i && !last ? 0.6 : 1}
                motion={{ config: SPRING_ACCENT, dist: 26 }}
              >
                <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 30, fontWeight: 650, color: last ? C.AC : C.FG }}>
                  {p}
                </div>
              </Box>
              {i > 0 ? (
                <>
                  <Line at={pipeAt[i] - 0.25} x1={x - NG + 4} y1={NY + 50} x2={x - 6} y2={NY + 50} color={C.AC} width={3} arrow />
                  <Flow at={pipeAt[i] + 0.4} x1={x - NG + 4} y1={NY + 50} x2={x - 6} y2={NY + 50} period={1.3} />
                </>
              ) : null}
            </React.Fragment>
          );
        })}
        <T at={b(0.3)} x={160} y={420} size={20} color={C.DIM} weight={650} style={{ letterSpacing: "0.14em" }}>
          ILLUSTRATIVE WALKTHROUGH
        </T>

        {/* Claim 1 — supported */}
        <Box
          at={b(0.3)}
          x={160}
          y={460}
          w={760}
          h={170}
          outline={now >= b(0.445) ? C.AC : C.LINE}
          glow={ramp(frame, b(0.445), 0.5) * 0.5}
          motion={{ arc: -30 }}
          extraScale={pop(frame, b(0.445), 0.04, 16)}
        >
          <div style={{ position: "absolute", left: 32, top: 24, fontSize: 32, fontWeight: 650 }}>Claim: retry limit is three</div>
          <div style={{ position: "absolute", left: 32, top: 80, fontFamily: MONO, fontSize: 26, color: C.AC }}>“cap retries at three”</div>
          <div style={{ position: "absolute", left: 32, top: 124, fontSize: 22, color: C.DIM }}>source: pull request</div>
          <div style={{ position: "absolute", right: 30, top: 54, fontSize: 56, color: C.AC, fontWeight: 800, opacity: ramp(frame, b(0.445), 0.3), transform: `scale(${0.6 + 0.4 * ramp(frame, b(0.445), 0.3) + pop(frame, b(0.45), 0.3, 14)})` }}>
            ✓
          </div>
        </Box>

        {/* Claim 2 — unsupported */}
        <Box at={b(0.315)} x={160} y={660} w={760} h={170} dim={claim2Dim} motion={{ arc: -30 }}>
          <div style={{ position: "absolute", left: 32, top: 24, fontSize: 32, fontWeight: 650 }}>
            <Strike p={ramp(frame, b(0.555), 0.6)} color={C.DIM}>
              Claim: flag required by audit
            </Strike>
          </div>
          <div style={{ position: "absolute", left: 32, top: 80, fontFamily: MONO, fontSize: 26, color: C.DIM }}>“mandated by the audit team”</div>
          <div style={{ position: "absolute", left: 32, top: 124, fontSize: 22, color: C.DIM }}>source: ticket</div>
        </Box>
        <Chip
          at={b(0.565)}
          x={810}
          y={720}
          label="✕ rejected"
          size={28}
          pad={18}
          color={C.AC}
          outline={C.AC}
          motion={{ config: SPRING_ACCENT, dist: 0, squash: 0.1 }}
        />

        {/* Source panel — ordinary code checks word for word */}
        <Box at={b(0.385)} x={1000} y={460} w={760} h={370} fill={C.INSET} motion={{ arc: 40 }}>
          <div style={{ position: "absolute", left: 32, top: 26, fontSize: 20, letterSpacing: "0.14em", color: C.DIM, fontWeight: 650 }}>ACTUAL SOURCE TEXT</div>
          <div style={{ position: "absolute", left: 32, top: 76, right: 32, fontFamily: MONO, fontSize: 26, lineHeight: 1.7, color: C.DIM, whiteSpace: "normal" }}>
            After the outage we decided to <Mark p={ramp(frame, b(0.405), 1.4)}><span style={{ color: C.FG }}>cap retries at three</span></Mark> so a stuck broker cannot
            flood the cluster.
          </div>
          <div style={{ position: "absolute", left: 32, bottom: 30, fontSize: 24, color: C.FG, fontWeight: 600, opacity: ramp(frame, b(0.43), 0.4) }}>
            <span style={{ color: C.AC }}>●</span> exact string match — plain code, not a model
          </div>
          <div style={{ position: "absolute", left: 32, bottom: 72, fontSize: 24, color: C.DIM, opacity: ramp(frame, b(0.54), 0.4) }}>
            “mandated by the audit team” → no match
          </div>
        </Box>
        <Line at={b(0.42)} x1={600} y1={555} x2={1000} y2={600} color={C.AC} width={2.5} dashed bend={-30} />

        <T at={b(0.62)} x={160} y={858} size={30} weight={600} motion={{ config: SPRING_ACCENT }} style={{ whiteSpace: "normal", width: 780, lineHeight: 1.3 }}>
          The model does not get to declare its own answer correct.
        </T>
        <Box
          at={b(0.725)}
          x={1000}
          y={855}
          w={760}
          h={86}
          outline={C.AC}
          glow={ramp(frame, b(0.73), 0.5) * (0.7 + 0.3 * breathe(frame, 1.6))}
          motion={{ config: SPRING_ACCENT, dist: 20, windup: 8 }}
          extraScale={pop(frame, b(0.725) + 0.45, 0.06, 16)}
        >
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32, fontWeight: 650 }}>
            Thin evidence →&nbsp;<span style={{ color: C.AC, fontWeight: 750 }}>“Not established”</span>
          </div>
        </Box>
      </Phase>

      {/* C — close */}
      <Phase>
        <T at={CLOSE + 0.1} x={W / 2} y={380} size={120} weight={750} anchor="mm" motion={{ dist: 34, windup: 12 }}>
          AI suggests.
        </T>
        <T
          at={b(0.885)}
          x={W / 2}
          y={540}
          size={120}
          weight={750}
          color={C.AC}
          anchor="mm"
          motion={{ config: SPRING_ACCENT, dist: 34, windup: 12 }}
          style={{ textShadow: glowShadow(0.5 + 0.5 * breathe(frame, 2.2)) }}
        >
          Evidence decides.
        </T>
        <Underline at={b(0.9)} x={W / 2} y={620} w={820} h={5} />
        <T at={b(0.915)} x={W / 2} y={720} size={36} color={C.DIM} anchor="mm" extraScale={pop(frame, b(0.94), 0.04, 16)}>
          what we are allowed to claim
        </T>
      </Phase>
    </Scene>
  );
};
