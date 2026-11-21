"use client";
// /w/[ws]/sync: fetch history from the connected sources. Run controls, live streams + log, run history, run detail.
// (What the fetched records became in the graph lives under Ingestion.)
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { wsApi } from "@/lib/api";
import { useData } from "@/lib/data";
import { fmtStamp, type Run, type RunMeta, type StreamStatus, type SyncMode, type SyncStream } from "@/lib/types";
import { Icon } from "./icons";
import LogViewer from "./LogViewer";
import { Chip, Notice, Spinner, btnGhost, btnPrimary, errText } from "./ui";

const TONE: Record<StreamStatus, "run" | "ok" | "warn" | "bad"> = { running: "run", done: "ok", incomplete: "warn", failed: "bad" };
const RUN_TONE = { running: "run", done: "ok", failed: "bad" } as const;
const MODES: { id: SyncMode; label: string; hint: string }[] = [
  { id: "standard", label: "Standard", hint: "up to 20 pages per stream" },
  { id: "deep", label: "Deep sync", hint: "up to 100 pages per stream; slower" },
];
const dur = (r: { started_at: string; finished_at?: string }) => {
  if (!r.finished_at) return "running";
  const s = Math.max(0, Math.round((Date.parse(r.finished_at) - Date.parse(r.started_at)) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
};

export function StreamTable({ streams }: { streams: SyncStream[] }) {
  return (
    <div className="overflow-auto rounded-lg border border-line">
      <table className="w-full text-[12px]">
        <caption className="sr-only">Sync streams</caption>
        <thead className="bg-panel">
          <tr className="label text-left">
            <th scope="col" className="py-1.5 pl-3 pr-2 font-medium">Stream</th><th scope="col" className="px-2 font-medium">Status</th>
            <th scope="col" className="px-2 text-right font-medium">Pages</th><th scope="col" className="px-2 text-right font-medium">Fetched</th>
            <th scope="col" className="px-2 text-right font-medium">Stored</th><th scope="col" className="pl-2 pr-3 text-right font-medium">Errors</th>
          </tr>
        </thead>
        <tbody>
          {streams.map((s) => (
            <tr key={s.stream} className="border-t border-line align-top">
              <th scope="row" className="max-w-[220px] truncate py-1.5 pl-3 pr-2 text-left font-mono text-[11.5px] font-normal" title={s.stream}>{s.stream}</th>
              <td className="px-2 py-1.5"><Chip tone={TONE[s.status]}>{s.status === "running" && <Spinner />}{s.status}</Chip></td>
              <td className="px-2 py-1.5 text-right num">{s.pages}</td>
              <td className="px-2 py-1.5 text-right num">{s.fetched}</td>
              <td className="px-2 py-1.5 text-right num">{s.persisted}</td>
              <td className="py-1.5 pl-2 pr-3 text-right num">{s.errors.length}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetail({ ws, id, onClose }: { ws: string; id: string; onClose: () => void }) {
  const { sync } = useData();
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const live = run?.state === "running";
  useEffect(() => {
    const ctl = new AbortController();
    const load = () => wsApi.run(ws, id, ctl.signal).then((r) => { if (!ctl.signal.aborted) { setRun(r); setError(""); } }, (e) => { if (e?.name !== "AbortError") setError(errText(e)); });
    load();
    const t = live ? setInterval(load, 1500) : undefined;
    return () => { ctl.abort(); if (t) clearInterval(t); };
  }, [ws, id, live, sync?.state]);

  return (
    <section aria-label="Run detail" className="card fade-up overflow-hidden">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
        <h3 className="font-semibold">Run <span className="font-mono text-[12.5px] text-mute">{id.slice(0, 8)}</span></h3>
        {run && <Chip tone={RUN_TONE[run.state]}>{live && <Spinner />}{run.state}</Chip>}
        {run && <span className="text-[12px] text-dim">{run.mode === "deep" ? "deep" : "standard"} · {fmtStamp(run.started_at)} · {dur(run)}</span>}
        <button onClick={onClose} aria-label="Close run detail" className="ml-auto text-dim hover:text-fg"><Icon name="x" size={15} /></button>
      </header>
      <div className="space-y-4 p-5">
        {error && <Notice tone="warn">{error}</Notice>}
        {!run && !error && <p className="flex items-center gap-2 text-dim"><Spinner />Loading run…</p>}
        {run && (
          <>
            {run.error && <Notice tone="warn">{run.error}</Notice>}
            {run.streams.length > 0 && <StreamTable streams={run.streams} />}
            <p className="text-[12px] text-dim">
              <b className="font-medium text-fg">{run.totals.fetched}</b> fetched · <b className="font-medium text-fg">{run.totals.persisted}</b> stored · <b className="font-medium text-fg">{run.totals.errors}</b> errors
              {run.graph && <> · graph <b className="font-medium text-fg">{run.graph.artifacts}</b> items, <b className="font-medium text-fg">{run.graph.edges}</b> links</>}
              {run.triggered_by && <> · started by <span className="font-mono">{run.triggered_by}</span></>}
            </p>
            <LogViewer lines={run.log} live={live} />
          </>
        )}
      </div>
    </section>
  );
}

export default function SyncPage() {
  const router = useRouter();
  const params = useSearchParams();
  const { ws, info, sync, syncLoaded, startSync, targets, connected } = useData();
  const [mode, setMode] = useState<SyncMode>("standard");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<RunMeta[] | null>(null);
  const [runsError, setRunsError] = useState("");
  const selected = params.get("run");
  const running = sync?.state === "running";

  // history reloads whenever a run starts or ends
  useEffect(() => {
    if (!ws) return;
    let off = false;
    wsApi.runs(ws).then((r) => { if (!off) { setRuns(r); setRunsError(""); } }, (e) => { if (!off) setRunsError(errText(e)); });
    return () => { off = true; };
  }, [ws, sync?.state, sync?.id]);

  if (!ws || !info) return null;
  const demo = info.workspace.demo;
  const hasTargets = !!targets && targets.github.repos.length + targets.jira.projects.length + targets.slack.channels.length > 0;
  const select = (id: string | null) => router.replace(id ? `/w/${ws}/sync?run=${encodeURIComponent(id)}` : `/w/${ws}/sync`, { scroll: false });
  const start = async (m: SyncMode) => {
    setStarting(true); setError("");
    try { await startSync(m); } catch (e) { setError(errText(e)); } finally { setStarting(false); }
  };
  const sources = [
    { icon: "repo", n: connected.repos.length, label: "repositories" },
    { icon: "issue", n: connected.jira.length, label: "Jira projects" },
    { icon: "discussion", n: connected.slack.length, label: "Slack channels" },
  ] as const;

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-[980px] px-8 py-8">
        <p className="label">{info.workspace.name}</p>
        <div className="mt-1 flex flex-wrap items-end gap-4">
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight">Sync</h1>
            <p className="mt-0.5 max-w-[560px] text-dim">Fetch history from your connected sources. Every run is recorded with its log. What the records became in the graph is under <Link href={`/w/${ws}/ingestion`} className="text-accent hover:underline">Ingestion</Link>.</p>
          </div>
        </div>

        <section aria-label="Run a sync" className="card mt-6 p-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[12.5px]">
            {sources.map((s) => (
              <span key={s.label} className={`flex items-center gap-1.5 ${s.n ? "text-mute" : "text-dim/60"}`}><Icon name={s.icon} size={13} /><b className="font-medium text-fg">{s.n}</b>{s.label}</span>
            ))}
            <Link href={`/w/${ws}/settings/sources`} className="ml-auto text-accent hover:underline">Edit sources</Link>
          </div>
          {demo ? <div className="mt-4"><Notice tone="dim">Demo setup is locked: this workspace is not re-synced.</Notice></div> : (
            <>
              <fieldset disabled={running || starting} className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1">
                <legend className="sr-only">Sync mode</legend>
                {MODES.map((m) => (
                  <label key={m.id} className="flex cursor-pointer items-center gap-1.5">
                    <input type="radio" name={`mode-${ws}`} checked={mode === m.id} onChange={() => setMode(m.id)} className="accent-[var(--accent)]" />
                    <span className="font-medium">{m.label}</span><span className="text-[11.5px] text-dim">{m.hint}</span>
                  </label>
                ))}
              </fieldset>
              <div className="mt-3 flex items-center gap-3">
                <button type="button" onClick={() => start(mode)} disabled={running || starting || !hasTargets || !syncLoaded} className={btnPrimary}>
                  {running || starting ? <Spinner /> : <Icon name="play" size={11} />}{running ? "Syncing…" : "Run sync"}
                </button>
                {!hasTargets && <span className="text-[11.5px] text-dim">Select a repository, project or channel in <Link href={`/w/${ws}/settings/sources`} className="text-accent hover:underline">Sources</Link> first.</span>}
              </div>
              {error && <div className="mt-3"><Notice tone="warn">{error}</Notice></div>}
            </>
          )}
        </section>

        {sync && sync.streams.length > 0 && (
          <section aria-label="Current sync" className="mt-5 space-y-3">
            <div className="flex items-center gap-3">
              <h2 className="font-semibold">{running ? "Running now" : "Latest run"}</h2>
              {sync.state !== "idle" && <Chip tone={sync.state === "running" ? "run" : sync.state === "failed" ? "bad" : sync.complete ? "ok" : "warn"}>{running && <Spinner />}{running ? "running" : sync.state === "failed" ? "failed" : sync.complete ? "complete" : "incomplete"}</Chip>}
              <span className="text-[12px] text-dim">{sync.mode === "deep" ? "deep" : "standard"}{sync.finished_at ? ` · ${fmtStamp(sync.finished_at)}` : ""}</span>
            </div>
            {sync.error && <Notice tone="warn">{sync.error}</Notice>}
            <StreamTable streams={sync.streams} />
            {sync.log && sync.log.length > 0 && <LogViewer lines={sync.log} live={running} height={220} />}
            {sync.state === "done" && !sync.complete && !demo && sync.mode !== "deep" && (
              <div className="flex items-center gap-3 rounded-md border border-line bg-panel px-3 py-2.5">
                <Icon name="alert" size={13} className="text-warn" /><span className="text-[12.5px] text-mute">Some streams hit the page limit, so older history may be missing.</span>
                <button type="button" onClick={() => start("deep")} disabled={starting} className={`${btnGhost} ml-auto`}>{starting && <Spinner />}Sync deeper</button>
              </div>
            )}
          </section>
        )}

        <section aria-label="Run history" className="mt-8">
          <h2 className="mb-2 font-semibold">Run history</h2>
          {runsError && <Notice tone="warn">{runsError}</Notice>}
          {!runs && !runsError && <p className="flex items-center gap-2 text-dim"><Spinner />Loading…</p>}
          {runs && runs.length === 0 && <div className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-dim">No runs yet. Run a sync to see its log here.</div>}
          {runs && runs.length > 0 && (
            <div className="card overflow-hidden">
              <table className="w-full text-[12.5px]">
                <caption className="sr-only">Sync runs, newest first</caption>
                <thead className="bg-panel"><tr className="label text-left">
                  <th scope="col" className="py-2 pl-4 pr-2 font-medium">Started</th><th scope="col" className="px-2 font-medium">State</th><th scope="col" className="px-2 font-medium">Mode</th>
                  <th scope="col" className="px-2 text-right font-medium">Fetched</th><th scope="col" className="px-2 text-right font-medium">Stored</th><th scope="col" className="px-2 text-right font-medium">Errors</th>
                  <th scope="col" className="py-2 pl-2 pr-4 text-right font-medium">Duration</th>
                </tr></thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className={`cursor-pointer border-t border-line hover:bg-panel ${selected === r.id ? "bg-raised" : ""}`}
                      onClick={() => select(selected === r.id ? null : r.id)} aria-selected={selected === r.id}>
                      <td className="py-2 pl-4 pr-2"><button className="text-left hover:underline" aria-label={`Open run from ${fmtStamp(r.started_at)}`}>{fmtStamp(r.started_at)}</button></td>
                      <td className="px-2"><Chip tone={RUN_TONE[r.state]}>{r.state === "running" && <Spinner />}{r.state}{r.state === "done" && !r.complete ? " · partial" : ""}</Chip></td>
                      <td className="px-2 text-dim">{r.mode}</td>
                      <td className="px-2 text-right num">{r.totals.fetched}</td><td className="px-2 text-right num">{r.totals.persisted}</td>
                      <td className={`px-2 text-right num ${r.totals.errors ? "text-warn" : "text-dim"}`}>{r.totals.errors}</td>
                      <td className="py-2 pl-2 pr-4 text-right font-mono text-[11.5px] text-dim">{dur(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selected && <div className="mt-5"><RunDetail ws={ws} id={selected} onClose={() => select(null)} /></div>}
      </div>
    </div>
  );
}
