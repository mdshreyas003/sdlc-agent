"use client";
// Shared frame for the user Settings and the workspace Settings: a title, a vertical sub-nav of sections, one panel.
import Link from "next/link";
import type { ReactNode } from "react";
import { Icon, type IconName } from "./icons";

export interface Section { key: string; label: string; href: string; icon: IconName; danger?: boolean }

export default function SettingsShell({ eyebrow, title, sections, active, children }: {
  eyebrow: string; title: ReactNode; sections: Section[]; active: string; children: ReactNode;
}) {
  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto grid max-w-[1000px] grid-cols-[200px_minmax(0,1fr)] gap-10 px-8 py-10">
        <aside aria-label="Settings sections" className="sticky top-0 self-start">
          <p className="label">{eyebrow}</p>
          <h1 className="mt-1 break-words text-[20px] font-semibold leading-tight tracking-tight">{title}</h1>
          <nav className="mt-6 space-y-0.5">
            {sections.map((s) => (
              <Link key={s.key} href={s.href} aria-current={active === s.key ? "page" : undefined}
                className={`relative flex h-8 items-center gap-2.5 rounded-md px-2.5 ${active === s.key ? "bg-raised font-medium text-fg" : s.danger ? "text-dim hover:bg-hover hover:text-bad" : "text-mute hover:bg-hover hover:text-fg"}`}>
                {active === s.key && <span className="absolute -left-2 top-1.5 h-5 w-[2px] rounded-full bg-accent" />}
                <Icon name={s.icon} size={14} className={active === s.key ? "text-accent" : "text-dim"} />{s.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}

/** A titled panel inside a settings section. */
export function Panel({ title, sub, children, right }: { title: string; sub?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="card mb-5 overflow-hidden">
      <header className="flex items-start gap-3 border-b border-line px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="font-semibold">{title}</h2>
          {sub && <p className="mt-0.5 text-[12.5px] text-dim">{sub}</p>}
        </div>
        {right && <div className="ml-auto shrink-0">{right}</div>}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}
