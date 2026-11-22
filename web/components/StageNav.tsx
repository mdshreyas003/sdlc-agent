"use client";
import { useEffect, useState } from "react";

// Presenter controls for the landing page: a dot rail on the right plus arrow / PageUp / PageDown keys that step one
// slide at a time. The scroller is #stage; each slide is a <section> whose id is in `slides`.
export default function StageNav({ slides }: { slides: readonly (readonly [string, string])[] }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const root = document.getElementById("stage");
    if (!root) return;
    const els = slides.map(([id]) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) setActive(els.indexOf(e.target as HTMLElement)); }),
      { root, threshold: 0.55 },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [slides]);

  const go = (i: number) => {
    const el = document.getElementById(slides[Math.max(0, Math.min(slides.length - 1, i))][0]);
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey || t?.closest("input, textarea, select, [contenteditable]")) return;
      const next = ["ArrowDown", "ArrowRight", "PageDown"].includes(e.key);
      const prev = ["ArrowUp", "ArrowLeft", "PageUp"].includes(e.key);
      if (!next && !prev) return;
      e.preventDefault();
      go(active + (next ? 1 : -1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <nav aria-label="Slides" className="fixed right-5 top-1/2 z-20 hidden -translate-y-1/2 flex-col gap-1 md:flex">
      {slides.map(([id, t], i) => (
        <button key={id} type="button" onClick={() => go(i)} aria-label={`Go to ${t}`} aria-current={i === active ? "true" : undefined} title={t} className="group flex h-5 w-5 items-center justify-center">
          <span className={`block rounded-full transition-all ${i === active ? "h-2.5 w-2.5 bg-accent" : "h-1.5 w-1.5 bg-line2 group-hover:bg-dim"}`} />
        </button>
      ))}
    </nav>
  );
}
