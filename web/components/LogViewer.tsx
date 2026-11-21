"use client";
// Structured run log: level + stream + text filters, copy, and auto-follow while the run is live.
import { useEffect, useMemo, useRef, useState } from "react";
import type { LogLine } from "@/lib/types";
import { Icon } from "./icons";
import { Notice, btnGhost, field } from "./ui";

const LEVELS = ["all", "info", "warn", "error"] as const;
type Level = (typeof LEVELS)[number];
const COLOR = { info: "text-dim", warn: "text-warn", error: "text-bad" } as const;
const hms = (ts: string) => (/T(\d\d:\d\d:\d\d)/.exec(ts)?.[1] ?? ts);

export default function LogViewer({ lines, live = false, height = 280 }: { lines: LogLine[]; live?: boolean; height?: number }) {
  const [level, setLevel] = useState<Level>("all");
  const [stream, setStream] = useState("");
  const [q, setQ] = useState("");
  const [follow, setFollow] = useState(true);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const streams = useMemo(() => [...new Set(lines.map((l) => l.stream).filter((s): s is string => !!s))], [lines]);
  const counts = useMemo(() => ({ warn: lines.filter((l) => l.level === "warn").length, error: lines.filter((l) => l.level === "error").length }), [lines]);
  const shown = useMemo(() => {
    const s = q.trim().toLowerCase();
    return lines.filter((l) => (level === "all" || l.level === level) && (!stream || l.stream === stream) && (!s || l.message.toLowerCase().includes(s)));
  }, [lines, level, stream, q]);

  // follow the tail while live; scrolling up pauses it, scrolling back to the bottom resumes
  useEffect(() => { if (live && follow && box.current) box.current.scrollTop = box.current.scrollHeight; }, [shown, live, follow]);
  const onScroll = () => {
    const el = box.current;
    if (!el || !live) return;
    setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
  };

  const copy = async () => {
    const text = shown.map((l) => `${l.ts} ${l.level.toUpperCase().padEnd(5)} ${l.stream ? `[${l.stream}] ` : ""}${l.message}`).join("\n");
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };

  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <div role="radiogroup" aria-label="Level" className="flex gap-0.5 rounded-md border border-line p-0.5">
          {LEVELS.map((l) => (
            <button key={l} role="radio" aria-checked={level === l} onClick={() => setLevel(l)}
              className={`rounded px-2 py-0.5 font-mono text-[11px] ${level === l ? "bg-raised text-fg" : "text-dim hover:text-fg"}`}>
              {l}{l === "warn" && counts.warn > 0 ? ` ${counts.warn}` : l === "error" && counts.error > 0 ? ` ${counts.error}` : ""}
            </button>
          ))}
        </div>
        {streams.length > 0 && (
          <select value={stream} onChange={(e) => setStream(e.target.value)} aria-label="Stream" className={`${field} h-7 max-w-[200px] flex-none font-sans text-[11.5px]`}>
            <option value="">all streams</option>
            {streams.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter text…" aria-label="Filter log text" className={`${field} h-7 min-w-[120px] flex-1 text-[11.5px]`} />
        {live && (
          <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-dim">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} className="accent-[var(--accent)]" />follow
          </label>
        )}
        <button type="button" onClick={copy} className={`${btnGhost} h-7 px-2 text-[11.5px]`}><Icon name={copied ? "check" : "copy"} size={12} />{copied ? "Copied" : "Copy"}</button>
      </div>
      <div ref={box} onScroll={onScroll} style={{ height }} className="overflow-auto px-3 py-2 font-mono text-[11.5px] leading-[1.75]" role="log" aria-live={live ? "polite" : "off"}>
        {lines.length === 0 && <p className="text-dim">No log lines yet.</p>}
        {lines.length > 0 && shown.length === 0 && <Notice tone="dim">Nothing matches these filters.</Notice>}
        {shown.map((l, i) => (
          <div key={`${l.ts}-${i}`} className="flex gap-3 whitespace-pre-wrap break-words">
            <span className="shrink-0 text-dim/70 num">{hms(l.ts)}</span>
            <span className={`w-9 shrink-0 uppercase ${COLOR[l.level]}`}>{l.level}</span>
            {l.stream && <span className="shrink-0 text-accent">{l.stream}</span>}
            <span className={l.level === "error" ? "text-bad" : l.level === "warn" ? "text-warn" : "text-mute"}>{l.message}</span>
          </div>
        ))}
        {live && <span className="px-caret mt-1" />}
      </div>
    </div>
  );
}
