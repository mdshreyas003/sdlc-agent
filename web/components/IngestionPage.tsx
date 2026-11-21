"use client";
// /w/[ws]/ingestion: what the synced records became. Sync fetches; ingestion maps, links and stores them in the graph.
import Link from "next/link";
import { useMemo } from "react";
import { useData, useRemote } from "@/lib/data";
import { fmtDate, fmtStamp, type Ingestion } from "@/lib/types";
import { Icon } from "./icons";
import { Chip, Notice, Spinner } from "./ui";

const STAGE_ICON = { fetched: "replay", stored: "db", linked: "graph", indexed: "file" } as const;
const STAGE_HINT = {
  fetched: "Records pulled from the sources by the last run.",
  stored: "Mapped to items and written to the graph.",
  linked: "Links stated by a source (replies, containment, references).",
  indexed: "Repositories whose commit history can answer line-level questions.",
};
const TONE = { ok: "bg-ok", warn: "bg-warn", idle: "bg-line2" } as const;
const SOURCE_LABEL: Record<string, string> = { github: "GitHub", jira: "Jira", slack: "Slack / mail", confluence: "Docs", docs: "Docs" };
const n = (x: number) => x.toLocaleString();
const cap = (x: number | null) => (x === null ? "per item" : n(x));

/** What a run pulls, per target, and how far back the graph reaches. Sources of truth: PLAN in api/accounts.py, the graph. */
function HowItWorks({ data, ws }: { data: Ingestion; ws: string }) {
  const { plan, timeline, last_streams: streams } = data;
  const t = timeline.map((r) => ({ ...r, a: Date.parse(r.oldest), b: Date.parse(r.newest) })).filter((r) => !Number.isNaN(r.a) && !Number.isNaN(r.b));
  const lo = Math.min(...t.map((r) => r.a)), hi = Math.max(...t.map((r) => r.b));
  const span = Math.max(1, hi - lo);
  const incomplete = streams.filter((s) => s.status === "incomplete");
  return (
    <>
      <section aria-label="What gets pulled" className="card mt-6 overflow-hidden">
        <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line px-5 py-3">
          <h2 className="font-semibold">What a sync pulls</h2>
          <span className="font-mono text-[11.5px] text-dim">{plan.order} · standard {plan.pages.standard} pages · deep {plan.pages.deep} pages per stream</span>
          <Link href={`/w/${ws}/sync`} className="ml-auto inline-flex items-center gap-1 text-accent underline underline-offset-2">Run a sync<Icon name="arrow" size={12} /></Link>
        </header>
        {plan.sources.length === 0 ? <p className="px-5 py-4 text-dim">No sources selected yet. Pick repositories, projects or channels in <Link href={`/w/${ws}/settings/sources`} className="text-accent underline underline-offset-2">Settings</Link>.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12.5px]">
              <thead><tr className="label border-b border-line"><th className="px-5 py-2 font-medium">Target</th><th className="px-2 py-2 font-medium">Stream</th><th className="px-2 py-2 font-medium">Read order</th><th className="px-2 py-2 text-right font-medium">Standard max</th><th className="px-2 py-2 text-right font-medium">Deep max</th><th className="px-5 py-2 font-medium">Includes</th></tr></thead>
              <tbody className="divide-y divide-line">
                {plan.sources.flatMap((src) => src.streams.map((st, i) => (
                  <tr key={src.target + st.stream}>
                    <td className="px-5 py-2 font-mono text-[11.5px]">{i === 0 ? <><span className="text-dim">{src.source}:</span>{src.target}</> : ""}</td>
                    <td className="px-2 py-2">{st.label}</td>
                    <td className="px-2 py-2 text-dim">{st.order}</td>
                    <td className="px-2 py-2 text-right font-mono num">{cap(st.max.standard)}</td>
                    <td className="px-2 py-2 text-right font-mono num">{cap(st.max.deep)}</td>
                    <td className="px-5 py-2 text-dim">{st.includes}</td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
        )}
        <ul className="space-y-1 border-t border-line bg-panel px-5 py-3 text-[12px] text-dim">
          {plan.notes.map((x) => <li key={x} className="flex gap-2"><span aria-hidden className="text-accent">›</span>{x}</li>)}
        </ul>
      </section>

      <section aria-label="Time coverage" className="card mt-5 overflow-hidden">
        <header className="flex items-center gap-3 border-b border-line px-5 py-3">
          <h2 className="font-semibold">Time coverage</h2>
          {t.length > 0 && <span className="font-mono text-[11.5px] text-dim">{fmtDate(new Date(lo).toISOString())} → {fmtDate(new Date(hi).toISOString())}</span>}
        </header>
        {t.length === 0 ? <p className="px-5 py-4 text-dim">Nothing stored yet, so there is no time range. After a sync this shows the oldest and newest record per source.</p> : (
          <ul className="divide-y divide-line">
            {t.map((r) => (
              <li key={r.source + r.kind} className="grid grid-cols-[150px_1fr_190px] items-center gap-4 px-5 py-2.5">
                <span className="truncate text-[12.5px]"><span className="font-medium">{SOURCE_LABEL[r.source] ?? r.source}</span> <span className="font-mono text-[11px] text-dim">{r.kind}</span></span>
                <span className="relative block h-2 rounded-full bg-raised" aria-hidden>
                  <span className="absolute top-0 h-full rounded-full bg-accent/70" style={{ left: `${((r.a - lo) / span) * 100}%`, width: `${Math.max(1.5, ((r.b - r.a) / span) * 100)}%` }} />
                </span>
                <span className="text-right font-mono text-[11px] text-mute num">{fmtDate(r.oldest)} → {fmtDate(r.newest)} · {n(r.count)}</span>
              </li>
            ))}
          </ul>
        )}
        {incomplete.length > 0 && (
          <p className="border-t border-line bg-panel px-5 py-3 text-[12px] text-warn">
            {incomplete.length} stream{incomplete.length === 1 ? "" : "s"} in the last run stopped at the page cap, so older history exists that is not here: {incomplete.slice(0, 3).map((x) => x.stream).join(", ")}{incomplete.length > 3 ? "…" : ""}. A Deep sync reaches further back.
          </p>
        )}
      </section>
    </>
  );
}

export default function IngestionPage() {
  const { ws, info, sync } = useData();
  const { data, error, loading } = useRemote<Ingestion>(ws ? `/api/w/${encodeURIComponent(ws)}/ingestion` : null);
  const running = sync?.state === "running";

  const bySource = useMemo(() => {
    const m = new Map<string, { total: number; kinds: { kind: string; count: number }[] }>();
    for (const r of data?.by_source ?? []) {
      const e = m.get(r.source) ?? { total: 0, kinds: [] };
      e.total += r.count; e.kinds.push({ kind: r.kind, count: r.count });
      m.set(r.source, e);
    }
    return [...m.entries()].sort((a, b) => b[1].total - a[1].total);
  }, [data]);
  const max = Math.max(1, ...bySource.map(([, v]) => v.total));

  if (!ws || !info) return null;
  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-[980px] px-8 py-8">
        <p className="label">{info.workspace.name}</p>
        <h1 className="mt-1 text-[22px] font-semibold tracking-tight">Ingestion</h1>
        <p className="mt-0.5 max-w-[600px] text-dim">What your synced records became in the evidence graph. Sync fetches from sources; ingestion maps, links and stores. Run or inspect fetches under <Link href={`/w/${ws}/sync`} className="text-accent underline underline-offset-2">Sync</Link>.</p>

        {error && <div className="mt-5"><Notice tone="warn">{error}</Notice></div>}
        {loading && !data && <p className="mt-6 flex items-center gap-2 text-dim"><Spinner />Loading…</p>}
        {data && !data.neo4j.ok && (
          <div className="mt-5 rounded-lg border border-warn/40 px-3 py-2"><Notice tone="warn">The graph database (Neo4j) is not reachable, so counts below may be empty.</Notice></div>
        )}

        {data && (
          <>
            <HowItWorks data={data} ws={ws} />
            <section aria-label="Pipeline" className="mt-6 grid grid-cols-4 items-stretch gap-0">
              {data.stages.map((s, i) => (
                <div key={s.key} className="flex items-center">
                  <div className="card w-full p-4">
                    <div className="flex items-center justify-between">
                      <span className="grid h-8 w-8 place-items-center rounded-lg bg-raised"><Icon name={STAGE_ICON[s.key]} size={15} /></span>
                      <span aria-label={s.status} className={`h-[7px] w-[7px] rounded-full ${TONE[s.status]} ${running && s.key !== "indexed" ? "px-ping" : ""}`} />
                    </div>
                    <p className="mt-3 font-mono text-[24px] font-medium leading-none num">{n(s.count)}</p>
                    <p className="mt-1.5 font-medium">{s.label}</p>
                    <p className="mt-0.5 text-[11.5px] leading-snug text-dim">{STAGE_HINT[s.key]}</p>
                  </div>
                  {i < data.stages.length - 1 && <span aria-hidden className={`mx-1 h-[2px] w-5 shrink-0 rounded ${running ? "px-flow" : "bg-line2"}`} />}
                </div>
              ))}
            </section>

            <div className="mt-6 grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-5">
              <section aria-label="Graph" className="card overflow-hidden">
                <header className="flex items-center gap-3 border-b border-line px-5 py-3">
                  <h2 className="font-semibold">Graph</h2>
                  {data.graph && <span className="font-mono text-[11.5px] text-dim num">{n(data.graph.artifacts)} items · {n(data.graph.edges)} links{data.graph.stubs ? ` · ${n(data.graph.stubs)} stubs` : ""}</span>}
                </header>
                <div className="space-y-4 px-5 py-4">
                  {bySource.length === 0 && <p className="text-dim">Nothing ingested yet. <Link href={`/w/${ws}/sync`} className="text-accent underline underline-offset-2">Run a sync</Link>.</p>}
                  {bySource.map(([source, v]) => (
                    <div key={source}>
                      <div className="mb-1 flex items-center justify-between text-[12.5px]"><span className="font-medium">{SOURCE_LABEL[source] ?? source}</span><span className="font-mono text-dim num">{n(v.total)}</span></div>
                      <span className="block h-1.5 overflow-hidden rounded-full bg-raised"><span className="block h-full rounded-full bg-accent" style={{ width: `${(v.total / max) * 100}%` }} /></span>
                      <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[11px] text-dim">{v.kinds.map((k) => <span key={k.kind}>{k.kind} <b className="font-medium text-mute num">{n(k.count)}</b></span>)}</p>
                    </div>
                  ))}
                  {data.graph && data.graph.stubs > 0 && <p className="text-[11.5px] text-dim">Stubs are items that something links to but that were not loaded (outside the selected sources or beyond the page limit). A deeper sync can fill some in.</p>}
                </div>
              </section>

              <div className="space-y-5">
                <section aria-label="Repository coverage" className="card overflow-hidden">
                  <header className="border-b border-line px-5 py-3"><h2 className="font-semibold">Repository coverage</h2></header>
                  <ul className="divide-y divide-line">
                    {data.repos.length === 0 && <li className="px-5 py-4 text-dim">No repositories connected.</li>}
                    {data.repos.map((r) => (
                      <li key={r.repo} className="flex items-center gap-2 px-5 py-2.5">
                        <Icon name="repo" size={13} className="text-dim" /><span className="min-w-0 flex-1 truncate font-mono text-[12px]" title={r.repo}>{r.repo}</span>
                        {r.indexed ? <Chip tone="ok"><Icon name="check" size={11} />indexed</Chip> : <Chip tone="warn">not indexed</Chip>}
                      </li>
                    ))}
                  </ul>
                </section>

                <section aria-label="Last run" className="card p-5">
                  <h2 className="mb-2 font-semibold">Last run</h2>
                  {!data.last_run ? <p className="text-dim">No run recorded.</p> : (
                    <div className="space-y-1.5 text-[12.5px]">
                      <p className="flex items-center gap-2"><Chip tone={data.last_run.state === "done" ? (data.last_run.complete ? "ok" : "warn") : data.last_run.state === "failed" ? "bad" : "run"}>{data.last_run.state}{data.last_run.state === "done" && !data.last_run.complete ? " · partial" : ""}</Chip><span className="text-dim">{data.last_run.mode}</span></p>
                      <p className="text-dim">{fmtStamp(data.last_run.finished_at ?? data.last_run.started_at)}</p>
                      <p className="font-mono text-[11.5px] text-mute num">{n(data.last_run.totals.fetched)} fetched · {n(data.last_run.totals.persisted)} stored · {data.last_run.totals.errors} errors</p>
                      <Link href={`/w/${ws}/sync?run=${encodeURIComponent(data.last_run.id)}`} className="inline-flex items-center gap-1 pt-1 text-accent underline underline-offset-2">Open run and log<Icon name="arrow" size={12} /></Link>
                    </div>
                  )}
                </section>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
