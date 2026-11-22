"use client";
import { useEffect } from "react";
import Answer from "./Answer";
import CodePane from "./CodePane";
import Evidence from "./Evidence";
import type { Investigation } from "@/lib/types";
import { CollapsedStrip, DEFAULT_SIZES, LIMITS, Splitter, useLayout } from "./layout";
import { Provider, useWb } from "./store";

function Layout() {
  const wb = useWb();
  const L = useLayout();
  const answerW = Math.min(L.answerW, Math.round(L.vw * 0.4)); // code never gets squeezed below ~60% of the window
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape") { if (L.evMax) L.toggleEvMax(); else { wb.selectNode(null); wb.setClaim(null); } }
      else if (e.key === "j") wb.stepNode(1);
      else if (e.key === "k") wb.stepNode(-1);
      else if (e.key === "1") wb.setTab("timeline");
      else if (e.key === "2") wb.setTab("graph");
      else if (e.key === "r") wb.replay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // keep the selected artifact in view when stepping with j/k
  useEffect(() => {
    if (wb.selected) document.querySelector(`[data-node="${wb.selected}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [wb.selected]);

  const evMax = Math.max(LIMITS.evH[0], Math.min(LIMITS.evH[1], (typeof window === "undefined" ? 900 : window.innerHeight) - 300));
  return (
    <div className="relative flex h-full min-w-0">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!(L.evMax && wb.inv) && <CodePane />}
        {wb.inv && L.evidenceOpen && !L.evMax && (
          <Splitter orientation="horizontal" invert label="Evidence height" value={L.evH} min={LIMITS.evH[0]} max={evMax} onChange={(v) => L.set({ evH: v })} onReset={() => L.set({ evH: DEFAULT_SIZES.evH })} />
        )}
        <Evidence />
      </div>
      {L.answerVisible ? (
        <>
          <Splitter orientation="vertical" invert label="Answer width" value={answerW} min={LIMITS.answerW[0]} max={Math.max(LIMITS.answerW[0], Math.min(LIMITS.answerW[1], Math.round(L.vw * 0.4)))} onChange={(v) => L.set({ answerW: v })} onReset={() => L.set({ answerW: DEFAULT_SIZES.answerW })} />
          <div style={{ width: answerW }} className="h-full min-w-0 shrink-0"><Answer /></div>
        </>
      ) : !L.focus && <CollapsedStrip side="right" label="Answer" hint="]" onOpen={L.toggleAnswer} busy={wb.running} />}
      {L.focus && (
        <button onClick={L.toggleFocus} className="absolute right-4 top-3 z-20 flex h-7 items-center gap-2 rounded-full border border-line2 bg-bg px-3 text-[11.5px] text-mute shadow-lg shadow-black/10 hover:text-fg">
          Code only <span className="kbd">z</span> exit
        </button>
      )}
    </div>
  );
}

export default function Workbench(props: { ws: string; repo: string; repoName: string; file: string | null; inv: Investigation | null }) {
  return <Provider {...props}><Layout /></Provider>;
}
