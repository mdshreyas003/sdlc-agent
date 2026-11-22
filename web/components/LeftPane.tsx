"use client";
import Link from "next/link";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { repoSlug, useData, useRepoFiles } from "@/lib/data";
import { buildTree, fileHref, shortName, type TreeNode } from "@/lib/workspace";
import { Icon } from "./icons";
import { useLayout } from "./layout";
import { useLocation } from "./Shell";

const indent = (depth: number) => Math.min(depth, 5) * 12; // cap so deep trees never push names out of view

/** Current repo + dropdown of every repo in the workspace, so switching never needs a trip back to the list. */
function RepoSwitcher({ ws, current }: { ws: string; current: string }) {
  const { repos, isIndexed } = useData();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const on = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", on); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", on); document.removeEventListener("keydown", key); };
  }, [open]);
  const shown = repos.filter((r) => r.toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <div ref={ref} className="relative shrink-0 border-b border-line p-2">
      <button onClick={() => { setOpen((o) => !o); setQ(""); }} aria-haspopup="listbox" aria-expanded={open} title={current}
        className="flex h-9 w-full min-w-0 items-center gap-2 rounded-md px-2 hover:bg-hover">
        <Icon name="repo" size={14} className="text-dim" />
        <span className="min-w-0 flex-1 truncate text-left font-medium">{current}</span>
        {repos.length > 1 && <span className="shrink-0 rounded-full border border-line px-1.5 text-[10.5px] leading-[16px] text-dim">{repos.length}</span>}
        <Icon name="updown" size={12} className="shrink-0 text-dim" />
      </button>
      {open && (
        <div role="listbox" className="fade-up absolute inset-x-2 top-12 z-40 rounded-lg border border-line2 bg-bg p-1 shadow-xl shadow-black/20">
          {repos.length > 6 && (
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter repositories…"
              className="mb-1 h-8 w-full rounded-md border border-line bg-bg px-2 text-[12px] outline-none placeholder:text-dim focus:border-line2" />
          )}
          <div className="max-h-[260px] overflow-y-auto">
            {shown.map((r) => (
              <Link key={r} href={`/w/${ws}/${repoSlug(r)}`} onClick={() => setOpen(false)} role="option" aria-selected={r === current} title={r}
                className="flex h-8 items-center gap-2 rounded-md px-2 hover:bg-hover">
                <span className="min-w-0 flex-1 truncate">{r}</span>
                {!isIndexed(r) && <span className="shrink-0 text-[11px] text-warn">not synced</span>}
                {r === current && <Icon name="check" size={13} className="shrink-0 text-dim" />}
              </Link>
            ))}
            {shown.length === 0 && <p className="px-2 py-3 text-dim">No match</p>}
          </div>
          <div className="my-1 border-t border-line" />
          <Link href={`/w/${ws}`} onClick={() => setOpen(false)} className="flex h-8 items-center gap-2 rounded-md px-2 text-mute hover:bg-hover hover:text-fg"><Icon name="back" size={13} />All repositories</Link>
          <Link href={`/w/${ws}/settings/sources`} onClick={() => setOpen(false)} className="flex h-8 items-center gap-2 rounded-md px-2 text-mute hover:bg-hover hover:text-fg"><Icon name="plus" size={13} />Connect sources</Link>
        </div>
      )}
    </div>
  );
}

function Tree({ nodes, base, active, depth = 0 }: { nodes: TreeNode[]; base: string; active?: string; depth?: number }) {
  const [closed, setClosed] = useState<string[]>([]);
  return (
    <>
      {nodes.map((n) =>
        n.dir ? (
          <Fragment key={n.path}>
            <button onClick={() => setClosed((c) => (c.includes(n.path) ? c.filter((x) => x !== n.path) : [...c, n.path]))}
              style={{ paddingLeft: 8 + indent(depth) }} title={n.name}
              className="flex h-7 w-full min-w-0 items-center gap-1.5 rounded-md pr-2 text-left text-mute hover:bg-hover hover:text-fg">
              <Icon name="chevron" size={11} className={`shrink-0 text-dim transition-transform ${closed.includes(n.path) ? "-rotate-90" : ""}`} />
              <span className="min-w-0 truncate font-mono text-[12px]">{shortName(n.name, true)}</span>
            </button>
            {!closed.includes(n.path) && <Tree nodes={n.children} base={base} active={active} depth={depth + 1} />}
          </Fragment>
        ) : (
          <Link key={n.path} href={fileHref(base, n.path)} style={{ paddingLeft: 8 + indent(depth) + 15 }} aria-current={active === n.path ? "page" : undefined} title={n.path}
            className={`flex h-7 w-full min-w-0 items-center gap-2 rounded-md pr-2 ${active === n.path ? "bg-raised text-fg" : "text-mute hover:bg-hover hover:text-fg"}`}>
            <span className="min-w-0 truncate font-mono text-[12px]">{shortName(n.name, false)}</span>
          </Link>
        ),
      )}
    </>
  );
}

function Files({ repo, base, active }: { repo: string; base: string; active?: string }) {
  const { data, error, loading } = useRepoFiles(repo);
  const tree = useMemo(() => buildTree(data?.files ?? []), [data]);
  if (loading) return <p className="px-2 py-3 text-dim">Loading…</p>;
  if (error) return <p className="px-2 py-3 text-warn">{error}</p>;
  if (!tree.length) return <p className="px-2 py-3 text-dim">No files with recorded history.</p>;
  return <Tree nodes={tree} base={base} active={active} />;
}

export default function LeftPane({ ws }: { ws: string }) {
  const { repo: slug, file } = useLocation();
  const { repos, connected, repoByslug, isIndexed } = useData();
  const repo = slug ? repoByslug(slug) : undefined;
  const L = useLayout();

  return (
    <aside style={{ width: L.treeW }} className="flex h-full shrink-0 flex-col overflow-hidden bg-panel" aria-label="Repositories">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-line px-3">
        <span className="label">Files</span>
        <button onClick={L.toggleTree} aria-label="Hide files (\)" title="Hide files (\)" className="ml-auto grid h-6 w-6 place-items-center rounded-md text-dim hover:bg-hover hover:text-fg"><Icon name="back" size={13} /></button>
      </div>
      {repo ? (
        <>
          <RepoSwitcher ws={ws} current={repo} />
          <nav className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden px-2 py-2">
            {!connected.repos.includes(repo) ? (
              <p className="px-2 py-3 text-dim">Not connected.</p>
            ) : !isIndexed(repo) ? (
              <p className="px-2 py-3 text-dim">Not synced yet. <Link href={`/w/${ws}/sync`} className="text-accent underline underline-offset-2">Run a sync</Link> to ingest it.</p>
            ) : (
              <Files repo={repo} base={`/w/${ws}/${slug}`} active={file} />
            )}
          </nav>
        </>
      ) : (
        <>
          <div className="flex h-10 shrink-0 items-center px-3"><span className="label">Repositories</span></div>
          <nav className="min-h-0 flex-1 overflow-auto px-2">
            {repos.map((r) => (
              <Link key={r} href={`/w/${ws}/${repoSlug(r)}`} title={r} className="flex h-8 min-w-0 items-center gap-2 rounded-md px-2 text-mute hover:bg-hover hover:text-fg">
                <Icon name="repo" size={14} className="text-dim" /><span className="min-w-0 truncate">{r}</span>
                {!isIndexed(r) && <span className="ml-auto text-[11px] text-warn">not synced</span>}
              </Link>
            ))}
            {repos.length === 0 && <p className="px-2 py-3 text-dim">No repositories yet.</p>}
          </nav>
          <div className="border-t border-line p-2">
            <Link href={`/w/${ws}/settings/sources`} className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-mute hover:bg-hover hover:text-fg">
              <Icon name="plus" size={13} />Connect sources
            </Link>
          </div>
        </>
      )}
    </aside>
  );
}
