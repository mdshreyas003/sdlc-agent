import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, H, W } from "./theme";
import { draw, easeInOut, easeOut, exit, sec } from "./motion";
import { T, Tag } from "./primitives";

/**
 * Shared scene FX (v4.2 remake). Everything here is relative-timing friendly:
 * scenes call useBeats() and author beats as FRACTIONS of the composition length,
 * so when durations.ts changes after TTS the animation stretches to fill the VO.
 */

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** b(p) → seconds at fraction p of this composition. D = total seconds. */
export function useBeats() {
  const { durationInFrames, fps } = useVideoConfig();
  const D = durationInFrames / fps;
  const b = (p: number) => p * D;
  return { b, D };
}

/** Eased 0→1 ramp starting at atSec over lenSec. */
export function ramp(frame: number, atSec: number, lenSec = 0.6): number {
  return interpolate(frame, [sec(atSec), sec(atSec) + Math.max(1, sec(lenSec))], [0, 1], { ...clamp, easing: easeInOut });
}

/** Continuous 0..1 sine "breathing" — secondary motion through the middle of a scene. */
export function breathe(frame: number, periodSec = 2.4, phase = 0): number {
  return 0.5 + 0.5 * Math.sin((frame / sec(periodSec)) * Math.PI * 2 + phase);
}

/** Times (sec) from a to b every step — feed into pulseAt for rhythmic secondary pops. */
export function every(a: number, b: number, step: number): number[] {
  const out: number[] = [];
  if (step <= 0) return out;
  for (let t = a; t < b; t += step) out.push(t);
  return out;
}

export const glowShadow = (g: number, px = 36) =>
  g > 0 ? `0 0 ${px * g}px rgba(124,180,255,${(0.45 * g).toFixed(3)})` : "none";

/** Typewriter substring. */
export function typed(text: string, frame: number, atSec: number, cps = 28): string {
  const f = frame - sec(atSec);
  if (f <= 0) return "";
  return text.slice(0, Math.min(text.length, Math.floor((f / 30) * cps)));
}

/** Count-up for "1,201" / "445" / "5" style strings (keeps suffix). */
export function countUp(text: string, atSec: number, frame: number, durSec = 1.2): string {
  const m = text.match(/^(\d[\d,]*)(.*)$/);
  if (!m) return text;
  const target = parseInt(m[1].replace(/,/g, ""), 10);
  const v = interpolate(frame - sec(atSec), [0, sec(durSec)], [0, target], { ...clamp, easing: easeOut });
  const n = Math.round(v);
  return (m[1].includes(",") ? n.toLocaleString("en-US") : String(n)) + m[2];
}

/** Dark backdrop with slow-drifting accent light, faint dot grid and a scene-progress hairline. */
export const Ambient: React.FC<{ intensity?: number; hue?: "left" | "right" | "center" }> = ({ intensity = 1, hue = "center" }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const t = frame / 30;
  const bx = (hue === "left" ? 28 : hue === "right" ? 72 : 50) + 8 * Math.sin(t * 0.21);
  const by = 38 + 6 * Math.cos(t * 0.17);
  const cx = 100 - bx + 6 * Math.cos(t * 0.13);
  const prog = frame / Math.max(1, durationInFrames - 1);
  const intro = interpolate(frame, [0, 18], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <AbsoluteFill
        style={{
          opacity: intro * intensity,
          background: `radial-gradient(900px 620px at ${bx}% ${by}%, rgba(124,180,255,0.10), transparent 70%),
            radial-gradient(700px 520px at ${cx}% 92%, rgba(140,120,255,0.06), transparent 70%)`,
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.35 * intro,
          backgroundImage: "radial-gradient(rgba(160,170,188,0.16) 1.2px, transparent 1.4px)",
          backgroundSize: "48px 48px",
          backgroundPosition: `0px ${(-t * 6) % 48}px`,
          maskImage: "radial-gradient(ellipse 75% 70% at 50% 45%, black 30%, transparent 85%)",
          WebkitMaskImage: "radial-gradient(ellipse 75% 70% at 50% 45%, black 30%, transparent 85%)",
        }}
      />
      <div style={{ position: "absolute", left: 0, top: H - 4, width: W * prog, height: 4, background: C.AC, opacity: 0.35 }} />
    </AbsoluteFill>
  );
};

/** Scene-internal page: children author their own entrances; Phase handles the clean exit at `to`. */
export const Phase: React.FC<{ to?: number; children: React.ReactNode; len?: number }> = ({ to, children, len = 0.45 }) => {
  const frame = useCurrentFrame();
  if (to === undefined) return <AbsoluteFill>{children}</AbsoluteFill>;
  const o = exit(frame, to, len);
  if (o.opacity <= 0) return null;
  return <AbsoluteFill style={{ opacity: o.opacity, transform: `translateY(${o.dy}px)` }}>{children}</AbsoluteFill>;
};

/** Consistent header: tag + big title (+ optional dim subline). */
export const Header: React.FC<{ at: number; tag: string; title: React.ReactNode; sub?: React.ReactNode; dim?: number; x?: number }> = ({
  at,
  tag,
  title,
  sub,
  dim,
  x = 140,
}) => (
  <>
    <Tag at={at} x={x} y={78} label={tag} dim={dim} />
    <T at={at + 0.25} x={x} y={116} size={60} weight={700} dim={dim} motion={{ delay: 2, dist: 22 }}>
      {title}
    </T>
    {sub ? (
      <T at={at + 0.6} x={x} y={196} size={30} color={C.DIM} dim={dim} motion={{ delay: 4, dist: 12 }}>
        {sub}
      </T>
    ) : null}
  </>
);

/** Accent underline that draws from centre (or left) then keeps a soft travelling shimmer. */
export const Underline: React.FC<{ at: number; x: number; y: number; w: number; from?: "center" | "left"; h?: number; dur?: number }> = ({
  at,
  x,
  y,
  w,
  from = "center",
  h = 4,
  dur = 0.7,
}) => {
  const frame = useCurrentFrame();
  const p = draw(frame, at, dur);
  if (p <= 0) return null;
  const ww = w * p;
  const left = from === "center" ? x - ww / 2 : x;
  const shimmer = ((frame - sec(at)) / sec(2.2)) % 1;
  return (
    <div
      style={{
        position: "absolute",
        left,
        top: y,
        width: ww,
        height: h,
        borderRadius: h,
        background: `linear-gradient(90deg, ${C.AC} 0%, ${C.AC} ${shimmer * 100 - 12}%, #E6F0FF ${shimmer * 100}%, ${C.AC} ${shimmer * 100 + 12}%, ${C.AC} 100%)`,
        boxShadow: `0 0 18px rgba(124,180,255,0.55)`,
      }}
    />
  );
};

/** Expanding radar rings — continuous "alive" cue around a key node after `at`. */
export const Pulse: React.FC<{ at: number; x: number; y: number; r?: number; period?: number; color?: string; until?: number }> = ({
  at,
  x,
  y,
  r = 40,
  period = 1.8,
  color = C.AC,
  until = Infinity,
}) => {
  const frame = useCurrentFrame();
  const f = frame - sec(at);
  if (f < 0 || frame > sec(until)) return null;
  const rings = [0, 0.5].map((off) => ((f / sec(period) + off) % 1 + 1) % 1);
  return (
    <>
      {rings.map((k, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: x - r * (1 + k),
            top: y - r * (1 + k),
            width: r * 2 * (1 + k),
            height: r * 2 * (1 + k),
            borderRadius: "50%",
            border: `2px solid ${color}`,
            opacity: 0.45 * (1 - k) * Math.min(1, f / 10),
          }}
        />
      ))}
    </>
  );
};

/** Inline highlighter sweep behind text (p 0..1). */
export const Mark: React.FC<{ p: number; children: React.ReactNode; color?: string }> = ({ p, children, color = "rgba(124,180,255,0.30)" }) => (
  <span
    style={{
      backgroundImage: `linear-gradient(${color}, ${color})`,
      backgroundRepeat: "no-repeat",
      backgroundSize: `${Math.max(0, Math.min(1, p)) * 100}% 100%`,
      borderRadius: 6,
      padding: "0 6px",
    }}
  >
    {children}
  </span>
);

/** Inline strike-through that draws across (p 0..1). */
export const Strike: React.FC<{ p: number; children: React.ReactNode; color?: string }> = ({ p, children, color = C.AC }) => (
  <span style={{ position: "relative", display: "inline-block" }}>
    {children}
    <span
      style={{
        position: "absolute",
        left: -6,
        top: "54%",
        height: 6,
        borderRadius: 3,
        width: `calc(${Math.max(0, Math.min(1, p)) * 100}% + ${12 * p}px)`,
        background: color,
        boxShadow: "0 0 14px rgba(124,180,255,0.5)",
      }}
    />
  </span>
);

/** Travelling light along a straight segment (secondary motion on links). */
export const Flow: React.FC<{ at: number; x1: number; y1: number; x2: number; y2: number; period?: number; until?: number; r?: number }> = ({
  at,
  x1,
  y1,
  x2,
  y2,
  period = 1.6,
  until = Infinity,
  r = 6,
}) => {
  const frame = useCurrentFrame();
  const f = frame - sec(at);
  if (f < 0 || frame > sec(until)) return null;
  const k = easeInOut((f / sec(period)) % 1);
  const fadeIn = Math.min(1, f / 10);
  return (
    <div
      style={{
        position: "absolute",
        left: x1 + (x2 - x1) * k - r,
        top: y1 + (y2 - y1) * k - r,
        width: r * 2,
        height: r * 2,
        borderRadius: "50%",
        background: "#E6F0FF",
        boxShadow: "0 0 16px 4px rgba(124,180,255,0.7)",
        opacity: fadeIn * Math.sin(Math.PI * k),
      }}
    />
  );
};
