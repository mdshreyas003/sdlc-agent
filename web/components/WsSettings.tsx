"use client";
// /w/[ws]/settings/<tab>: General · Sources · Model override · Danger. Credentials here belong to this workspace only.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { wsApi } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { useData } from "@/lib/data";
import { Icon } from "./icons";
import { LlmCard, Sources } from "./Integrations";
import SettingsShell, { Panel, type Section } from "./SettingsShell";
import { Chip, Notice, Spinner, btnGhost, btnPrimary, errText, field } from "./ui";

const SRC = { user: "your settings", server: "the server", workspace: "this workspace" } as const;

export default function WsSettings() {
  const path = usePathname();
  const { ws, info } = useData();
  if (!ws || !info) return null;
  const tab = path.split("/")[4] ?? "general";
  const base = `/w/${ws}/settings`;
  const sections: Section[] = [
    { key: "general", label: "General", href: base, icon: "sliders" },
    { key: "sources", label: "Sources", href: `${base}/sources`, icon: "repo" },
    { key: "model", label: "Model", href: `${base}/model`, icon: "spark" },
    { key: "danger", label: "Danger zone", href: `${base}/danger`, icon: "alert", danger: true },
  ];
  const active = sections.some((s) => s.key === tab) ? tab : "general";
  return (
    <SettingsShell eyebrow="Workspace settings" title={info.workspace.name} sections={sections} active={active}>
      {active === "general" && <General />}
      {active === "sources" && <Panel title="Sources" sub="Credentials and what to sync. Tokens are write-only and belong to this workspace."><Sources /></Panel>}
      {active === "model" && <ModelOverride />}
      {active === "danger" && <Danger />}
    </SettingsShell>
  );
}

function useRow() {
  const { ws, workspaces } = useData();
  return workspaces?.find((w) => w.slug === ws);
}

function General() {
  const { ws, info, saveTargets, refreshWorkspaces } = useData();
  const row = useRow();
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!ws || !info) return null;
  const locked = info.workspace.demo || row?.shared;
  const cur = name ?? info.workspace.name;
  const save = async () => {
    setBusy(true); setMsg(null);
    try { await saveTargets({ name: cur.trim() }); await refreshWorkspaces(); setName(null); setMsg({ ok: true, text: "Saved" }); }
    catch (e) { setMsg({ ok: false, text: errText(e) }); } finally { setBusy(false); }
  };
  return (
    <>
      <Panel title="Name">
        <form onSubmit={(e) => { e.preventDefault(); save(); }} className="flex max-w-[460px] items-center gap-2">
          <input value={cur} onChange={(e) => setName(e.target.value)} disabled={locked} maxLength={80} aria-label="Workspace name" className={field} />
          <button type="submit" disabled={busy || locked || !cur.trim() || cur.trim() === info.workspace.name} className={btnPrimary}>{busy && <Spinner />}Save</button>
        </form>
        {msg && <div className="mt-2"><Notice tone={msg.ok ? "ok" : "warn"}>{msg.text}</Notice></div>}
        {locked && <div className="mt-2"><Notice tone="dim">Demo setup is locked.</Notice></div>}
      </Panel>
      <Panel title="Access" sub="Workspaces are separated per account.">
        <dl className="grid grid-cols-[120px_1fr] gap-y-2 text-[12.5px]">
          <dt className="text-dim">Id</dt><dd className="font-mono">{ws}</dd>
          <dt className="text-dim">Visibility</dt>
          <dd>{row?.shared ? <Chip tone="dim"><Icon name="flask" size={11} />shared demo · read-only</Chip> : <Chip tone="ok"><Icon name="lock" size={11} />private to you</Chip>}</dd>
        </dl>
      </Panel>
      <Panel title="Elsewhere">
        <div className="flex flex-wrap gap-2">
          <Link href={`/w/${ws}/sync`} className={btnGhost}><Icon name="replay" size={13} />Sync &amp; run history</Link>
          <Link href={`/w/${ws}/ingestion`} className={btnGhost}><Icon name="layers" size={13} />Ingestion</Link>
          <Link href="/settings/models" className={btnGhost}><Icon name="spark" size={13} />Your models</Link>
        </div>
      </Panel>
    </>
  );
}

function ModelOverride() {
  const { ws, info, refresh } = useData();
  const { me } = useMe();
  const row = useRow();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!ws || !info) return null;
  const sec = info.integrations.llm.secrets;
  const overridden = ["azure_endpoint", "azure_key", "sarvam_key", "llm_provider", "llm_model"].some((k) => sec[k]?.source === "workspace");
  const m = info.model;
  const shared = info.workspace.demo && (row?.shared || me?.auth === "enabled");

  const clear = async () => {
    setBusy(true); setMsg(null);
    try {
      await wsApi.saveSecrets(ws, { azure_endpoint: "", azure_key: "", sarvam_key: "", llm_provider: "", llm_model: "" });
      await refresh(); setMsg({ ok: true, text: "Override removed" });
    } catch (e) { setMsg({ ok: false, text: errText(e) }); } finally { setBusy(false); }
  };

  return (
    <>
      <Panel title="Model used here" sub="Resolution order: this workspace → your settings → server.">
        {m ? (
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-mono text-[15px]">{m.provider}<span className="text-dim"> / </span>{m.model}</span>
            <Chip tone={m.source === "workspace" ? "run" : "dim"}>from {SRC[m.source]}</Chip>
          </div>
        ) : <p className="text-dim">No model resolved yet.</p>}
        {!info.providers.some((p) => p.configured) && <div className="mt-3"><Notice tone="warn">No model is configured. Add a key in <Link href="/settings/models" className="underline">your model settings</Link> or override it below.</Notice></div>}
        <p className="mt-3 text-[12px] text-dim">Your shared default lives in <Link href="/settings/models" className="text-accent underline underline-offset-2">Settings → Models</Link>. Override it here only if this workspace needs a different provider, key or model.</p>
      </Panel>
      <Panel title="Workspace override" right={overridden ? <button onClick={clear} disabled={busy || shared} className={btnGhost}>{busy && <Spinner />}Remove override</button> : <Chip tone="dim">inherits</Chip>}>
        {shared ? <Notice tone="dim">This is a shared demo, so it cannot hold its own keys. It uses your model settings.</Notice> : <LlmCard />}
        {msg && <div className="mt-2"><Notice tone={msg.ok ? "ok" : "warn"}>{msg.text}</Notice></div>}
      </Panel>
    </>
  );
}

function Danger() {
  const router = useRouter();
  const { ws, info } = useData();
  const row = useRow();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!ws || !info) return null;
  const blocked = row?.shared || (info.workspace.demo && row?.owned === false);
  const remove = async () => {
    setBusy(true); setError("");
    try { await wsApi.remove(ws); router.push("/workspaces"); } catch (e) { setError(errText(e)); setBusy(false); }
  };
  return (
    <section className="card overflow-hidden border-bad/40">
      <header className="border-b border-bad/30 px-5 py-3.5"><h2 className="font-semibold text-bad">Delete workspace</h2></header>
      <div className="space-y-3 px-5 py-4">
        <p className="text-[12.5px] text-mute">Removes this workspace&apos;s configuration, saved credentials, sync history and stored questions. Graph data that other workspaces may share is left alone. This cannot be undone.</p>
        {blocked ? <Notice tone="dim">A shared demo cannot be deleted.</Notice> : (
          <form onSubmit={(e) => { e.preventDefault(); remove(); }} className="flex max-w-[460px] items-center gap-2">
            <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={`Type “${info.workspace.name}” to confirm`} aria-label="Confirm workspace name" className={field} />
            <button type="submit" disabled={busy || typed !== info.workspace.name}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-bad px-4 text-[12.5px] font-medium text-bg hover:opacity-90 disabled:opacity-40">{busy && <Spinner />}<Icon name="trash" size={13} />Delete</button>
          </form>
        )}
        {error && <Notice tone="warn">{error}</Notice>}
      </div>
    </section>
  );
}
