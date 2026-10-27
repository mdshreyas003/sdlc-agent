import { Easing, interpolate, spring } from "remotion";
import { FPS } from "./theme";

/**
 * Shared motion vocabulary for every scene (README §3 "Twelve principles").
 * All timing is authored in SECONDS on narration beats (pose-to-pose, #4) and converted here.
 * Nothing is linear: springs for travel, cubic/sine easing for fades (#6 slow in / slow out).
 */

export const sec = (s: number) => Math.round(s * FPS);

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const easeOut = Easing.out(Easing.cubic);
export const easeInOut = Easing.inOut(Easing.cubic);
export const easeSine = Easing.inOut(Easing.sin);

/** Main travel spring — slight overshoot so things land with weight. */
export const SPRING_MAIN = { damping: 13, stiffness: 140, mass: 0.9 };
/** Softer, later spring for labels that follow a box (#5 follow-through). */
export const SPRING_FOLLOW = { damping: 16, stiffness: 110, mass: 1 };
/** Snappy, bigger overshoot for accent moments (#10 exaggeration). */
export const SPRING_ACCENT = { damping: 9, stiffness: 170, mass: 0.8 };

export type EnterOpts = {
  /** extra frames after `at` (use for follow-through: labels ~3-5f after their box) */
  delay?: number;
  /** vertical travel in px (enters from below) */
  dist?: number;
  /** horizontal offset at start; travels on a curve (#7 arcs) because x eases quadratically vs y */
  arc?: number;
  /** anticipation wind-up in px, opposite to travel (#2) */
  windup?: number;
  /** squash amount on land, e.g. 0.04 (#1) */
  squash?: number;
  config?: typeof SPRING_MAIN;
  /** fade length in frames */
  fade?: number;
};

export type EnterState = {
  visible: boolean;
  opacity: number;
  progress: number; // spring value (can overshoot 1)
  transform: string;
  f: number; // frames since start
};

export function enter(frame: number, atSec: number, o: EnterOpts = {}): EnterState {
  const {
    delay = 0,
    dist = 26,
    arc = 0,
    windup = 7,
    squash = 0.035,
    config = SPRING_MAIN,
    fade = 11,
  } = o;
  const f = frame - sec(atSec) - delay;
  if (f < 0) return { visible: false, opacity: 0, progress: 0, transform: "none", f };

  // Anticipation: a short dip further away from the destination before the spring takes over.
  const wind = interpolate(f, [0, 4, 9], [0, 1, 0], { ...clamp, easing: easeSine }) * windup;
  const p = spring({ frame: Math.max(0, f - 3), fps: FPS, config });
  const rest = 1 - p;
  const ty = dist * rest + wind;
  const tx = arc * Math.sign(rest) * rest * rest; // quadratic in x vs linear in y => curved path

  // Squash & stretch on land: wide+short at contact, then recover.
  const land = interpolate(f, [9, 13, 22], [0, 1, 0], { ...clamp, easing: easeSine });
  const sx = 1 + squash * land;
  const sy = 1 - squash * land;

  const opacity = interpolate(f, [0, fade], [0, 1], { ...clamp, easing: easeOut });
  return {
    visible: true,
    opacity,
    progress: p,
    f,
    transform: `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`,
  };
}

/** 0→1 eased draw progress for lines/strokes (slow in/out). */
export function draw(frame: number, atSec: number, durSec = 0.6, delay = 0): number {
  const f = frame - sec(atSec) - delay;
  return interpolate(f, [0, sec(durSec)], [0, 1], { ...clamp, easing: easeInOut });
}

/**
 * Staging (#3): returns an opacity multiplier that pushes an element back while another beat
 * has focus. windows = [[fromSec, toSec], ...] (toSec = Infinity for "rest of scene").
 */
export function stage(frame: number, windows: Array<[number, number]>, level = 0.42): number {
  let m = 1;
  for (const [a, b] of windows) {
    const v = Number.isFinite(b)
      ? interpolate(frame, [sec(a), sec(a) + 12, sec(b), sec(b) + 12], [1, level, level, 1], { ...clamp, easing: easeInOut })
      : interpolate(frame, [sec(a), sec(a) + 12], [1, level], { ...clamp, easing: easeInOut });
    m = Math.min(m, v);
  }
  return m;
}

/** Secondary action (#8): a single soft scale pop (returns extra scale, e.g. 0..amt). */
export function pop(frame: number, atSec: number, amt = 0.06, lenFrames = 14): number {
  const f = frame - sec(atSec);
  return interpolate(f, [0, lenFrames * 0.35, lenFrames], [0, amt, 0], { ...clamp, easing: easeSine });
}

/** Clean exit (used for scene-internal clears): 1 → 0 with ease-in, slight drop. */
export function exit(frame: number, atSec: number, lenSec = 0.45) {
  const f = frame - sec(atSec);
  const t = interpolate(f, [0, sec(lenSec)], [0, 1], { ...clamp, easing: Easing.in(Easing.cubic) });
  return { opacity: 1 - t, dy: -14 * t };
}
