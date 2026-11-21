"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import { useData } from "@/lib/data";
import { Ready } from "./Gate";
import { Icon, type IconName } from "./icons";
import LeftPane from "./LeftPane";
import { Switcher, useLocation } from "./Shell";

/** Slim workspace navigation: Ask (workbench), Sync, Ingestion, Settings. The repo tree only shows on Ask routes. */
function Rail({ ws }: { ws: string }) {
  const { section } = useLocation();
  const { sync, info } = useData();
  const running = sync?.state === "running";
  const needsSetup = !!info && info.indexed_repos.length === 0 && !running;
  const items: { key: string; label: string; icon: IconName; href: string; on: boolean; dot?: "run" | "warn" }[] = [
    { key: "ask", label: "Ask", icon: "help", href: `/w/${ws}`, on: !section || section === "setup" },
    { key: "sync", label: "Sync", icon: "replay", href: `/w/${ws}/sync`, on: section === "sync", dot: running ? "run" : needsSetup ? "warn" : undefined },
    { key: "ingestion", label: "Ingestion", icon: "layers", href: `/w/${ws}/ingestion`, on: section === "ingestion" },
    { key: "settings", label: "Settings", icon: "sliders", href: `/w/${ws}/settings`, on: section === "settings" },
  ];
  return (
    <aside className="flex w-[208px] shrink-0 flex-col gap-3 border-r border-line bg-bg p-2.5" aria-label="Workspace">
      <Switcher rail />
      <nav aria-label="Sections" className="flex flex-col gap-0.5">
        <p className="label px-2 pb-1 pt-1">Workspace</p>
        {items.map((i) => (
          <Link key={i.key} href={i.href} aria-current={i.on ? "page" : undefined}
            className={`relative flex h-9 items-center gap-2.5 rounded-md px-2.5 ${i.on ? "bg-raised font-medium text-fg" : "text-mute hover:bg-hover hover:text-fg"}`}>
            {i.on && <span className="absolute -left-2.5 top-2 h-5 w-[2px] rounded-full bg-accent" />}
            <Icon name={i.icon} size={15} className={i.on ? "text-accent" : "text-dim"} />
            {i.label}
            {i.dot && <span aria-hidden className={`ml-auto h-[7px] w-[7px] rounded-full ${i.dot === "run" ? "px-ping bg-accent" : "bg-warn"}`} />}
          </Link>
        ))}
      </nav>
      <p className="mt-auto px-2 font-mono text-[10.5px] leading-snug text-dim">Repo + file: pick them inside Ask.</p>
    </aside>
  );
}

export default function WsFrame({ children }: { children: ReactNode }) {
  const { ws, section } = useLocation();
  return (
    <Ready>
      <div className="flex h-full">
        <Rail ws={ws!} />
        {!section && <LeftPane ws={ws!} />}
        <div className={`min-w-0 flex-1 ${section ? "px-grid" : ""}`}>{children}</div>
      </div>
    </Ready>
  );
}
