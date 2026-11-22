"use client";
// /w/[ws]/memory: review queue for ADRs, rules and episodes proposed from the evidence graph.
// Nothing reaches agents until a person approves it (docs/memory.md). Every control says why it is disabled.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, wsApi } from "@/lib/api";
import { useData } from "@/lib/data";
import type { MemoryEntry, MemoryKind, MemoryList, MemoryStatus, TriageResult } from "@/lib/types";
import { Icon } from "./icons";
import { Chip, Notice, Spinner, btnAccent, btnGhost, btnPrimary, errText, field } from "./ui";

const btnDanger = "inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-bad/40 px-3 text-[12.5px] text-bad hover:bg-bad/10 disabled:opacity-40";
const NEXT: Record<string, string> = {
  draft: "Next: read the evidence, fix the text, then approve or reject.",
  staged: "Next: review what changed, then approve the update or leave it staged.",
  approved: "Live. Edit to stage a change, or retire it to stop serving it.",
  rejected: "Closed. Reopen it if the decision should be reconsidered.",
  retired: "Closed. Reopen it to start a new draft.",
};

const KIND: Record<MemoryKind, { label: string; hint: string }> = {
  adr: { label: "Decision (ADR)", hint: "A choice and its trade-off" },
  rule: { label: "Rule", hint: "Something agents must always or never do" },
  episode: { label: "Episode", hint: "What broke, why, and the fix" },
};
const TABS = [
  { id: "review", label: "Review", has: ["draft", "staged"] },
  { id: "approved", label: "Approved", has: ["approved"] },
  { id: "closed", label: "Closed", has: ["rejected", "retired"] },
] as const;
const TONE: Record<MemoryStatus, "run" | "warn" | "ok" | "dim"> = { draft: "dim", staged: "warn", approved: "ok", rejected: "dim", retired: "dim" };
const STATUS_HELP: Record<MemoryStatus, string> = {
  draft: "Proposed. Not served to agents.",
  staged: "New evidence arrived. Needs your review.",
  approved: "Served to agents.",
  rejected: "Dismissed. The same evidence will not be proposed again.",
  retired: "Was approved; no longer served.",
};
const ACTION_TEXT: Record<TriageResult["action"], (r: TriageResult) => string> = {
  created: () => "Drafted a new entry.",
  refined: (r) => `Existing entry refined: ${r.note}`,
  unchanged: () => "Already covered. No new evidence for that entry.",
  suppressed: (r) => r.note,
  nothing: (r) => r.note,
};

export default function MemoryPage() {
  const { ws } = useData();
  const [data, setData] = useState<MemoryList | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("review");
  const [sel, setSel] = useState<string | null>(null);
  const [anchor, setAnchor] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "warn" | "dim"; text: string } | null>(null);
  const dirty = useRef(false); // set by the open editor; asked before anything that would discard its edits
  const leave = useCallback(() => !dirty.current || window.confirm("You have unsaved edits. Discard them?"), []);
  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (dirty.current) e.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const load = useCallback(async () => {
    if (!ws) return;
    try { setData(await wsApi.memory(ws)); } catch (e) { setMsg({ tone: "warn", text: errText(e) }); setData({ counts: {} as MemoryList["counts"], items: [] }); }
  }, [ws]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { try { const e = new URLSearchParams(window.location.search).get("e"); if (e) setSel(e); } catch {} }, []);

  const group = TABS.find((t) => t.id === tab)!;
  const items = useMemo(() => (data?.items ?? []).filter((e) => (group.has as readonly string[]).includes(e.status)), [data, group]);
  const count = (t: (typeof TABS)[number]) => t.has.reduce((n, s) => n + (data?.counts[s] ?? 0), 0);
  const current = items.find((e) => e.id === sel) ?? items[0] ?? null;
  useEffect(() => { // a deep link (?e=) may point at an entry in another tab
    const hit = data?.items.find((e) => e.id === sel);
    const t = hit && TABS.find((x) => (x.has as readonly string[]).includes(hit.status));
    if (t && t.id !== tab) setTab(t.id);
  }, [sel, data]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { // j / k step through the list unless the user is typing
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || e.metaKey || e.ctrlKey || e.altKey || !items.length) return;
      const i = Math.max(0, items.findIndex((x) => x.id === current?.id));
      if (e.key === "j" && leave()) setSel(items[Math.min(items.length - 1, i + 1)].id);
      if (e.key === "k" && leave()) setSel(items[Math.max(0, i - 1)].id);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [items, current?.id, leave]);

  async function triage(e: React.FormEvent) {
    e.preventDefault();
    if (!ws || !anchor.trim()) return;
    setBusy(true); setMsg(null);
    try {
      const r = await wsApi.memoryTriage(ws, anchor.trim());
      setMsg({ tone: r.action === "created" || r.action === "refined" ? "ok" : "dim", text: ACTION_TEXT[r.action](r) });
      await load();
      if (r.entry) { setSel(r.entry.id); setTab(r.entry.status === "rejected" ? "closed" : "review"); }
    } catch (err) { setMsg({ tone: "warn", text: errText(err) }); } finally { setBusy(false); }
  }

  return (
    <div className="h-full overflow-y-auto"><div className="mx-auto flex max-w-[1180px] flex-col gap-5 px-6 py-8 sm:px-8">
      <header>
        <h1 className="text-[20px] font-semibold">Memory review</h1>
        <p className="mt-1 max-w-[70ch] text-[13px] leading-relaxed text-mute">
          Decisions, rules and past incidents proposed from your history. You decide what becomes memory. Only approved entries are served to coding agents.
        </p>
      </header>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-label="How memory works">
        {[
          ["1", "Triage", "Point at a PR, ticket or file. A draft appears, or nothing if it holds no decision.", null],
          ["2", "Review", "Edit the text and check the cited evidence.", data ? `${(data.counts.draft ?? 0) + (data.counts.staged ?? 0)} waiting` : null],
          ["3", "Approve", "Your sign-off publishes it. Reject needs a reason.", null],
          ["4", "Agents read", "The MCP memory tool serves approved entries only.", data ? `${data.items.filter((e) => e.served).length} live` : null],
        ].map(([n, t, d, c]) => (
          <li key={n} className="card flex gap-3 p-3.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-raised font-mono text-[11px] text-mute">{n}</span>
            <span className="min-w-0"><span className="flex items-center gap-2 text-[13px] font-medium">{t}{c && <span className="font-mono text-[11px] font-normal text-accent">{c}</span>}</span>
              <span className="mt-0.5 block text-[12px] leading-snug text-dim">{d}</span></span>
          </li>
        ))}
      </ol>
      <form onSubmit={triage} className="card flex flex-wrap items-center gap-3 p-4" aria-label="Triage a change">
        <label htmlFor="triage" className="text-[13px] font-medium">Step 1 · Triage a change</label>
        <input id="triage" className={`${field} min-w-[240px] max-w-[440px]`} value={anchor} onChange={(e) => setAnchor(e.target.value)}
          placeholder="#18720, KAFKA-18654 or clients/…/Sender.java" />
        <button className={btnAccent} disabled={busy || !anchor.trim()}>{busy ? <Spinner /> : <Icon name="search" size={14} />}Draft memory from this</button>
        <span className="text-[11.5px] text-dim">Reads the evidence only. It never approves anything.</span>
      </form>
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}

      <div role="tablist" aria-label="Memory status" className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => { if (leave()) { setTab(t.id); setSel(null); } }}
            className={`-mb-px h-9 border-b-2 px-3 text-[13px] ${tab === t.id ? "border-accent font-medium text-fg" : "border-transparent text-mute hover:text-fg"}`}>
            {t.label} <span className="font-mono text-[11px] text-dim">{count(t)}</span>
          </button>
        ))}
      </div>

      {!data ? <p className="text-dim"><Spinner /> Loading…</p> : !items.length ? <EmptyState tab={tab} /> : (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(260px,340px)_1fr]">
          <ul className="flex flex-col gap-2" aria-label="Entries">
            {items.map((e) => (
              <li key={e.id}>
                <button onClick={() => { if (e.id !== current?.id && leave()) setSel(e.id); }} aria-current={e.id === current?.id}
                  className={`w-full rounded-lg border p-3 text-left ${e.id === current?.id ? "border-line2 bg-raised" : "border-transparent hover:bg-hover"}`}>
                  <span className="flex items-center gap-1.5 text-[11px]"><span className="font-medium text-accent">{KIND[e.kind].label}</span><Chip tone={TONE[e.status]}>{e.status}</Chip>
                    {e.served && e.status === "staged" && <span className="text-dim">v{e.served.version} live</span>}</span>
                  <span className="mt-1 line-clamp-2 block text-[13px]">{e.title}</span>
                  <span className="mt-0.5 block font-mono text-[10.5px] text-dim">{e.evidence.length} evidence · v{e.version}</span>
                </button>
              </li>
            ))}
          </ul>
          {current && <Detail key={`${current.id}:${current.version}`} entry={current} ws={ws!} onDirty={(d) => { dirty.current = d; }} onChange={async (m) => { if (m) setMsg(m); await load(); }} />}
        </div>
      )}
    </div>
    </div>
  );
}

function EmptyState({ tab }: { tab: string }) {
  const text = {
    review: "Nothing waiting. Paste a PR, ticket or file above and Triage will draft an entry when the evidence holds a decision, a rule or an incident. When it does not, it says so and drafts nothing.",
    approved: "No approved memory yet. Approve an entry from Review and it is served to agents through the `memory` tool.",
    closed: "Nothing rejected or retired.",
  }[tab];
  return <p className="max-w-[64ch] rounded-lg border border-dashed border-line p-6 text-[13px] text-mute">{text}</p>;
}

function Detail({ entry: e, ws, onChange, onDirty }: { entry: MemoryEntry; ws: string; onDirty: (d: boolean) => void; onChange: (m?: { tone: "ok" | "warn" | "dim"; text: string }) => Promise<void> }) {
  const [title, setTitle] = useState(e.title);
  const [body, setBody] = useState(e.body);
  const [kind, setKind] = useState<MemoryKind>(e.kind);
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<{ text: string; stale: boolean } | null>(null);
  const dirty = title !== e.title || body !== e.body || kind !== e.kind;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty]); // eslint-disable-line react-hooks/exhaustive-deps
  const editable = e.status === "draft" || e.status === "staged" || e.status === "approved";
  const todo = body.includes("TODO");
  const blocker = dirty ? "Save your edits first." : todo ? "Resolve the TODO markers in the text." : !e.evidence.length ? "Needs at least one evidence item." : null;

  async function run(fn: () => Promise<unknown>, ok?: string) {
    setBusy(true); setErr(null);
    try { await fn(); await onChange(ok ? { tone: "ok", text: ok } : undefined); }
    catch (x) { setErr({ text: errText(x), stale: x instanceof ApiError && x.status === 409 }); } finally { setBusy(false); }
  }
  const save = () => run(() => wsApi.memoryEdit(ws, e.id, { version: e.version, title, body, kind }),
    e.status === "approved" ? "Saved as a staged version. Agents still see the approved one until you approve." : "Saved.");

  return (
    <section className="card flex flex-col gap-4 p-5" aria-label="Entry">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={TONE[e.status]}>{e.status}</Chip>
        <span className="text-[12px] text-mute">{STATUS_HELP[e.status]}</span>
        <span className="ml-auto font-mono text-[11px] text-dim">v{e.version} · from {e.anchor}</span>
      </div>
      {e.served && e.status === "staged" && (
        <Notice tone="warn">Agents currently see v{e.served.version}, approved by {e.served.approved_by}. This version is not live until you approve it.</Notice>
      )}
      <p className="rounded-md bg-raised p-2.5 text-[12px] text-mute"><span className="font-medium text-fg">Why this kind: </span>{e.triage}</p>
      <p className="text-[12.5px] font-medium text-accent">{NEXT[e.status]}</p>

      <label className="flex flex-col gap-1 text-[12px] text-mute">Title
        <input className={`${field} flex-none text-[13px]`} value={title} onChange={(x) => setTitle(x.target.value)} disabled={!editable} maxLength={200} />
      </label>
      <label className="flex flex-col gap-1 text-[12px] text-mute">Kind
        <select className={`${field} max-w-[320px] flex-none`} value={kind} onChange={(x) => setKind(x.target.value as MemoryKind)} disabled={!editable}>
          {(Object.keys(KIND) as MemoryKind[]).map((k) => <option key={k} value={k}>{KIND[k].label}: {KIND[k].hint}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[12px] text-mute">Text (Markdown)
        <textarea className={`${field} h-56 flex-none resize-y py-2 leading-relaxed ${todo ? "border-warn" : ""}`} value={body} onChange={(x) => setBody(x.target.value)} disabled={!editable} spellCheck />
      </label>
      {todo && editable && <Notice tone="warn">TODO markers mark what the evidence could not fill in. Complete them before approving.</Notice>}

      <div>
        <h2 className="label pb-1">Evidence ({e.evidence.length})</h2>
        <ul className="flex flex-col gap-1.5">
          {e.evidence.map((ev) => (
            <li key={ev.id} className="rounded-md border border-line p-2 text-[12px]">
              <span className="flex items-center gap-2"><span className="font-mono text-[10.5px] text-dim">{ev.kind}</span>
                {ev.url ? <a href={ev.url} target="_blank" rel="noreferrer" className="truncate text-accent underline underline-offset-2">{ev.title || ev.id}</a> : <span className="truncate">{ev.title || ev.id}</span>}</span>
              {ev.quote && <q className="mt-1 line-clamp-3 block text-mute">{ev.quote}</q>}
            </li>
          ))}
        </ul>
      </div>

      {err && <div role="alert" className="flex items-center gap-2 text-[12px] text-warn">{err.text}{err.stale && <button className={btnGhost} onClick={() => onChange()}>Reload</button>}</div>}

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line pt-4">
        {editable && (
          <div className="flex flex-col gap-1">
            <button className={btnGhost} disabled={busy || !dirty || !title.trim() || !body.trim()} onClick={save}>Save edits</button>
            <span className="text-[11px] text-dim">{dirty ? "Unsaved changes" : "Nothing to save"}</span>
          </div>
        )}
        <div className="ml-auto flex flex-col items-end gap-1">
          <div className="flex gap-2">
            {(e.status === "draft" || e.status === "staged") && <>
              {!e.served && <button className={btnDanger} disabled={busy} onClick={() => setRejecting((r) => !r)}>Reject…</button>}
              <button className={btnAccent} disabled={busy || !!blocker} onClick={() => run(() => wsApi.memoryMove(ws, e.id, "approve", e.version), "Approved. Agents can now read it through the memory tool.")}>
                <Icon name="check" size={14} />Approve &amp; publish to agents</button>
            </>}
            {e.status === "approved" && <button className={btnDanger} disabled={busy} onClick={() => setRejecting((r) => !r)}>Retire…</button>}
            {(e.status === "rejected" || e.status === "retired") && <button className={btnPrimary} disabled={busy} onClick={() => run(() => wsApi.memoryMove(ws, e.id, "reopen", e.version), "Reopened as a draft.")}>Reopen as draft</button>}
          </div>
          {blocker && (e.status === "draft" || e.status === "staged") && <span className="text-[11.5px] text-warn">Approve is off: {blocker}</span>}
        </div>
      </div>
      {rejecting && (
        <form className="flex flex-wrap items-center gap-2 rounded-md bg-raised p-3" onSubmit={(x) => { x.preventDefault(); run(() => wsApi.memoryMove(ws, e.id, e.status === "approved" ? "retire" : "reject", e.version, reason), e.status === "approved" ? "Retired. Agents no longer see it." : "Rejected."); }}>
          <input autoFocus className={`${field} max-w-[380px]`} value={reason} onChange={(x) => setReason(x.target.value)} placeholder={e.status === "approved" ? "Why retire? (e.g. superseded by …)" : "Why reject? This stops the same proposal returning."} aria-label="Reason" />
          <button className={btnDanger} disabled={busy || (e.status !== "approved" && !reason.trim())}>{e.status === "approved" ? "Confirm retire" : "Confirm reject"}</button>
          <button type="button" className={btnGhost} onClick={() => setRejecting(false)}>Cancel</button>
        </form>
      )}

      <details className="text-[12px] text-mute">
        <summary className="cursor-pointer">History ({e.revisions.length})</summary>
        <ol className="mt-1 flex flex-col gap-0.5 font-mono text-[11px]">
          {[...e.revisions].reverse().map((r) => <li key={r.version}>v{r.version} · {r.at.slice(0, 16).replace("T", " ")} · {r.by} · {r.note}</li>)}
        </ol>
      </details>
    </section>
  );
}
