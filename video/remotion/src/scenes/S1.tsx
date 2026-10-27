import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { C, SOURCE_CHATS_LABEL, W } from "../theme";
import { easeInOut, pop, sec, SPRING_ACCENT } from "../motion";
import { Box, Chip, Scene, T, Tag } from "../primitives";
import { Ambient, breathe, glowShadow, Phase, ramp, Underline, useBeats } from "../fx";

/**
 * S1 — The problem we discovered (script.md v4.2)
 * Beats are FRACTIONS of the VO (word-position mapped): hook → code stays / why disappears →
 * hopping Jira · GitHub · discussion chats → wasted time / effort / context switching → lost why is the cost.
 */
const WHYS = ["why is the retry limit three?", "why must this flag stay enabled?", "why was this service never migrated?"];
const TILES: Array<{ label: string; x: number }> = [
  { label: "Jira", x: 420 },
  { label: "GitHub", x: 960 },
  { label: SOURCE_CHATS_LABEL, x: 1500 },
];
const HOP_ORDER = [0, 1, 2, 0, 2, 1, 0, 1, 2, 1, 0, 2, 0, 1, 2, 0, 2, 1, 0, 1];

export const S1: React.FC = () => {
  const frame = useCurrentFrame();
  const { b } = useBeats();

  // Beat map (fractions of VO)
  const P2 = b(0.385); // "The code stays."
  const P3 = b(0.62); // "So they burn hours hopping…"
  const P4 = b(0.82); // "That is wasted time…"

  // --- hopping cursor (secondary motion through the middle) ---
  const hopStart = b(0.66);
  const hopLen = Math.max(0.55, (b(0.8) - hopStart) / 9);
  const hk = (frame / 30 - hopStart) / hopLen;
  const seg = Math.max(0, Math.floor(hk));
  const loc = Math.min(1, Math.max(0, hk - seg));
  const from = TILES[HOP_ORDER[seg % HOP_ORDER.length]];
  const to = TILES[HOP_ORDER[(seg + 1) % HOP_ORDER.length]];
  const e = easeInOut(loc);
  const cx = from.x + (to.x - from.x) * e;
  const cy = 520 - 150 * Math.sin(Math.PI * e);
  const hops = hk > 0 ? seg : 0;
  const tileHits = (j: number) =>
    HOP_ORDER.slice(0, 18)
      .map((ix, n) => (ix === j && n > 0 ? hopStart + n * hopLen : -1))
      .filter((t) => t > 0);

  return (
    <Scene>
      <Ambient />

      {/* 1 — Hook: the person who knew why has left */}
      <Phase to={P2 - 0.3}>
        <T at={b(0.01)} x={W / 2} y={330} size={84} weight={700} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 36, windup: 10 }}>
          “Why is the code <span style={{ color: C.AC, textShadow: glowShadow(ramp(frame, b(0.03), 0.8)) }}>like this</span>?”
        </T>
        <T at={b(0.06)} x={W / 2} y={440} size={38} color={C.DIM} anchor="mm" motion={{ delay: 3 }}>
          The person who knew has left — the answer sits in a two-year-old thread.
        </T>
        <Tag at={b(0.16)} x={W / 2 - 110} y={560} label="Every team has these" color={C.DIM} />
        {WHYS.map((w, i) => (
          <Chip
            key={w}
            at={b(0.19 + i * 0.05)}
            x={W / 2}
            y={620 + i * 100}
            label={<span style={{ fontFamily: "JetBrains Mono" }}>{w}</span>}
            size={30}
            color={C.FG}
            motion={{ arc: i % 2 ? 50 : -50, dist: 30 }}
            pulseAt={[b(0.33) + i * 0.15]}
          />
        ))}
      </Phase>

      {/* 2 — The code stays. The why disappears. */}
      <Phase to={P3 - 0.3}>
        <T at={P2} x={W / 2} y={380} size={104} weight={700} anchor="mm" motion={{ dist: 30, windup: 10 }}>
          The code stays.
        </T>
        <T at={b(0.43)} x={W / 2} y={510} size={104} weight={700} anchor="mm" color={C.AC} motion={{ config: SPRING_ACCENT, dist: 30, windup: 10 }}>
          {"The why disappears.".split("").map((ch, i) => {
            const k = i >= 8 ? ramp(frame, b(0.47) + (i - 8) * 0.07, 0.6) : 0;
            return (
              <span
                key={i}
                style={{
                  display: "inline-block",
                  whiteSpace: "pre",
                  opacity: 1 - 0.82 * k,
                  transform: `translateY(${-18 * k}px)`,
                  filter: `blur(${4 * k}px)`,
                }}
              >
                {ch}
              </span>
            );
          })}
        </T>
        <T at={b(0.46)} x={W / 2} y={640} size={34} color={C.DIM} anchor="mm" motion={{ delay: 4 }}>
          …into old pull requests, tickets and discussion chats
        </T>
        <T at={b(0.5)} x={W / 2} y={760} size={44} weight={600} anchor="mm" motion={{ config: SPRING_ACCENT, dist: 22 }}>
          Code shows <span style={{ color: C.FG }}>what</span>. It never shows <span style={{ color: C.AC, textShadow: glowShadow(ramp(frame, b(0.53), 0.6)) }}>why</span>.
        </T>
      </Phase>

      {/* 3 — Hopping tools to answer one why */}
      <Phase to={P4 - 0.3}>
        <T at={P3} x={W / 2} y={200} size={64} weight={700} anchor="mm" motion={{ dist: 24 }}>
          Hours hopping tools for <span style={{ color: C.AC }}>one</span> why
        </T>
        {TILES.map((tile, j) => (
          <Chip
            key={tile.label}
            at={b(0.635 + j * 0.015)}
            x={tile.x}
            y={560}
            label={tile.label}
            size={44}
            pad={34}
            w={j === 2 ? 440 : 300}
            weight={650}
            motion={{ config: SPRING_ACCENT, dist: 40, arc: (j - 1) * 60 }}
            pulseAt={tileHits(j)}
          />
        ))}
        {hk > 0 && frame < sec(P4) ? (
          <div
            style={{
              position: "absolute",
              left: cx - 16,
              top: cy - 16,
              width: 32,
              height: 32,
              borderRadius: "50%",
              background: C.AC,
              boxShadow: "0 0 26px 6px rgba(124,180,255,0.6)",
              transform: `scale(${1 + 0.25 * Math.sin(Math.PI * loc)}, ${1 - 0.18 * Math.sin(Math.PI * loc)})`,
            }}
          />
        ) : null}
        <T at={b(0.71)} x={W / 2} y={780} size={40} color={C.DIM} anchor="mm" motion={{ delay: 2 }}>
          Reloading context on every switch
        </T>
        <T at={b(0.72)} x={W / 2} y={860} size={34} weight={650} anchor="mm" color={C.AC} mono motion={{ delay: 4 }}>
          tabs in your head: {Math.min(6, 1 + hops)}
        </T>
      </Phase>

      {/* 4 — The cost */}
      <Phase>
        {["Wasted time", "Wasted effort", "Context switching"].map((w, i) => (
          <Box
            key={w}
            at={P4 + i * b(0.018)}
            x={210 + i * 520}
            y={260}
            w={460}
            h={150}
            outline={i === 2 ? C.AC : C.LINE}
            glow={i === 2 ? 0.6 * breathe(frame, 2) : 0}
            motion={{ config: SPRING_ACCENT, dist: 34 }}
            extraScale={pop(frame, P4 + i * b(0.018) + 0.5, 0.05, 16)}
          >
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 42, fontWeight: 650 }}>
              {w}
            </div>
          </Box>
        ))}
        <T at={b(0.885)} x={W / 2} y={560} size={60} weight={600} anchor="mm" motion={{ dist: 24 }}>
          Scattered history is the problem.
        </T>
        <T
          at={b(0.9)}
          x={W / 2}
          y={680}
          size={84}
          weight={750}
          color={C.AC}
          anchor="mm"
          motion={{ config: SPRING_ACCENT, dist: 30, windup: 12 }}
          style={{ textShadow: glowShadow(interpolate(breathe(frame, 2.2), [0, 1], [0.5, 1])) }}
        >
          Lost “why” is the cost.
        </T>
        <Underline at={b(0.92)} x={W / 2} y={745} w={620} />
      </Phase>
    </Scene>
  );
};
