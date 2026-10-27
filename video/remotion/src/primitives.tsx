import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C, MONO, SANS } from "./theme";
import { draw, enter, EnterOpts, pop, sec, SPRING_ACCENT } from "./motion";

type Anchor = "la" | "mm" | "lm";
const anchorTf: Record<Anchor, string> = {
  la: "none",
  mm: "translate(-50%, -50%)",
  lm: "translate(0, -50%)",
};

export const Scene: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ backgroundColor: C.BG, fontFamily: SANS, color: C.FG, overflow: "hidden" }}>
    {children}
  </AbsoluteFill>
);

/** Positions at (x, y) with a Pillow-like anchor, then runs the shared entrance on an inner layer. */
const Placed: React.FC<{
  x: number;
  y: number;
  anchor?: Anchor;
  at: number;
  motion?: EnterOpts;
  dim?: number;
  extraScale?: number;
  origin?: string;
  children: React.ReactNode;
}> = ({ x, y, anchor = "la", at, motion, dim = 1, extraScale = 0, origin = "50% 50%", children }) => {
  const frame = useCurrentFrame();
  const e = enter(frame, at, motion);
  if (!e.visible) return null;
  return (
    <div style={{ position: "absolute", left: x, top: y, transform: anchorTf[anchor] }}>
      <div
        style={{
          opacity: e.opacity * dim,
          transform: `${e.transform} scale(${1 + extraScale})`,
          transformOrigin: origin,
          willChange: "transform, opacity",
        }}
      >
        {children}
      </div>
    </div>
  );
};

export const T: React.FC<{
  at: number;
  x: number;
  y: number;
  children: React.ReactNode;
  size?: number;
  weight?: number;
  color?: string;
  anchor?: Anchor;
  mono?: boolean;
  motion?: EnterOpts;
  dim?: number;
  extraScale?: number;
  style?: React.CSSProperties;
}> = ({ at, x, y, children, size = 48, weight = 500, color = C.FG, anchor = "la", mono, motion, dim, extraScale, style }) => (
  <Placed x={x} y={y} anchor={anchor} at={at} motion={{ squash: 0.02, ...motion }} dim={dim} extraScale={extraScale}>
    <div
      style={{
        fontFamily: mono ? MONO : SANS,
        fontSize: size,
        fontWeight: weight,
        color,
        lineHeight: 1.15,
        whiteSpace: "nowrap",
        letterSpacing: size >= 80 ? "-0.02em" : size >= 40 ? "-0.01em" : 0,
        fontVariationSettings: mono ? undefined : `"opsz" ${Math.min(32, Math.max(14, size))}`,
        ...style,
      }}
    >
      {children}
    </div>
  </Placed>
);

/** Uppercase section tag (render.py `tag`). */
export const Tag: React.FC<{ at: number; x: number; y: number; label: string; color?: string; dim?: number }> = ({
  at,
  x,
  y,
  label,
  color = C.AC,
  dim,
}) => (
  <T at={at} x={x} y={y} size={24} weight={650} color={color} dim={dim} motion={{ dist: 14, arc: -18 }} style={{ letterSpacing: "0.14em" }}>
    {label.toUpperCase()}
  </T>
);

export const Box: React.FC<{
  at: number;
  x: number;
  y: number;
  w: number;
  h: number;
  fill?: string;
  outline?: string;
  dashed?: boolean;
  r?: number;
  width?: number;
  motion?: EnterOpts;
  dim?: number;
  glow?: number; // 0..1 accent glow (exaggeration on proof moments)
  extraScale?: number;
  children?: React.ReactNode;
}> = ({ at, x, y, w, h, fill = C.CARD, outline = C.LINE, dashed, r = 18, width = 2, motion, dim, glow = 0, extraScale, children }) => (
  <Placed x={x} y={y} at={at} motion={{ squash: 0.03, dist: 30, ...motion }} dim={dim} extraScale={extraScale}>
    <div
      style={{
        position: "relative",
        width: w,
        height: h,
        borderRadius: r,
        background: fill,
        border: `${width}px ${dashed ? "dashed" : "solid"} ${outline}`,
        boxSizing: "border-box",
        boxShadow: glow > 0 ? `0 0 ${40 * glow}px ${6 * glow}px rgba(110,168,254,${0.22 * glow})` : undefined,
      }}
    >
      {children}
    </div>
  </Placed>
);

/** Pill chip, centered on x (render.py `chip`). `pulseAt` = secondary-action pops. */
export const Chip: React.FC<{
  at: number;
  x: number;
  y: number;
  label: React.ReactNode;
  color?: string;
  size?: number;
  pad?: number;
  fill?: string;
  outline?: string;
  dashed?: boolean;
  center?: boolean;
  w?: number;
  motion?: EnterOpts;
  dim?: number;
  pulseAt?: number[];
  weight?: number;
}> = ({ at, x, y, label, color = C.FG, size = 34, pad = 26, fill = C.CARD, outline = C.LINE, dashed, center = true, w, motion, dim, pulseAt = [], weight = 500 }) => {
  const frame = useCurrentFrame();
  const extra = pulseAt.reduce((acc, t) => acc + pop(frame, t, 0.07), 0);
  const h = size + pad * 1.4;
  return (
    <Placed x={x} y={y} at={at} anchor="la" motion={{ squash: 0.05, ...motion }} dim={dim} extraScale={extra}>
      <div
        style={{
          transform: center ? "translateX(-50%)" : undefined,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          height: h,
          width: w,
          padding: w ? 0 : `0 ${pad}px`,
          borderRadius: w ? 16 : h / 2,
          background: fill,
          border: `2px ${dashed ? "dashed" : "solid"} ${outline}`,
          boxSizing: "border-box",
          fontSize: size,
          fontWeight: weight,
          color,
          whiteSpace: "nowrap",
          letterSpacing: size <= 26 ? "0.08em" : "-0.005em",
        }}
      >
        {label}
      </div>
    </Placed>
  );
};

/** Stroke that draws itself (eased), optional arrowhead that pops on arrival. */
export const Line: React.FC<{
  at: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color?: string;
  width?: number;
  arrow?: boolean;
  dashed?: boolean;
  dur?: number;
  dim?: number;
  /** bow the line into a gentle arc (px of sag at midpoint) */
  bend?: number;
}> = ({ at, x1, y1, x2, y2, color = C.LINE, width = 3, arrow, dashed, dur = 0.6, dim = 1, bend = 0 }) => {
  const frame = useCurrentFrame();
  const p = draw(frame, at, dur);
  if (p <= 0) return null;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const len = Math.hypot(x2 - x1, y2 - y1) || 1;
  const nx = -(y2 - y1) / len;
  const ny = (x2 - x1) / len;
  const cx = mx + nx * bend;
  const cy = my + ny * bend;
  const d = `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
  const pathLen = len * (1 + (bend ? 0.1 : 0));
  // Arrowhead: tangent at end of quadratic = (P2 - C)
  const ang = Math.atan2(y2 - cy, x2 - cx);
  const s = 14;
  const af = frame - sec(at) - Math.round(sec(dur) * 0.85);
  const arrowP = af < 0 ? 0 : Math.min(1.15, enter(frame, at, { delay: Math.round(sec(dur) * 0.85), config: SPRING_ACCENT, dist: 0, windup: 0 }).progress);
  return (
    <svg style={{ position: "absolute", left: 0, top: 0, opacity: dim }} width={1920} height={1080}>
      {dashed ? (
        <>
          <defs>
            <mask id={`m-${x1}-${y1}-${x2}-${y2}`}>
              <path d={d} stroke="white" strokeWidth={width + 4} fill="none" strokeDasharray={pathLen} strokeDashoffset={pathLen * (1 - p)} />
            </mask>
          </defs>
          <path d={d} stroke={color} strokeWidth={width} fill="none" strokeDasharray="10 10" mask={`url(#m-${x1}-${y1}-${x2}-${y2})`} />
        </>
      ) : (
        <path d={d} stroke={color} strokeWidth={width} fill="none" strokeLinecap="round" strokeDasharray={pathLen} strokeDashoffset={pathLen * (1 - p)} />
      )}
      {arrow && arrowP > 0 ? (
        <polygon
          transform={`translate(${x2} ${y2}) scale(${arrowP}) translate(${-x2} ${-y2})`}
          points={`${x2},${y2} ${x2 - s * Math.cos(ang - 0.45)},${y2 - s * Math.sin(ang - 0.45)} ${x2 - s * Math.cos(ang + 0.45)},${y2 - s * Math.sin(ang + 0.45)}`}
          fill={color}
        />
      ) : null}
    </svg>
  );
};

/** Graph node dot — exaggerated spring pop + squash (render.py `dot`). */
export const Dot: React.FC<{ at: number; x: number; y: number; r?: number; color?: string; dim?: number; pulseAt?: number[] }> = ({
  at,
  x,
  y,
  r = 16,
  color = C.AC,
  dim = 1,
  pulseAt = [],
}) => {
  const frame = useCurrentFrame();
  const e = enter(frame, at, { config: SPRING_ACCENT, dist: 0, windup: 0, squash: 0.12 });
  if (!e.visible) return null;
  const extra = pulseAt.reduce((acc, t) => acc + pop(frame, t, 0.35, 16), 0);
  const sc = Math.max(0, e.progress) * (1 + extra);
  return (
    <div
      style={{
        position: "absolute",
        left: x - r,
        top: y - r,
        width: r * 2,
        height: r * 2,
        borderRadius: "50%",
        background: color,
        opacity: e.opacity * dim,
        transform: `${e.transform} scale(${sc})`,
        boxShadow: `0 0 ${18 + 30 * extra}px rgba(110,168,254,${0.35 + extra})`,
      }}
    />
  );
};
