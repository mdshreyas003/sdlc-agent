"use client";
// /w/[ws]/overview: the workspace home. A greeting, what is waiting for review, and what changed lately.
// Each card can be switched off with "Customize"; the choice is a per-browser convenience (localStorage).
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { wsApi } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { useData } from "@/lib/data";
import type { MemoryEntry, MemoryList } from "@/lib/types";
import { Icon } from "./icons";
import { Chip, btnAccent, btnGhost } from "./ui";

const CARDS = [
  { id: "greeting", label: "Greeting and summary" },
  { id: "review", label: "Memory waiting for review" },
  { id: "activity", label: "Recent activity" },
] as const;
type CardId = (typeof CARDS)[number]["id"];
const KIND = { adr: "Decision", rule: "Rule", episode: "Episode" } as const;

const greeting = (d = new Date()) => (d.getHours() < 12 ? "Good morning" : d.getHours() < 18 ? "Good afternoon" : "Good evening");
const when = (iso: string) => {
  const m = Math.round((Date.now() - Date.parse(iso)) / 60000);
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
};

export default function OverviewPage() {
  const { ws, investigations } = useData();
  const { me } = useMe();
  const [data, setData] = useState<MemoryList | null>(null);
  const [error, setError] = useState(false);
  const [off, setOff] = useState<CardId[]>([]);
  const [custom, setCustom] = useState(false);

  useEffect(() => { try { setOff(JSON.parse(localStorage.getItem(`ov-off:${ws}`) || "[]")); } catch {} }, [ws]);
  useEffect(() => { if (ws) wsApi.memory(ws).then(setData).catch(() => setError(true)); }, [ws]);
  const toggle = (id: CardId) => setOff((o) => {
    const n = o.includes(id) ? o.filter((x) => x !== id) : [...o, id];
    try { localStorage.setItem(`ov-off:${ws}`, JSON.stringify(n)); } catch {}
    return n;
  });
  const on = (id: CardId) => !off.includes(id);

  const waiting = useMemo(() => (data?.items ?? []).filter((e) => e.status === "draft" || e.status === "staged"), [data]);
  const events = useMemo(() => (data?.items ?? [])
    .flatMap((e) => e.revisions.map((r) => ({ ...r, entry: e })))
    .sort((a, b) => b.at.localeCompare(a.at)).slice(0, 8), [data]);
  const live = (data?.items ?? []).filter((e) => e.served).length; // approved, including ones with a staged update
  const name = me?.auth === "enabled" ? me.user?.name?.split(" ")[0] : undefined;
  const base = `/w/${ws}`;

  return (
    <div className="mx-auto flex max-w-[1000px] flex-col gap-6 px-6 py-8 sm:px-8">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          {on("greeting") ? (
            <>
              <h1 className="text-[22px] font-semibold">{greeting()}{name ? `, ${name}` : ""}</h1>
              <p className="mt-1 text-[13.5px] text-mute">
                {error ? "Memory could not be loaded. Is the API running?" : !data ? "Checking your memory…"
                  : waiting.length ? `${waiting.length} ${waiting.length === 1 ? "entry is" : "entries are"} waiting for your review. ${live} live for agents.`
                  : `Nothing is waiting. ${live} ${live === 1 ? "entry is" : "entries are"} live for agents.`}
              </p>
            </>
          ) : <h1 className="text-[22px] font-semibold">Overview</h1>}
        </div>
        <button className={btnGhost} aria-expanded={custom} onClick={() => setCustom((c) => !c)}><Icon name="sliders" size={14} />Customize</button>
      </div>

      {custom && (
        <fieldset className="card flex flex-wrap gap-x-6 gap-y-2 p-4">
          <legend className="label px-1">Show on this page</legend>
          {CARDS.map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-[13px]">
              <input type="checkbox" checked={on(c.id)} onChange={() => toggle(c.id)} />{c.label}
            </label>
          ))}
          <p className="w-full text-[11.5px] text-dim">Saved in this browser only.</p>
        </fieldset>
      )}

      {on("review") && (
        <section className="card p-5" aria-label="Memory waiting for review">
          <header className="mb-3 flex items-center gap-3">
            <h2 className="text-[14px] font-semibold">Waiting for your review</h2>
            <Chip tone={waiting.length ? "warn" : "dim"}>{waiting.length}</Chip>
            <Link href={`${base}/memory`} className={`${btnAccent} ml-auto`}>Open review queue<Icon name="right" size={14} /></Link>
          </header>
          {!waiting.length ? <p className="text-[13px] text-dim">{data ? "Triage a new PR from the review queue to draft more." : "…"}</p> : (
            <ul className="flex flex-col divide-y divide-line">
              {waiting.slice(0, 5).map((e) => <ReviewRow key={e.id} e={e} href={`${base}/memory?e=${e.id}`} />)}
            </ul>
          )}
        </section>
      )}

      {on("activity") && (
        <section className="card p-5" aria-label="Recent activity">
          <h2 className="mb-3 text-[14px] font-semibold">Recent activity</h2>
          {!events.length && !investigations.length ? <p className="text-[13px] text-dim">Nothing yet. Memory changes and questions you ask will show up here.</p> : (
            <ul className="flex flex-col gap-2.5 text-[13px]">
              {events.map((r) => (
                <li key={`${r.entry.id}:${r.version}`} className="flex items-baseline gap-2">
                  <Icon name="shield" size={13} className="shrink-0 text-dim" />
                  <Link href={`${base}/memory?e=${r.entry.id}`} className="min-w-0 flex-1 truncate hover:underline"><span className="text-mute">{r.note}</span> · {r.entry.title}</Link>
                  <span className="shrink-0 text-[11.5px] text-dim">{r.by} · {when(r.at)}</span>
                </li>
              ))}
              {investigations.slice(0, 3).map((q) => (
                <li key={q.id} className="flex items-baseline gap-2">
                  <Icon name="help" size={13} className="shrink-0 text-dim" />
                  <span className="min-w-0 flex-1 truncate"><span className="text-mute">Question</span> · {q.question}</span>
                  <span className="shrink-0 text-[11.5px] text-dim">{when(q.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

function ReviewRow({ e, href }: { e: MemoryEntry; href: string }) {
  return (
    <li>
      <Link href={href} className="flex items-center gap-3 py-2.5 hover:bg-hover/50">
        <span className="w-[72px] shrink-0 text-[11.5px] font-medium text-accent">{KIND[e.kind]}</span>
        <span className="min-w-0 flex-1 truncate text-[13px]">{e.title}</span>
        <span className="shrink-0 text-[11.5px] text-dim">{e.status === "staged" ? "updated by a new PR" : "new draft"} · {e.evidence.length} evidence</span>
        <Icon name="right" size={13} className="shrink-0 text-dim" />
      </Link>
    </li>
  );
}
