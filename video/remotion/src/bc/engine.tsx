import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { AVAILABLE_SHOTS } from "./shots";

// Brightcart (BC) scenes: pure black, white bold text, one dim grey. Nothing else.
export const BC_FONT = '"Helvetica Neue", Helvetica, Arial, sans-serif';
export const BC_MONO = 'Menlo, "SF Mono", "Courier New", monospace';
const WHITE = "#FFFFFF";
const DIM = "#9A9A9A";

export type Slide =
  | { k: "big"; lines: string[]; w: number; size?: number; dim?: string[] }
  | { k: "type"; text: string; w: number; sub?: string }
  | { k: "list"; items: string[]; w: number; head?: string; size?: number }
  | { k: "shot"; src: string; cap: string; w: number }
  | { k: "card"; lines: string[]; w: number; head?: string }
  | { k: "stats"; items: Array<[string, string]>; w: number; head?: string };

const clampOpts = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Fade/slide a child in at `at` frames (relative to slide start). */
const Rise: React.FC<{ at: number; children: React.ReactNode; style?: React.CSSProperties }> = ({ at, children, style }) => {
  const f = useCurrentFrame();
  const p = interpolate(f, [at, at + 14], [0, 1], clampOpts);
  return <div style={{ opacity: p, transform: `translateY(${(1 - p) * 26}px)`, ...style }}>{children}</div>;
};

const Text: React.FC<{ size: number; color?: string; mono?: boolean; children: React.ReactNode }> = ({ size, color = WHITE, mono, children }) => (
  <div style={{ fontFamily: mono ? BC_MONO : BC_FONT, fontWeight: 800, fontSize: size, lineHeight: 1.15, color, textAlign: "center", letterSpacing: "-0.01em" }}>{children}</div>
);

const Typed: React.FC<{ text: string; size: number }> = ({ text, size }) => {
  const f = useCurrentFrame();
  const n = Math.floor(interpolate(f, [6, 6 + text.length * 2], [0, text.length], clampOpts));
  const caret = Math.floor(f / 15) % 2 === 0 ? "_" : " ";
  return <Text size={size} mono>{text.slice(0, n)}{caret}</Text>;
};

const Body: React.FC<{ s: Slide; frames: number }> = ({ s, frames }) => {
  const stagger = (n: number) => Math.max(8, Math.min(26, Math.floor((frames * 0.55) / Math.max(1, n))));
  const col = (children: React.ReactNode, gap = 30) => (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap, padding: "0 120px" }}>{children}</AbsoluteFill>
  );
  switch (s.k) {
    case "big": {
      const st = stagger(s.lines.length);
      return col(
        <>
          {s.lines.map((l, i) => (
            <Rise key={i} at={i * st}><Text size={s.size ?? 112}>{l}</Text></Rise>
          ))}
          {(s.dim ?? []).map((l, i) => (
            <Rise key={`d${i}`} at={(s.lines.length + i) * st}><Text size={56} color={DIM}>{l}</Text></Rise>
          ))}
        </>,
        24,
      );
    }
    case "type":
      return col(
        <>
          <Typed text={s.text} size={104} />
          {s.sub ? <Rise at={Math.min(70, Math.floor(frames * 0.5))}><Text size={64} color={DIM}>{s.sub}</Text></Rise> : null}
        </>,
      );
    case "list": {
      const st = stagger(s.items.length);
      return col(
        <>
          {s.head ? <Rise at={0}><Text size={60} color={DIM}>{s.head}</Text></Rise> : null}
          {s.items.map((l, i) => (
            <Rise key={i} at={(i + (s.head ? 1 : 0)) * st}><Text size={s.size ?? 68}>{l}</Text></Rise>
          ))}
        </>,
        22,
      );
    }
    case "shot": {
      return (
        <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 34 }}>
          <Rise at={0}>
            <div style={{ border: `4px solid ${WHITE}`, width: 1500, height: 790, boxSizing: "border-box", padding: 6, background: "#000" }}>
              <Img src={staticFile(`brightcart/${s.src}`)} style={{ width: "100%", height: "100%", objectFit: "contain", objectPosition: "center top" }} />
            </div>
          </Rise>
          <Rise at={10}><Text size={58}>{s.cap}</Text></Rise>
        </AbsoluteFill>
      );
    }
    case "card": {
      const st = stagger(s.lines.length);
      return col(
        <>
          {s.head ? <Rise at={0}><Text size={60} color={DIM}>{s.head}</Text></Rise> : null}
          <div style={{ border: `4px solid ${WHITE}`, padding: "44px 56px", display: "flex", flexDirection: "column", gap: 26, maxWidth: 1620 }}>
            {s.lines.map((l, i) => (
              <Rise key={i} at={(i + 1) * st}>
                <div style={{ fontFamily: BC_MONO, fontWeight: 800, fontSize: 44, color: WHITE, textAlign: "left", lineHeight: 1.2 }}>{l}</div>
              </Rise>
            ))}
          </div>
        </>,
        40,
      );
    }
    case "stats": {
      return col(
        <>
          {s.head ? <Rise at={0}><Text size={70}>{s.head}</Text></Rise> : null}
          <div style={{ display: "flex", gap: 140, marginTop: 20 }}>
            {s.items.map(([big, small], i) => (
              <Rise key={i} at={12 + i * 18}>
                <Text size={170}>{big}</Text>
                <div style={{ height: 14 }} />
                <Text size={54} color={DIM}>{small}</Text>
              </Rise>
            ))}
          </div>
        </>,
        26,
      );
    }
  }
};

/** Plays slides one after another; start of each is set by its weight. Missing screenshots are skipped. */
export const BCScene: React.FC<{ slides: Slide[] }> = ({ slides }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const usable = slides.filter((s) => s.k !== "shot" || AVAILABLE_SHOTS.includes(s.src));
  const total = usable.reduce((a, s) => a + s.w, 0);
  let acc = 0;
  const bounds = usable.map((s) => {
    const start = Math.round((acc / total) * durationInFrames);
    acc += s.w;
    const end = Math.round((acc / total) * durationInFrames);
    return { s, start, end };
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#000", fontFamily: BC_FONT, color: WHITE, overflow: "hidden" }}>
      {bounds.map(({ s, start, end }, i) => {
        if (frame < start || frame >= end) return null;
        const len = end - start;
        const local = frame - start;
        const last = i === bounds.length - 1;
        const fadeOut = last ? 1 : interpolate(local, [len - 8, len], [1, 0], clampOpts);
        const fadeIn = i === 0 ? 1 : interpolate(local, [0, 8], [0, 1], clampOpts);
        return (
          <AbsoluteFill key={i} style={{ opacity: Math.min(fadeIn, fadeOut) }}>
            <Sequence0 offset={start}>
              <Body s={s} frames={len} />
            </Sequence0>
          </AbsoluteFill>
        );
      })}
    </AbsoluteFill>
  );
};

// Re-base useCurrentFrame inside a slide so Rise/Typed timings start at 0.
import { Sequence } from "remotion";
const Sequence0: React.FC<{ offset: number; children: React.ReactNode }> = ({ offset, children }) => (
  <Sequence from={offset} layout="none">{children}</Sequence>
);
