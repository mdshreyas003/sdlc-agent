"use client";
// /w/[ws]/setup: a guided checklist. Each step shows live status and links to the page that owns it
// (Sources and Model in Settings, Sync, then Ask). Nothing is configured here.
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { wsApi } from "@/lib/api";
import { repoSlug, useData } from "@/lib/data";
import { fileHref } from "@/lib/workspace";
import { Icon } from "./icons";
import { Chip, Notice, Spinner, btnGhost, btnPrimary, errText } from "./ui";

type StepState = "done" | "todo" | "blocked" | "running";
const started = new Set<string>(); // module-level: survives StrictMode's double effect and remounts
const DEMO_QUESTIONS = ["Why are gateway retries capped at 3?", "Why is the session TTL 15 minutes?"];
// Same four questions as data/kafka_demo_questions.json. The kafka workspace is demo:true, so it must not reuse the Acme prompts.
const KAFKA_QUESTIONS = [
  "Why are compacted topics not supported with tiered storage in the first version?",
  "Why does the metadata quorum implement its own Raft replication inside Kafka instead of using an existing library such as Apache Ratis?",
  "Why is the epoch used for leader election limited to 31 bits instead of being widened to 63 bits?",
  "Why did producers in 3.0 and 3.1 stay non-idempotent by default even though enable.idempotence defaults to true?",
];
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;
const SRC = { workspace: "this workspace", user: "your settings", server: "the server" } as const;

function Dot({ n, state }: { n: number; state: StepState }) {
  const base = "grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[12px] font-medium";
  if (state === "done") return <span className={`${base} border-ok bg-ok text-bg`}><Icon name="check" size={13} /></span>;
  if (state === "running") return <span className={`${base} border-accent text-accent`}><Spinner /></span>;
  return <span className={`${base} ${state === "blocked" ? "border-line text-dim/60" : "border-line2 text-mute"}`}>{n}</span>;
}

function Step({ n, title, state, summary, children }: { n: number; title: string; state: StepState; summary: string; children?: ReactNode }) {
  return (
    <li className={`card flex items-start gap-4 p-5 ${state === "blocked" ? "opacity-70" : ""}`}>
      <Dot n={n} state={state} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">{title}</h2>
          <Chip tone={state === "done" ? "ok" : state === "running" ? "run" : state === "blocked" ? "warn" : "dim"}>
            {state === "running" && <Spinner />}{{ done: "done", todo: "to do", blocked: "blocked", running: "running" }[state]}
          </Chip>
        </div>
        <p className="mt-0.5 text-[12.5px] text-dim">{summary}</p>
        {children && <div className="mt-3 flex flex-wrap items-center gap-2">{children}</div>}
      </div>
    </li>
  );
}

export default function Setup() {
  const router = useRouter();
  const auto = useSearchParams().get("auto") === "1";
  const { ws, info, status, sync, syncLoaded, startSync, connected } = useData();
  const [autoError, setAutoError] = useState("");
  const [opening, setOpening] = useState("");
  const [openError, setOpenError] = useState("");

  useEffect(() => {
    if (!auto || !ws || status !== "ready" || !syncLoaded || started.has(ws)) return;
    started.add(ws);
    router.replace(`/w/${encodeURIComponent(ws)}/sync`); // a reload must not start another run
    if (info?.workspace.demo || sync?.state === "running") return;
    startSync("standard").catch((e) => setAutoError(errText(e)));
  }, [auto, ws, status, syncLoaded, sync, startSync, router, info]);

  if (!ws || !info) return null;
  const demo = info.workspace.demo;
  const ints = info.integrations;
  const n = { repos: connected.repos.length, jira: connected.jira.length, slack: connected.slack.length };
  const hasTargets = n.repos + n.jira + n.slack > 0;
  const dbDown = !info.neo4j.ok;
  const indexed = info.indexed_repos;
  const running = sync?.state === "running";
  const s1 = hasTargets && (demo || (["github", "jira", "slack"] as const).some((k) => ints[k].configured));
  const s2 = info.providers.some((p) => p.configured);
  const s3 = indexed.length > 0 && !running;
  const ready = s1 && s2 && indexed.length > 0;
  const suggested = ws === "kafka" ? KAFKA_QUESTIONS : DEMO_QUESTIONS;
  const doneCount = [s1, s2, s3, false].filter(Boolean).length;

  const open = async (question?: string) => {
    const repo = indexed[0];
    if (!repo) return;
    setOpening(question ?? "open"); setOpenError("");
    const base = `/w/${ws}/${repoSlug(repo)}`;
    try {
      const first = (await wsApi.files(ws, repo)).files[0];
      router.push(first ? `${fileHref(base, first)}${question ? `?q=${encodeURIComponent(question)}` : ""}` : base);
    } catch (e) { setOpenError(errText(e)); setOpening(""); }
  };

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-[760px] px-8 py-10">
        <p className="label">Set up</p>
        <h1 className="mt-1 flex flex-wrap items-center gap-2 text-[24px] font-semibold tracking-tight">
          {info.workspace.name}{demo && <Chip tone="dim"><Icon name="flask" size={11} />demo</Chip>}
        </h1>
        <p className="mt-1 text-dim">{doneCount} of 4 steps done. Each step opens the page that owns it; come back here any time.</p>

        {dbDown && (
          <div className="mt-5 rounded-lg border border-warn/40 px-3 py-2">
            <Notice tone="warn">The graph database (Neo4j) is not reachable. Start it with <code className="font-mono">docker compose up -d</code>, check the NEO4J_* values in <code className="font-mono">.env</code>, restart the API and reload.</Notice>
          </div>
        )}

        <ol className="mt-6 space-y-3">
          <Step n={1} title="Connect sources" state={s1 ? "done" : "todo"}
            summary={demo ? "Demo data, pre-connected." : hasTargets ? [n.repos && plural(n.repos, "repo"), n.jira && plural(n.jira, "project"), n.slack && plural(n.slack, "channel")].filter(Boolean).join(" · ") : "GitHub, Jira, Slack: nothing connected yet."}>
            <Link href={`/w/${ws}/settings/sources`} className={s1 ? btnGhost : btnPrimary}>{s1 ? "Manage sources" : "Connect sources"}<Icon name="arrow" size={12} /></Link>
          </Step>
          <Step n={2} title="Choose a model" state={s2 ? "done" : "todo"}
            summary={s2 && info.model ? `${info.model.provider} / ${info.model.model} from ${SRC[info.model.source]}.` : "No model key yet. Add one under your account; every workspace of yours can use it."}>
            <Link href="/settings/models" className={s2 ? btnGhost : btnPrimary}>{s2 ? "Your models" : "Add a model key"}<Icon name="arrow" size={12} /></Link>
            <Link href={`/w/${ws}/settings/model`} className="text-[12px] text-dim hover:text-fg">Override for this workspace</Link>
          </Step>
          <Step n={3} title="Run a sync" state={running ? "running" : s3 ? "done" : s1 && !dbDown ? "todo" : "blocked"}
            summary={running ? `Running · ${sync?.totals.persisted ?? 0} stored.` : dbDown ? "Waiting for the database." : s3 ? (sync?.graph ? `${sync.graph.artifacts} items · ${sync.graph.edges} links in the graph.` : "History is in the graph.") : "Fetch history into the graph; every run keeps a log."}>
            <Link href={`/w/${ws}/sync`} className={running || !s3 ? btnPrimary : btnGhost}>{running ? "View progress" : s3 ? "Sync & history" : "Open Sync"}<Icon name="arrow" size={12} /></Link>
            {s3 && <Link href={`/w/${ws}/ingestion`} className="text-[12px] text-dim hover:text-fg">See ingestion</Link>}
            {autoError && <Notice tone="warn">{autoError}</Notice>}
          </Step>
          <Step n={4} title="Ask why" state={ready ? "todo" : "blocked"}
            summary={ready ? "Open a file and click a line, or start with a question." : `Still to do: ${[!s1 && "connect a source", !s2 && "add a model", indexed.length === 0 && "run a sync"].filter(Boolean).join(", ")}.`}>
            <button type="button" onClick={() => open()} disabled={!ready || !!opening} className={btnPrimary}>
              {opening === "open" ? <Spinner /> : <Icon name="arrow" size={12} />}Open workbench
            </button>
            {openError && <Notice tone="warn">{openError}</Notice>}
          </Step>
        </ol>

        {ready && demo && (
          <section className="mt-6" aria-label="Suggested questions">
            <p className="label mb-2">Or start with a question</p>
            <div className="flex flex-col items-start gap-2">
              {suggested.map((q) => (
                <button key={q} type="button" onClick={() => open(q)} disabled={!!opening}
                  className="inline-flex min-h-8 items-center gap-2 rounded-full border border-line px-3 py-1 text-left text-[12.5px] text-mute hover:border-line2 hover:text-fg disabled:opacity-40">
                  {opening === q ? <Spinner /> : <Icon name="help" size={12} />}{q}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
