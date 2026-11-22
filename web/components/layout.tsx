"use client";
// Workbench layout state and the small widgets that use it: resizable splitters, collapsed-panel strips, view controls.
// UI only. Sizes and toggles are remembered per browser (localStorage "wb-layout"); nothing here touches data or the API.
//
// Why these choices:
//  - The reading area (code) is the priority, so every side panel can be dragged narrower or collapsed to a strip.
//  - Narrow windows (< 1180px) start with the file tree hidden: three panels beside the code leave no room to read.
//  - The answer panel is capped at 45% of the window so code never drops below a readable width.
//  - A splitter works with the keyboard too (arrows, Shift = bigger steps, Home/End, Enter or double-click = reset).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type KeyboardEvent as RKeyEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import { Icon } from "./icons";

const KEY = "wb-layout";
const NARROW = 1180;
export const LIMITS = { treeW: [180, 420], answerW: [320, 720], evH: [140, 640], codeSize: [11, 18] } as const;

interface Stored { treeW: number; treeOpen: boolean | null; answerW: number; answerOpen: boolean; evH: number; evOpen: boolean; codeSize: number; wrap: boolean }
// Wrap is on by default: a long line should never hide off the right edge of a narrow pane.
export const DEFAULT_SIZES = { treeW: 232, answerW: 380, evH: 260 } as const;
const DEFAULTS: Stored = { ...DEFAULT_SIZES, treeOpen: null, answerOpen: true, evOpen: true, codeSize: 13, wrap: true };
const clamp = (n: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, n));

function load(): Stored {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Stored>;
    const num = (v: unknown, d: number, lim: readonly [number, number]) => (typeof v === "number" && Number.isFinite(v) ? clamp(v, lim) : d);
    const bool = (v: unknown, d: boolean) => (typeof v === "boolean" ? v : d);
    return {
      treeW: num(raw.treeW, DEFAULTS.treeW, LIMITS.treeW), treeOpen: typeof raw.treeOpen === "boolean" ? raw.treeOpen : null,
      answerW: num(raw.answerW, DEFAULTS.answerW, LIMITS.answerW), answerOpen: bool(raw.answerOpen, true),
      evH: num(raw.evH, DEFAULTS.evH, LIMITS.evH), evOpen: bool(raw.evOpen, true),
      codeSize: num(raw.codeSize, DEFAULTS.codeSize, LIMITS.codeSize), wrap: bool(raw.wrap, DEFAULTS.wrap),
    };
  } catch { return DEFAULTS; }
}

interface Layout {
  vw: number;
  focus: boolean; // temporary "code only" mode, never remembered
  treeW: number; answerW: number; evH: number; codeSize: number; wrap: boolean;
  treeVisible: boolean; answerVisible: boolean; evidenceOpen: boolean;
  set: (patch: Partial<Stored>) => void;
  toggleTree: () => void; toggleAnswer: () => void; toggleEvidence: () => void; toggleFocus: () => void; reset: () => void;
}
const Ctx = createContext<Layout | null>(null);
export const useLayout = () => {
  const l = useContext(Ctx);
  if (!l) throw new Error("useLayout outside LayoutProvider");
  return l;
};

export function LayoutProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<Stored>(DEFAULTS);
  const [loaded, setLoaded] = useState(false);
  const [focus, setFocus] = useState(false);
  const [vw, setVw] = useState(1440);
  useEffect(() => { setS(load()); setLoaded(true); }, []);
  useEffect(() => {
    const on = () => setVw(window.innerWidth);
    on();
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  useEffect(() => { if (loaded) try { localStorage.setItem(KEY, JSON.stringify(s)); } catch {} }, [s, loaded]);

  const set = useCallback((patch: Partial<Stored>) => setS((p) => ({ ...p, ...patch })), []);
  const treeOpen = s.treeOpen ?? vw >= NARROW; // no saved choice: auto by window width
  const l = useMemo<Layout>(() => ({
    vw, focus, treeW: s.treeW, answerW: s.answerW, evH: s.evH, codeSize: s.codeSize, wrap: s.wrap,
    treeVisible: treeOpen && !focus, answerVisible: s.answerOpen && !focus, evidenceOpen: s.evOpen && !focus,
    set,
    toggleTree: () => { setFocus(false); set({ treeOpen: !treeOpen }); },
    toggleAnswer: () => { setFocus(false); set({ answerOpen: !s.answerOpen }); },
    toggleEvidence: () => { setFocus(false); set({ evOpen: !s.evOpen }); },
    toggleFocus: () => setFocus((f) => !f),
    reset: () => { setFocus(false); setS(DEFAULTS); },
  }), [vw, focus, s, treeOpen, set]);

  // Shortcuts (ignored while typing): \ files · ] answer · e evidence · z code only
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.isContentEditable || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "\\") l.toggleTree();
      else if (e.key === "]") l.toggleAnswer();
      else if (e.key === "e") l.toggleEvidence();
      else if (e.key === "z") l.toggleFocus();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [l]);

  return <Ctx.Provider value={l}>{children}</Ctx.Provider>;
}

/** A drag handle between two panels. `invert` when the resized panel is to the right of / below the handle. */
export function Splitter({ orientation, value, min, max, onChange, onReset, invert = false, label }: {
  orientation: "vertical" | "horizontal"; // the line's direction: vertical = between left/right panels
  value: number; min: number; max: number; onChange: (v: number) => void; onReset: () => void; invert?: boolean; label: string;
}) {
  const start = useRef<{ p: number; v: number } | null>(null);
  const horiz = orientation === "horizontal";
  const move = (e: RPointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    const d = (horiz ? e.clientY : e.clientX) - start.current.p;
    onChange(Math.round(Math.min(max, Math.max(min, start.current.v + (invert ? -d : d)))));
  };
  const end = (e: RPointerEvent<HTMLDivElement>) => {
    start.current = null;
    document.body.style.userSelect = "";
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };
  const key = (e: RKeyEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 64 : 16;
    const grow = horiz ? (invert ? "ArrowUp" : "ArrowDown") : (invert ? "ArrowLeft" : "ArrowRight");
    const shrink = horiz ? (invert ? "ArrowDown" : "ArrowUp") : (invert ? "ArrowRight" : "ArrowLeft");
    if (e.key === grow) onChange(Math.min(max, value + step));
    else if (e.key === shrink) onChange(Math.max(min, value - step));
    else if (e.key === "Home") onChange(min);
    else if (e.key === "End") onChange(max);
    else if (e.key === "Enter") onReset();
    else return;
    e.preventDefault();
  };
  return (
    <div role="separator" aria-orientation={orientation} aria-label={label} aria-valuenow={value} aria-valuemin={min} aria-valuemax={max}
      tabIndex={0} title={`${label}: drag, or use arrow keys. Double-click resets.`}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); start.current = { p: horiz ? e.clientY : e.clientX, v: value }; document.body.style.userSelect = "none"; }}
      onPointerMove={move} onPointerUp={end} onPointerCancel={end} onDoubleClick={onReset} onKeyDown={key}
      className={`group relative shrink-0 touch-none bg-line outline-none transition-colors hover:bg-accent focus-visible:bg-accent ${horiz ? "h-px w-full cursor-row-resize" : "h-full w-px cursor-col-resize"}`}>
      <span aria-hidden className={`absolute ${horiz ? "inset-x-0 -inset-y-1" : "inset-y-0 -inset-x-1"}`} />
    </div>
  );
}

/** What a collapsed side panel leaves behind: a slim labelled strip that reopens it. */
export function CollapsedStrip({ side, label, hint, onOpen, busy = false }: { side: "left" | "right"; label: string; hint: string; onOpen: () => void; busy?: boolean }) {
  return (
    <button onClick={onOpen} aria-label={`Show ${label.toLowerCase()} (${hint})`} title={`Show ${label.toLowerCase()} (${hint})`}
      className={`relative flex w-8 shrink-0 flex-col items-center gap-3 bg-panel py-3 text-dim hover:bg-hover hover:text-fg ${side === "left" ? "border-r" : "border-l"} border-line`}>
      <Icon name="panel" size={14} />
      <span className="text-[11px] tracking-wide [writing-mode:vertical-rl]">{label}</span>
      {busy && <span aria-hidden className="px-ping absolute bottom-3 h-[7px] w-[7px] rounded-full bg-accent" />}
    </button>
  );
}

/** Code-pane header controls: text size, line wrap, code-only mode, reset. Remembered, never affects the data. */
export function ViewControls() {
  const L = useLayout();
  const btn = "grid h-7 min-w-7 place-items-center rounded-md px-1 text-dim hover:bg-hover hover:text-fg disabled:opacity-30";
  return (
    <div className="flex shrink-0 items-center gap-0.5" role="group" aria-label="View">
      <button onClick={() => L.set({ codeSize: Math.max(LIMITS.codeSize[0], L.codeSize - 1) })} disabled={L.codeSize <= LIMITS.codeSize[0]} aria-label="Smaller code text" title="Smaller code text" className={`${btn} text-[11px]`}>A</button>
      <span className="w-6 text-center font-mono text-[11px] text-dim num" aria-live="polite" title="Code text size">{L.codeSize}</span>
      <button onClick={() => L.set({ codeSize: Math.min(LIMITS.codeSize[1], L.codeSize + 1) })} disabled={L.codeSize >= LIMITS.codeSize[1]} aria-label="Larger code text" title="Larger code text" className={`${btn} text-[15px]`}>A</button>
      <button onClick={() => L.set({ wrap: !L.wrap })} aria-pressed={L.wrap} aria-label="Wrap long lines" title="Wrap long lines" className={`${btn} ml-1 ${L.wrap ? "bg-raised text-fg" : ""}`}><Icon name="wrap" size={14} /></button>
      <button onClick={L.toggleFocus} aria-pressed={L.focus} aria-label="Code only (z)" title="Code only: hide every other panel (z)" className={`${btn} ${L.focus ? "bg-raised text-fg" : ""}`}><Icon name="maximize" size={14} /></button>
      <button onClick={L.reset} aria-label="Reset layout" title="Reset panel sizes and view" className={btn}><Icon name="replay" size={13} /></button>
    </div>
  );
}
