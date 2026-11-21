"use client";
// /settings (the signed-in user): Profile, Models, Appearance. Models is where provider keys live for ALL of the user's
// workspaces; a workspace may override them (docs/accounts-and-settings-api.md).
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { meApi } from "@/lib/api";
import { useMe } from "@/lib/auth";
import type { ModelProvider, TestResult, UserModels } from "@/lib/types";
import { Icon } from "./icons";
import { SecretInput, TestLine } from "./Integrations";
import SettingsShell, { Panel, type Section } from "./SettingsShell";
import { Chip, Field, Notice, Spinner, btnGhost, btnPrimary, errText, field } from "./ui";

const SECTIONS: Section[] = [
  { key: "profile", label: "Profile", href: "/settings", icon: "user" },
  { key: "models", label: "Models", href: "/settings/models", icon: "spark" },
  { key: "appearance", label: "Appearance", href: "/settings/appearance", icon: "sun" },
];
const SOURCE_LABEL = { user: "Yours", server: "Server" } as const;

export default function UserSettings() {
  const path = usePathname();
  const tab = path.split("/")[2] ?? "profile";
  const active = SECTIONS.some((s) => s.key === tab) ? tab : "profile";
  return (
    <SettingsShell eyebrow="Settings" title="Your account" sections={SECTIONS} active={active}>
      {active === "profile" && <Profile />}
      {active === "models" && <Models />}
      {active === "appearance" && <Appearance />}
    </SettingsShell>
  );
}

function Profile() {
  const { me, signOut } = useMe();
  const u = me?.user;
  return (
    <>
      <Panel title="Profile" sub="Who you are signed in as.">
        <div className="flex items-center gap-4">
          {u?.avatar_url
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={u.avatar_url} alt="" width={48} height={48} className="h-12 w-12 rounded-full border border-line" />
            : <span className="grid h-12 w-12 place-items-center rounded-full bg-fg text-[18px] font-semibold text-bg">{(u?.name || u?.login || "L")[0].toUpperCase()}</span>}
          <div className="min-w-0">
            <p className="text-[15px] font-medium">{u?.name || u?.login || "Local user"}</p>
            <p className="font-mono text-[12px] text-dim">{u ? `@${u.login} · ${u.id}` : "local · sign-in is off"}</p>
          </div>
          {me?.auth === "enabled" && u && <button onClick={signOut} className={`${btnGhost} ml-auto`}><Icon name="logout" size={13} />Sign out</button>}
        </div>
      </Panel>
      <Panel title="What is private to you" sub="Accounts keep workspaces apart.">
        <ul className="space-y-2 text-[12.5px] text-mute">
          {[
            ["Workspaces", "only you can see, sync or delete the workspaces you create. Shared demos are read-only for everyone."],
            ["Source credentials", "GitHub, Jira and Slack tokens are stored per workspace, encrypted, and never shown again."],
            ["Model keys", "saved under your account in Models; no one else (and no other workspace owner) can use them."],
          ].map(([h, t]) => <li key={h} className="flex gap-2"><Icon name="shield" size={14} className="mt-0.5 text-ok" /><span><b className="font-medium text-fg">{h}</b>: {t}</span></li>)}
        </ul>
      </Panel>
    </>
  );
}

function Appearance() {
  const [theme, setTheme] = useState<"dark" | "light" | "system">("system");
  useEffect(() => {
    try { const t = localStorage.getItem("wb-theme"); setTheme(t === "light" || t === "dark" ? t : "system"); } catch { /* private mode */ }
  }, []);
  const pick = (t: "dark" | "light" | "system") => {
    const eff = t === "system" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : t;
    document.documentElement.dataset.theme = eff;
    try { if (t === "system") localStorage.removeItem("wb-theme"); else localStorage.setItem("wb-theme", t); } catch { /* private mode */ }
    setTheme(t);
  };
  return (
    <Panel title="Theme" sub="Stored in this browser only.">
      <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-3">
        {([["dark", "Dark", "moon"], ["light", "Light", "sun"], ["system", "System", "panel"]] as const).map(([k, l, ic]) => (
          <button key={k} role="radio" aria-checked={theme === k} onClick={() => pick(k)}
            className={`card flex h-20 flex-col items-start justify-between p-3 text-left ${theme === k ? "px-glow" : "card-link"}`}>
            <Icon name={ic} size={16} className="text-dim" /><span className="font-medium">{l}</span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- models
function Models() {
  const [m, setM] = useState<UserModels | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setM(await meApi.models()); setError(""); } catch (e) { setError(errText(e)); } }, []);
  useEffect(() => { load(); }, [load]);

  if (error) return <Notice tone="warn">{error}</Notice>;
  if (!m) return <p className="flex items-center gap-2 text-dim"><Spinner />Loading models…</p>;
  return (
    <>
      <Panel title="Effective model" sub="What a new workspace uses when it has no override.">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-[15px]">{m.default.provider}<span className="text-dim"> / </span>{m.default.model}</span>
          <Chip tone={m.default.source === "user" ? "run" : "dim"}>{SOURCE_LABEL[m.default.source]}</Chip>
        </div>
        <ol className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11.5px] text-dim" aria-label="Override order">
          {["Workspace override", "Your settings", "Server"].map((s, i) => (
            <li key={s} className="flex items-center gap-2">
              {i > 0 && <Icon name="right" size={11} />}
              <span className={`rounded border px-2 py-0.5 ${i === 1 ? "border-accent text-accent" : "border-line"}`}>{i + 1} · {s}</span>
            </li>
          ))}
        </ol>
        <p className="mt-2 text-[12px] text-dim">The first one that is set wins. This page edits step 2; each workspace can override it under its own Settings → Model.</p>
      </Panel>

      <DefaultPicker m={m} onSaved={setM} />
      {m.providers.map((p) => <ProviderCard key={p.name} p={p} onSaved={setM} isDefault={m.default.provider === p.name} />)}
    </>
  );
}

function DefaultPicker({ m, onSaved }: { m: UserModels; onSaved: (m: UserModels) => void }) {
  const ready = m.providers.filter((p) => p.configured);
  const [provider, setProvider] = useState(m.selected.provider);
  const [model, setModel] = useState(m.selected.model);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const dirty = provider !== m.selected.provider || model !== m.selected.model;
  const save = async () => {
    setBusy(true); setMsg(null);
    try { onSaved(await meApi.saveModels({ llm_provider: provider, llm_model: model.trim() })); setMsg({ ok: true, text: "Default saved" }); }
    catch (e) { setMsg({ ok: false, text: errText(e) }); } finally { setBusy(false); }
  };
  return (
    <Panel title="Your default" sub="Used by every workspace of yours that does not override it.">
      <form onSubmit={(e) => { e.preventDefault(); save(); }} className="grid max-w-[520px] grid-cols-2 gap-3">
        <Field label="Provider">
          <select value={provider} onChange={(e) => setProvider(e.target.value)} className={`${field} font-sans`}>
            <option value="">Automatic (first configured)</option>
            {ready.map((p) => <option key={p.name} value={p.name}>{p.label}</option>)}
          </select>
        </Field>
        <Field label="Model (optional)">
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="provider default" spellCheck={false} className={field} />
        </Field>
        <div className="col-span-2 flex items-center gap-2">
          <button type="submit" disabled={busy || !dirty} className={btnPrimary}>{busy && <Spinner />}Save default</button>
          {msg && <Notice tone={msg.ok ? "ok" : "warn"}>{msg.text}</Notice>}
          {ready.length === 0 && <Notice tone="dim">Add a key below first.</Notice>}
        </div>
      </form>
    </Panel>
  );
}

function ProviderCard({ p, isDefault, onSaved }: { p: ModelProvider; isDefault: boolean; onSaved: (m: UserModels) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState("");
  const dirty = Object.values(draft).some((v) => v.trim() !== "");

  const run = async (save: boolean) => {
    setBusy(true); setError(""); setResult(null);
    try {
      if (save) {
        const body: Record<string, string> = {};
        for (const f of p.fields) if (draft[f.key] !== undefined && (f.secret ? draft[f.key].trim() : draft[f.key].trim() !== (f.value ?? ""))) body[f.key] = draft[f.key].trim();
        if (Object.keys(body).length) onSaved(await meApi.saveModels(body));
        setDraft({});
      }
      setResult(await meApi.testModel(p.name));
    } catch (e) { setError(errText(e)); } finally { setBusy(false); }
  };

  return (
    <Panel title={p.label}
      sub={<span className="font-mono text-[11.5px]">{p.name} · {p.model}</span>}
      right={<span className="flex items-center gap-2">
        {isDefault && <Chip tone="run">default</Chip>}
        {p.configured ? <Chip tone="ok"><Icon name="check" size={11} />ready</Chip> : <Chip tone="dim">not set</Chip>}
        {p.source && <Chip tone="dim">{SOURCE_LABEL[p.source]}</Chip>}
      </span>}>
      {p.editable ? (
        <form onSubmit={(e) => { e.preventDefault(); run(true); }} className="max-w-[460px] space-y-3">
          {p.fields.map((f) => f.secret ? (
            <SecretInput key={f.key} id={`m-${f.key}`} label={f.label} state={{ set: f.set, source: f.set ? "workspace" : null, hint: f.hint }}
              value={draft[f.key] ?? ""} placeholder="Paste key" onChange={(v) => setDraft((d) => ({ ...d, [f.key]: v }))} />
          ) : (
            <Field key={f.key} label={f.label}>
              <input value={draft[f.key] ?? f.value ?? ""} placeholder="https://<resource>.openai.azure.com" spellCheck={false}
                onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))} className={field} />
            </Field>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <button type="submit" disabled={busy || (!dirty && !p.configured)} className={btnPrimary}>{busy && <Spinner />}{dirty ? "Save & test" : "Test"}</button>
            <span aria-live="polite" className="min-w-0"><TestLine result={result} error={error} /></span>
          </div>
          {p.source === "server" && <p className="text-[11.5px] text-dim">Currently using the server&apos;s key. Saving your own key takes precedence for your workspaces.</p>}
        </form>
      ) : (
        <div className="space-y-3">
          <p className="text-[12.5px] text-mute">Provided by this server. It is not editable here, but you can select it as your default.</p>
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => run(false)} disabled={busy || !p.configured} className={btnGhost}>{busy && <Spinner />}Test</button>
            <span aria-live="polite" className="min-w-0"><TestLine result={result} error={error} /></span>
          </div>
        </div>
      )}
    </Panel>
  );
}
