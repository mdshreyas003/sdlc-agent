import React from "react";
import { useCurrentFrame } from "remotion";
import { C, MONO, W } from "../theme";
import { pop, SPRING_ACCENT, stage } from "../motion";
import { Box, Chip, Line, Scene, T } from "../primitives";
import { Ambient, breathe, every, Flow, glowShadow, Header, Mark, Phase, ramp, Strike, Underline, useBeats } from "../fx";

/**
 * S2 — How we headed toward a solution (script.md v4.2)
 * Not another chatbot → what makes a why-answer trustworthy? → (1) explicit links only, no guessing
 * → (2) word-for-word quotes checked by plain code → "Not established" when proof is missing.
 */
const RELS: Array<[string, string, string]> = [
  ["Reply", "REPLIES_TO", "Thread"],
  ["Message", "REFERENCES", "Ticket"],
  ["Pull request", "CONTAINS", "Commit"],
];

export const S2: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();
  const RULES = b(0.195);
  const R2 = b(0.6);
  const CLOSE = b(0.885);
  const leftDim = stage(frame, [[R2, Infinity]], 0.5);

  return (
    <Scene>
      <Ambient hue="left" />

      {/* A — Not another chatbot */}
      <Phase to={RULES - 0.3}>
        <T at={b(0.01)} x={W / 2} y={330} size={120} weight={750} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 36, windup: 12 }}>
          Not another <Strike p={ramp(frame, b(0.05), 0.5)}>chatbot</Strike>.
        </T>
        <T at={b(0.105)} x={W / 2} y={520} size={40} color={C.DIM} anchor="mm" motion={{ delay: 2 }}>
          We asked one question first:
        </T>
        <T at={b(0.12)} x={W / 2} y={610} size={60} weight={650} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 24 }}>
          What makes a why-answer <Mark p={ramp(frame, b(0.15), 0.8)}>trustworthy</Mark>?
        </T>
      </Phase>

      {/* B — Two rules */}
      <Phase to={CLOSE - 0.3}>
        <Header at={RULES} tag="Our direction" title="Two rules for a trustworthy why" />

        {/* Rule 1 */}
        <Box at={RULES + 0.3} x={140} y={270} w={800} h={640} dim={leftDim} motion={{ arc: -40, dist: 30 }} />
        <T at={RULES + 0.5} x={190} y={305} size={26} weight={700} color={C.AC} dim={leftDim} mono>
          01
        </T>
        <T at={RULES + 0.6} x={250} y={296} size={44} weight={700} dim={leftDim} motion={{ delay: 2 }}>
          Explicit links only
        </T>
        <T at={RULES + 0.9} x={190} y={364} size={28} color={C.DIM} dim={leftDim} motion={{ delay: 3 }}>
          links people already wrote down
        </T>
        {RELS.map(([a, edge, z], i) => {
          const t = b(0.3 + i * 0.075);
          const y = 440 + i * 112;
          return (
            <React.Fragment key={edge}>
              <Chip at={t} x={190} y={y} label={a} size={26} pad={18} w={200} center={false} dim={leftDim} motion={{ arc: -30 }} />
              <Line at={t + 0.25} x1={404} y1={y + 26} x2={596} y2={y + 26} color={C.AC} width={3} arrow dim={leftDim} />
              <Flow at={t + 0.9} x1={404} y1={y + 26} x2={596} y2={y + 26} period={1.4 + i * 0.2} until={R2} />
              <T
                at={t + 0.35}
                x={500}
                y={y - 12}
                size={20}
                weight={700}
                mono
                color={C.AC}
                anchor="mm"
                dim={leftDim}
                extraScale={pop(frame, t + 0.6, 0.12, 14)}
                motion={{ config: SPRING_ACCENT, dist: 10 }}
              >
                {edge}
              </T>
              <Chip at={t + 0.45} x={612} y={y} label={z} size={26} pad={18} w={200} center={false} dim={leftDim} motion={{ arc: 30 }} />
            </React.Fragment>
          );
        })}
        <T at={b(0.545)} x={190} y={790} size={36} weight={650} dim={leftDim} motion={{ config: SPRING_ACCENT }}>
          No guessed edges
        </T>
        <Line at={b(0.555)} x1={560} y1={812} x2={800} y2={812} dashed color={C.DIM} width={3} dim={leftDim} />
        <T
          at={b(0.57)}
          x={680}
          y={812}
          size={56}
          weight={800}
          color={C.AC}
          anchor="mm"
          dim={leftDim}
          motion={{ config: SPRING_ACCENT, dist: 0, squash: 0.12 }}
          extraScale={pop(frame, b(0.57) + 0.3, 0.25, 14)}
        >
          ✕
        </T>

        {/* Rule 2 */}
        <Box at={R2} x={980} y={270} w={800} h={640} outline={C.AC} glow={0.35 + 0.25 * breathe(frame, 2.6)} motion={{ arc: 40, dist: 30, config: SPRING_ACCENT }} />
        <T at={R2 + 0.2} x={1030} y={305} size={26} weight={700} color={C.AC} mono>
          02
        </T>
        <T at={R2 + 0.3} x={1090} y={296} size={44} weight={700} motion={{ delay: 2 }}>
          Every claim carries a quote
        </T>
        <T at={b(0.7)} x={1030} y={364} size={28} color={C.DIM} motion={{ delay: 3 }}>
          word for word — checked by plain code
        </T>
        <Box at={b(0.635)} x={1030} y={430} w={700} h={150} fill={C.INSET} motion={{ dist: 18 }}>
          <div style={{ position: "absolute", left: 28, top: 22, fontSize: 18, letterSpacing: "0.14em", color: C.DIM, fontWeight: 650 }}>QUOTE</div>
          <div style={{ position: "absolute", left: 28, top: 62, fontFamily: MONO, fontSize: 30, color: C.FG, whiteSpace: "nowrap" }}>
            “<Mark p={ramp(frame, b(0.68), 1.2)}>cap retries at three</Mark>”
          </div>
        </Box>
        <T at={b(0.715)} x={1030} y={612} size={32} weight={600} motion={{ config: SPRING_ACCENT }}>
          <span style={{ color: C.AC }}>✓</span>&nbsp; found in the source, word for word
        </T>
        <T at={b(0.755)} x={1030} y={700} size={32} color={C.DIM}>
          Proof missing? The system says
        </T>
        <Box
          at={b(0.77)}
          x={1030}
          y={758}
          w={700}
          h={110}
          outline={C.AC}
          glow={ramp(frame, b(0.78), 0.6) * (0.7 + 0.3 * breathe(frame, 1.8))}
          motion={{ config: SPRING_ACCENT, dist: 24, windup: 10 }}
          extraScale={pop(frame, b(0.77) + 0.5, 0.06, 16)}
        >
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 50, fontWeight: 750, color: C.AC }}>
            “Not established”
          </div>
        </Box>
      </Phase>

      {/* C — close */}
      <Phase>
        <T at={CLOSE} x={W / 2} y={460} size={76} weight={700} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 30, windup: 10 }}>
          That direction shaped <span style={{ color: C.AC, textShadow: glowShadow(ramp(frame, CLOSE + 0.6, 0.8)) }}>every MVP</span>.
        </T>
        <Underline at={b(0.91)} x={W / 2} y={530} w={760} />
        {[0, 1, 2].map((i) => (
          <Chip
            key={i}
            at={b(0.905) + i * 0.15}
            x={W / 2 - 260 + i * 260}
            y={620}
            label={`MVP ${i + 1}`}
            size={30}
            color={C.AC}
            outline={C.AC}
            pulseAt={every(b(0.93) + i * 0.2, b(1), 1.2)}
          />
        ))}
      </Phase>
    </Scene>
  );
};
