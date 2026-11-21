"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { repoSlug, useData, useRepoFiles } from "@/lib/data";
import { decodeSeg, fileHref } from "@/lib/workspace";
import { useMe } from "@/lib/auth";
import { Icon, type IconName } from "./icons";
import { Logo } from "./Logo";

/** Workspace pages that live beside the repo routes: /w/[ws]/<section>/... */
export const SECTIONS = ["setup", "sync", "ingestion", "settings"] as const;
export type Section = (typeof SECTIONS)[number];
const SECTION_LABEL: Record<Section, string> = { setup: "Set up", sync: "Sync", ingestion: "Ingestion", settings: "Settings" };

/** Parse /w/[ws]/[repo]/(f|why)/... or /w/[ws]/<section> into its parts. */
export function useLocation() {
  const path = usePathname();
  const { investigations } = useData();
  const [, w, ws, seg, kind, ...rest] = path.split("/");
  const section = (SECTIONS as readonly string[]).includes(seg) ? (seg as Section) : undefined;
  const repo = section ? undefined : seg;
  const file = kind === "f" ? rest.map(decodeSeg).join("/") : kind === "why" ? investigations.find((i) => i.id === rest[0])?.file ?? undefined : undefined;
  return { ws: w === "w" ? ws : undefined, repo, section, file };
}

function useTheme() {
  const [theme, set] = useState<"light" | "dark">("dark");
  useEffect(() => { set(document.documentElement.dataset.theme === "light" ? "light" : "dark"); }, []);
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("wb-theme", next); } catch {}
    set(next);
  };
  return [theme, toggle] as const;
}

/** Workspace switcher. `rail` = the full-width block at the top of the workspace sidebar (its one home). */
export function Switcher({ rail = false }: { rail?: boolean }) {
  const { ws } = useLocation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { info, workspaces } = useData();
  const cur = info?.workspace;
  useEffect(() => {
    const on = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", on);
    return () => document.removeEventListener("mousedown", on);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} title={cur?.name}
        className={rail ? "flex h-11 w-full items-center gap-2.5 rounded-lg border border-line bg-bg px-2 text-left hover:border-line2" : "flex h-8 items-center gap-2 rounded-md pl-1.5 pr-2 hover:bg-hover"}>
        {cur && <span className={`grid shrink-0 place-items-center rounded bg-fg font-semibold text-bg ${rail ? "h-7 w-7 text-[13px]" : "h-5 w-5 text-[11px]"}`}>{cur.name[0]?.toUpperCase()}</span>}
        <span className="min-w-0 flex-1">
          {rail && <span className="block font-mono text-[10px] uppercase leading-none tracking-wide text-dim">Workspace</span>}
          <span className="block truncate font-medium leading-tight">{cur?.name ?? "Workspaces"}</span>
        </span>
        <Icon name="updown" size={12} className="shrink-0 text-dim" />
      </button>
      {open && (
        <div role="menu" className={`fade-up absolute left-0 z-40 rounded-lg border border-line2 bg-bg p-1 shadow-xl shadow-black/20 ${rail ? "top-12 w-[240px]" : "top-9 w-56"}`}>
          <div className="max-h-[260px] overflow-auto">
            {(workspaces ?? (cur ? [{ slug: cur.slug, name: cur.name }] : [])).map((w) => (
              <Link key={w.slug} href={`/w/${w.slug}`} onClick={() => setOpen(false)} role="menuitem"
                className="flex h-8 items-center gap-2 rounded-md px-2 hover:bg-hover">
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-raised text-[11px] font-semibold">{w.name[0]?.toUpperCase()}</span>
                <span className="truncate">{w.name}</span>{w.slug === ws && <Icon name="check" size={13} className="ml-auto shrink-0 text-dim" />}
              </Link>
            ))}
          </div>
          <div className="my-1 border-t border-line" />
          <Link href="/workspaces" onClick={() => setOpen(false)} role="menuitem" className="flex h-8 items-center gap-2 rounded-md px-2 text-mute hover:bg-hover hover:text-fg">
            <Icon name="home" size={13} />Manage workspaces
          </Link>
        </div>
      )}
    </div>
  );
}

function UserMenu() {
  const { me, signOut } = useMe();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const on = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", on); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", on); document.removeEventListener("keydown", key); };
  }, [open]);
  const u = me?.user;
  const label = u?.name || u?.login || "Local user";
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} aria-label="Account menu"
        className="grid h-8 w-8 place-items-center overflow-hidden rounded-full border border-line hover:border-line2">
        {u?.avatar_url
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={u.avatar_url} alt="" width={32} height={32} className="h-full w-full object-cover" />
          : <span className="text-[12px] font-semibold">{label[0].toUpperCase()}</span>}
      </button>
      {open && (
        <div role="menu" className="fade-up absolute right-0 top-10 z-40 w-56 rounded-lg border border-line2 bg-bg p-1 shadow-xl shadow-black/20">
          <div className="px-2 py-1.5">
            <p className="truncate font-medium">{label}</p>
            <p className="truncate font-mono text-[11px] text-dim">{u ? `@${u.login}` : "sign-in is off"}</p>
          </div>
          <div className="my-1 border-t border-line" />
          {([["/settings", "Settings", "sliders"], ["/settings/models", "Models", "spark"], ["/workspaces", "Workspaces", "home"]] as const).map(([href, l, ic]) => (
            <Link key={href} href={href} onClick={() => setOpen(false)} role="menuitem" className="flex h-8 items-center gap-2 rounded-md px-2 text-mute hover:bg-hover hover:text-fg">
              <Icon name={ic} size={13} />{l}
            </Link>
          ))}
          {me?.auth === "enabled" && u && (
            <>
              <div className="my-1 border-t border-line" />
              <button onClick={() => { setOpen(false); signOut(); }} role="menuitem" className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-mute hover:bg-hover hover:text-fg">
                <Icon name="logout" size={13} />Sign out
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const pageTitle = (path: string) => (path.startsWith("/settings") ? "Settings" : path.startsWith("/workspaces") ? "Workspaces" : "");

function Topbar({ onPalette }: { onPalette: () => void }) {
  const path = usePathname();
  const { info } = useData();
  const { ws, repo, section, file } = useLocation();
  const [theme, toggle] = useTheme();
  const parts = file?.split("/") ?? [];
  return (
    <header className="flex h-12 shrink-0 items-center gap-1.5 border-b border-line px-3">
      <Link href="/workspaces" aria-label="All workspaces" className="grid h-8 w-8 place-items-center rounded-md hover:bg-hover">
        <Logo />
      </Link>
      {/* Inside a workspace the switcher lives in the sidebar; the bar only says where you are. */}
      {!ws && <><span className="text-line2">/</span><span className="font-medium">{pageTitle(path)}</span></>}
      {ws && (repo || section) && (
        <nav aria-label="Location" className="flex min-w-0 items-center gap-1.5 text-[12.5px]">
          <Link href={`/w/${ws}`} className="max-w-[160px] truncate text-dim hover:text-fg">{info?.workspace.name ?? ws}</Link>
          <span className="text-line2">/</span>
          <Link href={`/w/${ws}/${section ?? repo}`} className={`font-medium ${parts.length ? "text-mute hover:text-fg" : ""}`}>{section ? SECTION_LABEL[section] : repo}</Link>
          {parts.map((p, i) => (
            <Fragment key={i}><span className="text-line2">/</span><span className={`truncate font-mono text-[12px] ${i === parts.length - 1 ? "text-fg" : "text-dim"}`}>{p}</span></Fragment>
          ))}
        </nav>
      )}
      <div className="ml-auto flex items-center gap-1.5">
        <button onClick={onPalette} className="flex h-8 items-center gap-2 rounded-md border border-line bg-bg pl-2.5 pr-1.5 text-dim hover:border-line2 hover:text-mute">
          <Icon name="search" size={13} />Search<span className="kbd">Ctrl K</span>
        </button>
        <button onClick={toggle} aria-label="Toggle theme" className="grid h-8 w-8 place-items-center rounded-md text-dim hover:bg-hover hover:text-fg">
          <Icon name={theme === "dark" ? "sun" : "moon"} size={14} />
        </button>
        <UserMenu />
      </div>
    </header>
  );
}

interface Item { group: string; label: string; hint?: string; icon: IconName; href: string }

function Palette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const { repo: slug } = useLocation();
  const { ws, info, investigations, repos, repoByslug, workspaces } = useData();
  // ponytail: investigations carry no repo, so questions open under the current (else first) repo
  const repoName = (slug && repoByslug(slug)) || repos[0];
  const base = `/w/${ws}/${repoName ? repoSlug(repoName) : ""}`;
  const files = useRepoFiles(open ? repoName : undefined).data?.files;
  const [q, setQ] = useState("");
  const [i, setI] = useState(0);
  useEffect(() => { if (open) { setQ(""); setI(0); } }, [open]);

  const items = useMemo<Item[]>(() => {
    const all: Item[] = [
      ...(ws && repoName ? investigations.map((v) => ({ group: "Questions", label: v.question, hint: v.file?.split("/").pop(), icon: "help" as const, href: `${base}/why/${v.id}` })) : []),
      ...(workspaces ?? (info ? [info.workspace] : [])).map((w) => ({ group: "Workspaces", label: w.name, icon: "home" as const, href: `/w/${w.slug}` })),
      ...(ws ? repos.map((r) => ({ group: "Repositories", label: r, icon: "repo" as const, href: `/w/${ws}/${repoSlug(r)}` })) : []),
      ...(ws ? [
        { group: "Go to", label: "Sync", icon: "replay" as const, href: `/w/${ws}/sync` },
        { group: "Go to", label: "Ingestion", icon: "layers" as const, href: `/w/${ws}/ingestion` },
        { group: "Go to", label: "Workspace settings", icon: "sliders" as const, href: `/w/${ws}/settings` },
        { group: "Go to", label: "Set up this workspace", icon: "list" as const, href: `/w/${ws}/setup` },
      ] : []),
      { group: "Go to", label: "Workspaces", icon: "home" as const, href: "/workspaces" },
      { group: "Go to", label: "Settings", icon: "user" as const, href: "/settings" },
      { group: "Go to", label: "Models", icon: "spark" as const, href: "/settings/models" },
      ...(ws && repoName ? (files ?? []).map((p) => ({ group: "Files", label: p, icon: "file" as const, href: fileHref(base, p) })) : []),
    ];
    const s = q.trim().toLowerCase();
    return (s ? all.filter((x) => x.label.toLowerCase().includes(s)) : all.filter((x) => x.group !== "Files")).slice(0, 30);
  }, [q, base, ws, repoName, investigations, info, workspaces, repos, files]);

  if (!open) return null;
  const go = (it?: Item) => { if (it) { router.push(it.href); onClose(); } };
  return (
    <div className="fixed inset-0 z-50 grid place-items-start justify-center bg-black/40 pt-[14vh] backdrop-blur-[2px]" onMouseDown={onClose}>
      <div role="dialog" aria-label="Search" onMouseDown={(e) => e.stopPropagation()}
        className="fade-up w-[540px] max-w-[92vw] overflow-hidden rounded-xl border border-line2 bg-bg shadow-2xl shadow-black/30">
        <div className="flex items-center gap-2 border-b border-line px-3">
          <Icon name="search" size={14} className="text-dim" />
          <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setI(0); }} placeholder="Search files, questions, repos…"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setI((x) => Math.min(items.length - 1, x + 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setI((x) => Math.max(0, x - 1)); }
              if (e.key === "Enter") go(items[i]);
              if (e.key === "Escape") onClose();
            }}
            className="h-11 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-dim" />
        </div>
        <ul className="max-h-[340px] overflow-auto p-1.5">
          {items.length === 0 && <li className="p-4 text-center text-dim">No results</li>}
          {items.map((it, n) => (
            <li key={it.group + it.href}>
              {(n === 0 || items[n - 1].group !== it.group) && <div className="label px-2 pb-1 pt-2.5">{it.group}</div>}
              <button onClick={() => go(it)} onMouseMove={() => setI(n)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left ${n === i ? "bg-raised text-fg" : "text-mute"}`}>
                <Icon name={it.icon} size={13} className="text-dim" /><span className="truncate">{it.label}</span>
                {it.hint && <span className="ml-auto shrink-0 font-mono text-[11px] text-dim">{it.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Compact strip while this workspace's ingestion runs; links to the live progress. */
function SyncBanner() {
  const { ws, sync } = useData();
  const { section } = useLocation();
  if (!ws || sync?.state !== "running" || section === "sync" || section === "setup") return null;
  const done = sync.streams.filter((s) => s.status !== "running").length;
  return (
    <div role="status" className="flex h-8 shrink-0 items-center gap-2 border-b border-line bg-panel px-4 text-[12px] text-mute">
      <span aria-hidden className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-accent border-t-transparent" />
      Syncing · {sync.totals.fetched} fetched · {done}/{sync.streams.length} streams
      <Link href={`/w/${ws}/sync`} className="ml-auto text-accent underline underline-offset-2">View progress</Link>
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  const [palette, setPalette] = useState(false);
  const { signedOut, loading } = useMe();
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); } };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  const pathname = usePathname();
  const gridPage = pathname.startsWith("/workspaces") || pathname.startsWith("/settings"); // thin-grid backdrop
  const bare = pathname === "/" || pathname === "/login" || pathname.startsWith("/prototype"); // these bring their own chrome
  if (bare) return <div className="h-screen min-w-[1000px]">{children}</div>;
  if (loading || signedOut) return <main className="grid h-screen place-items-center text-dim" aria-busy><h1 className="sr-only">Engineering Memory</h1>Loading…</main>; // signed-out visitors are sent to /login
  return (
    <>
      <div className="flex h-screen min-w-[1000px] flex-col">
        <Topbar onPalette={() => setPalette(true)} />
        <SyncBanner />
        <main className={`min-h-0 flex-1 ${gridPage ? "px-grid" : ""}`}>{children}</main>
      </div>
      <Palette open={palette} onClose={() => setPalette(false)} />
    </>
  );
}
