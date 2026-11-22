"use client";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { useData } from "@/lib/data";
import { Ready } from "./Gate";
import { Icon, type IconName } from "./icons";
import LeftPane from "./LeftPane";
import { CollapsedStrip, DEFAULT_SIZES, LIMITS, LayoutProvider, Splitter, useLayout } from "./layout";
import { Switcher, useLocation } from "./Shell";

/** Slim workspace navigation: Ask (workbench), Sync, Ingestion, Settings. The repo tree only shows on Ask routes. */
function Rail({ ws }: { ws: string }) {
  const { section } = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  // No saved choice: start collapsed on narrow windows (< 1180px), where every pixel beside the code matters.
  useEffect(() => { try { const v = localStorage.getItem("wb-rail"); setCollapsed(v === null ? window.innerWidth < 1180 : v === "1"); } catch {} }, []);
  const toggle = () => setCollapsed((c) => { const n = !c; try { localStorage.setItem("wb-rail", n ? "1" : "0"); } catch {} return n; });
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "[" && !e.metaKey && !e.ctrlKey && !e.altKey && !["INPUT", "TEXTAREA"].includes(t.tagName) && !t.isContentEditable) toggle();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, []);
  const { sync, info } = useData();
  const running = sync?.state === "running";
  const needsSetup = !!info && info.indexed_repos.length === 0 && !running;
  const items: { key: string; label: string; icon: IconName; href: string; on: boolean; dot?: "run" | "warn" }[] = [
    { key: "ask", label: "Ask", icon: "claude", href: `/w/${ws}`, on: !section || section === "setup" },
    { key: "sync", label: "Sync", icon: "replay", href: `/w/${ws}/sync`, on: section === "sync", dot: running ? "run" : needsSetup ? "warn" : undefined },
    { key: "ingestion", label: "Ingestion", icon: "layers", href: `/w/${ws}/ingestion`, on: section === "ingestion" },
    { key: "settings", label: "Settings", icon: "sliders", href: `/w/${ws}/settings`, on: section === "settings" },
  ];
  return (
    <aside className={`flex shrink-0 flex-col gap-3 border-r border-line bg-bg p-2.5 transition-[width] duration-150 ${collapsed ? "w-[64px]" : "w-[208px]"}`} aria-label="Workspace">
      <Switcher rail compact={collapsed} />
      <nav aria-label="Sections" className="flex flex-col gap-0.5">
        {!collapsed && <p className="label px-2 pb-1 pt-1">Workspace</p>}
        {items.map((i) => {
          const ask = i.key === "ask"; // Claude orange marks Ask, the agent
          const tone = ask ? "text-claude" : "text-accent";
          return (
            <Link key={i.key} href={i.href} aria-current={i.on ? "page" : undefined} aria-label={collapsed ? i.label : undefined} title={collapsed ? i.label : undefined}
              className={`relative flex h-9 items-center rounded-md ${collapsed ? "justify-center" : "gap-2.5 px-2.5"} ${i.on ? `${ask ? "bg-claude/10" : "bg-raised"} font-medium text-fg` : "text-mute hover:bg-hover hover:text-fg"}`}>
              {i.on && <span className={`absolute -left-2.5 top-2 h-5 w-[2px] rounded-full ${ask ? "bg-claude" : "bg-accent"}`} />}
              <Icon name={i.icon} size={ask ? 17 : 15} className={ask ? "text-claude" : i.on ? tone : "text-dim"} />
              {!collapsed && i.label}
              {i.dot && <span aria-hidden className={`${collapsed ? "absolute right-1.5 top-1.5" : "ml-auto"} h-[7px] w-[7px] rounded-full ${i.dot === "run" ? "px-ping bg-accent" : "bg-warn"}`} />}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto flex flex-col gap-2">
        {!collapsed && <p className="px-2 font-mono text-[10.5px] leading-snug text-dim">Repo + file: pick them inside Ask.</p>}
        <button onClick={toggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} title={`${collapsed ? "Expand" : "Collapse"} sidebar ([)`}
          className={`flex h-8 items-center rounded-md text-dim hover:bg-hover hover:text-fg ${collapsed ? "justify-center" : "gap-2.5 px-2.5"}`}>
          <Icon name="panel" size={15} />{!collapsed && <span className="text-[12px]">Collapse</span>}{!collapsed && <span className="kbd ml-auto">[</span>}
        </button>
      </div>
    </aside>
  );
}

/** The file tree beside the code: resizable, collapsible to a strip, or hidden in code-only mode. */
function Files({ ws }: { ws: string }) {
  const L = useLayout();
  if (L.focus) return null;
  if (!L.treeVisible) return <CollapsedStrip side="left" label="Files" hint="\" onOpen={L.toggleTree} />;
  return (
    <>
      <LeftPane ws={ws} />
      <Splitter orientation="vertical" label="Files width" value={L.treeW} min={LIMITS.treeW[0]} max={LIMITS.treeW[1]} onChange={(v) => L.set({ treeW: v })} onReset={() => L.set({ treeW: DEFAULT_SIZES.treeW })} />
    </>
  );
}

export default function WsFrame({ children }: { children: ReactNode }) {
  const { ws, section } = useLocation();
  return (
    <Ready>
      <LayoutProvider>
        <div className="flex h-full">
          <Rail ws={ws!} />
          {!section && <Files ws={ws!} />}
          <div className={`min-w-0 flex-1 ${section ? "bg-panel" : ""}`}>{children}</div>
        </div>
      </LayoutProvider>
    </Ready>
  );
}
