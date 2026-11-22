"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { meApi, wsApi } from "@/lib/api";
import { useData } from "@/lib/data";
import { fmtDate, fmtTime, type WorkspaceRow } from "@/lib/types";
import Empty from "./Empty";
import { Icon } from "./icons";
import { Chip, Notice, Spinner, btnGhost, btnPrimary, errText, field } from "./ui";

function SyncLine({ s }: { s: WorkspaceRow["last_sync"] }) {
  if (!s) return <span className="text-dim">Not synced yet</span>;
  const tone = s.state === "done" ? "text-ok" : s.state === "failed" ? "text-bad" : s.state === "running" ? "text-accent" : "text-dim";
  return (
    <span className="text-dim">
      Last sync <span className={tone}>{s.state}</span>
      {s.finished_at && ` · ${fmtDate(s.finished_at)} ${fmtTime(s.finished_at)} UTC`}
    </span>
  );
}

function Card({ w, onDeleted }: { w: WorkspaceRow; onDeleted: () => void }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState(w.name);
  const stats = [
    { icon: "repo", n: w.connected.repos, label: w.connected.repos === 1 ? "repo" : "repos" },
    { icon: "issue", n: w.connected.jira, label: "Jira" },
    { icon: "discussion", n: w.connected.slack, label: "Slack" },
    { icon: "file", n: w.connected.docs ?? 0, label: w.connected.docs === 1 ? "doc" : "docs" },
  ] as const;
  const empty = stats.every((s) => s.n === 0);

  const rename = async () => {
    setBusy(true); setError("");
    try { await meApi.renameWorkspace(w.slug, newName.trim()); onDeleted(); setRenaming(false); } catch (e) { setError(errText(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true); setError("");
    try { await wsApi.remove(w.slug); onDeleted(); } catch (e) { setError(errText(e)); setBusy(false); }
  };

  return (
    <li className="card flex min-w-0 flex-col p-5">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-fg text-[15px] font-semibold text-bg">{w.name[0]?.toUpperCase()}</span>
        <h2 className="min-w-0 truncate text-[15px] font-semibold">{w.name}</h2>
        {!w.shared && w.owned !== false && !w.demo && (
          <button onClick={() => setRenaming(true)} aria-label={`Rename ${w.name}`} className="ml-auto text-dim hover:text-fg"><Icon name="sliders" size={13} /></button>
        )}
      </div>
      <div className="mt-2">{w.shared ? <Chip tone="dim"><Icon name="flask" size={11} />shared demo · read-only</Chip> : w.demo ? <Chip tone="dim"><Icon name="flask" size={11} />demo</Chip> : <Chip tone="ok"><Icon name="lock" size={11} />yours</Chip>}</div>
      {renaming && (
        <form onSubmit={(e) => { e.preventDefault(); rename(); }} className="mt-3 flex items-center gap-2">
          <input value={newName} onChange={(e) => setNewName(e.target.value)} aria-label="Workspace name" maxLength={80} autoFocus className={field} />
          <button type="submit" disabled={busy || !newName.trim()} className={btnPrimary}>{busy && <Spinner />}Save</button>
          <button type="button" onClick={() => { setRenaming(false); setNewName(w.name); }} className={btnGhost}>Cancel</button>
        </form>
      )}
      <div className="mt-4 flex gap-4 text-[12.5px]">
        {empty ? <span className="text-dim">Nothing connected yet</span> : stats.map((s) => (
          <span key={s.label} className={`flex items-center gap-1.5 ${s.n ? "text-mute" : "text-dim/60"}`}>
            <Icon name={s.icon} size={13} /><b className="font-medium text-fg">{s.n}</b>{s.label}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[12px]"><SyncLine s={w.last_sync} /></p>
      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Link href={`/w/${w.slug}/overview`} className={btnPrimary}>Open</Link>
        <Link href={`/w/${w.slug}/sync`} className={btnGhost}><Icon name="replay" size={13} />Sync</Link>
        <Link href={`/w/${w.slug}/ingestion`} className={btnGhost}><Icon name="layers" size={13} />Ingestion</Link>
        <Link href={`/w/${w.slug}/settings`} className={btnGhost} aria-label={`Settings of ${w.name}`}><Icon name="sliders" size={13} /></Link>
        {w.shared || w.owned === false ? null : confirm ? (
          <span className="ml-auto flex items-center gap-1.5 text-[12px]">
            <span className="text-dim">Delete?</span>
            <button onClick={remove} disabled={busy} className="inline-flex h-8 items-center gap-1.5 rounded-md bg-bad px-3 text-[12.5px] font-medium text-bg hover:opacity-90 disabled:opacity-40">{busy && <Spinner />}Delete</button>
            <button onClick={() => setConfirm(false)} disabled={busy} className={btnGhost}>Cancel</button>
          </span>
        ) : (
          <button onClick={() => setConfirm(true)} aria-label={`Delete workspace ${w.name}`} className="ml-auto grid h-8 w-8 place-items-center rounded-md text-dim hover:bg-hover hover:text-bad"><Icon name="x" size={14} /></button>
        )}
      </div>
      {error && <div className="mt-2"><Notice tone="warn">{error}</Notice></div>}
    </li>
  );
}

export default function Home() {
  const router = useRouter();
  const { workspaces, workspacesError, refreshWorkspaces } = useData();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 30); // preview only; the server picks the final one

  const create = async () => {
    const n = name.trim();
    if (!n) return;
    setBusy(true); setError("");
    try {
      const w = await wsApi.create(n);
      router.push(`/w/${w.slug}/setup`);
    } catch (e) { setError(errText(e)); setBusy(false); }
  };

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-[760px] px-8 pb-16 pt-16">
        <h1 className="text-[24px] font-semibold tracking-tight">Workspaces</h1>
        <p className="mt-1 text-dim">Your workspaces are private to your account. Each has its own sources, credentials, sync history and optional model override.</p>

        <section aria-label="New workspace" className="card mt-8 p-5">
          <h2 className="font-semibold">New workspace</h2>
          <p className="mt-0.5 text-[12.5px] text-dim">One workspace per project or team. It holds its own sources, credentials and sync history.</p>
          <form onSubmit={(e) => { e.preventDefault(); create(); }} className="mt-4 flex items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Payments platform" aria-label="New workspace name" maxLength={80} autoComplete="off"
              className={`${field} h-10 font-sans text-[14px]`} />
            <button type="submit" disabled={busy || !name.trim()} className={`${btnPrimary} h-10 shrink-0 px-5`}>{busy ? <Spinner /> : <Icon name="plus" size={13} />}Create workspace</button>
          </form>
          <p className="mt-2 h-4 font-mono text-[11px] text-dim" aria-live="polite">{slug ? <>address <span className="text-mute">/w/{slug}</span> · you can rename it later</> : "You can rename it later in Settings."}</p>
          {error && <div className="mt-2"><Notice tone="warn">{error}</Notice></div>}
        </section>

        <div className="mt-6">
          {workspacesError && (
            <Empty icon="alert" title="Backend unavailable">
              <p className="mb-3 max-w-[360px] text-dim">{workspacesError}</p>
              <button onClick={refreshWorkspaces} className={btnPrimary}>Retry</button>
            </Empty>
          )}
          {!workspacesError && !workspaces && <p className="flex items-center gap-2 text-dim"><Spinner />Loading…</p>}
          {workspaces && workspaces.length === 0 && (
            <div className="py-10"><Empty icon="repo" title="No workspaces yet">
              <p className="max-w-[360px] text-dim">Create your first one above to connect a repository.</p>
            </Empty></div>
          )}
          {workspaces && workspaces.length > 0 && (
            <ul className="grid grid-cols-2 gap-4">{workspaces.map((w) => <Card key={w.slug} w={w} onDeleted={refreshWorkspaces} />)}</ul>
          )}
        </div>
      </div>
    </div>
  );
}
