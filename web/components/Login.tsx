"use client";
// /login: GitHub sign-in. With auth disabled (local default) there is nothing to sign in to: continue as the local user.
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { meApi } from "@/lib/api";
import { safeNext, useMe } from "@/lib/auth";
import { Icon } from "./icons";
import { Logo } from "./Logo";
import { Spinner, btnGhost, btnPrimary, errText, field } from "./ui";

const ERRORS: Record<string, string> = {
  denied: "GitHub sign-in was cancelled or refused.",
  state: "That sign-in link expired or was opened in another browser. Try again.",
  github_unreachable: "Could not reach GitHub. Try again in a moment.",
  bad_profile: "GitHub returned an unexpected profile. Try again.",
  not_configured: "GitHub sign-in is not configured on this server.",
  not_allowed: "This GitHub account is not allowed on this server. Ask its owner for access.",
};

/** Email + password: Sign in / Create account. There is no self-service reset; the operator runs `hackfront set-password`. */
function PasswordForm({ next, onDone }: { next: string; onDone: () => void }) {
  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [claimed, setClaimed] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      if (mode === "up") { const r = await meApi.signUp(email, password, name); setClaimed(r.claimed_workspaces); }
      else await meApi.signIn(email, password);
      await onDone();
    } catch (err) { setError(errText(err)); setBusy(false); }
  };
  void next;
  return (
    <form onSubmit={submit} className="space-y-3">
      <div role="tablist" className="mb-1 flex gap-4 border-b border-line text-[12.5px]">
        {([["in", "Sign in"], ["up", "Create account"]] as const).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={mode === k} onClick={() => { setMode(k); setError(""); }}
            className={`-mb-px h-8 ${mode === k ? "px-tab-active font-medium text-fg" : "text-dim hover:text-fg"}`}>{l}</button>
        ))}
      </div>
      {mode === "up" && <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional)" autoComplete="name" aria-label="Name" className={`${field} h-9 w-full font-sans text-[13px]`} />}
      <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" aria-label="Email" className={`${field} h-9 w-full font-sans text-[13px]`} />
      <input type="password" required minLength={mode === "up" ? 10 : 1} value={password} onChange={(e) => setPassword(e.target.value)}
        placeholder={mode === "up" ? "Password (10+ characters)" : "Password"} autoComplete={mode === "up" ? "new-password" : "current-password"} aria-label="Password" className={`${field} h-9 w-full font-sans text-[13px]`} />
      {error && <p role="alert" className="text-[12.5px] text-warn">{error}</p>}
      <button type="submit" disabled={busy} className={`${btnPrimary} h-10 w-full text-[13.5px]`}>{busy ? <Spinner /> : null}{mode === "up" ? "Create account" : "Sign in"}</button>
      <p className="text-[11.5px] text-dim">
        {mode === "up"
          ? (claimed ? "" : "The first account created on a server also takes ownership of workspaces that existed before accounts.")
          : "Forgot your password? There is no self-service reset: ask whoever runs this server to run `hackfront set-password`."}
      </p>
    </form>
  );
}

export default function Login() {
  const router = useRouter();
  const params = useSearchParams();
  const { me, loading, refresh } = useMe();
  const methods = me?.methods?.length ? me.methods : ["github" as const];
  const next = safeNext(params.get("next"));
  const code = params.get("error");
  const signedIn = !!me?.user && me.auth === "enabled";

  useEffect(() => { if (signedIn) router.replace(next); }, [signedIn, next, router]);

  return (
    <main className="grid h-full place-items-center bg-panel">
      <div className="px-halo grid h-full w-full place-items-center">
        <div className="card w-[400px] max-w-[92vw] p-8">
          <Link href="/" className="mb-4 inline-flex items-center gap-1 text-[12px] text-dim hover:text-fg"><Icon name="back" size={12} />Back to home</Link>
          <div className="mb-6 flex items-center gap-3">
            <Logo size={26} />
            <div>
              <h1 className="font-semibold leading-tight">Engineering Memory</h1>
              <p className="font-mono text-[11px] text-dim">why is this code the way it is?</p>
            </div>
          </div>

          {loading && <p className="flex items-center gap-2 text-dim"><Spinner />Checking session…</p>}

          {!loading && !me && <p role="alert" className="text-warn">Cannot reach the backend. Is <code className="font-mono">hackfront serve</code> running?</p>}

          {!loading && me?.auth === "enabled" && (
            <>
              <h2 className="text-[20px] font-semibold tracking-tight">Sign in</h2>
              <p className="mb-5 mt-1 text-mute">Your workspaces, sources and model keys are private to your account.</p>
              {code && <p role="alert" className="mb-4 rounded-md border border-warn/40 px-3 py-2 text-[12.5px] text-warn">{ERRORS[code] ?? "Sign-in failed. Try again."}</p>}
              {methods.includes("password") && <PasswordForm next={next} onDone={refresh} />}
              {methods.includes("password") && methods.includes("github") && <p className="my-4 flex items-center gap-3 text-[11px] uppercase tracking-wide text-dim"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></p>}
              {methods.includes("github") && (
                <>
                  <a href={`/api/auth/github/login?next=${encodeURIComponent(next)}`} className={`${methods.includes("password") ? btnGhost : btnPrimary} h-10 w-full text-[13.5px]`}>
                    <Icon name="github" size={16} />Continue with GitHub
                  </a>
                  <p className="mt-4 text-[11.5px] text-dim">We read your GitHub profile (name, avatar) to identify you. Source tokens are added later, per workspace.</p>
                </>
              )}
            </>
          )}

          {!loading && me?.auth === "disabled" && (
            <>
              <h2 className="text-[20px] font-semibold tracking-tight">Running as local user</h2>
              <p className="mb-5 mt-1 text-mute">Sign-in is not enabled on this server, so everything runs as one local user. Set the GitHub OAuth variables to turn accounts on.</p>
              <Link href={next} className={`${btnPrimary} h-10 w-full text-[13.5px]`}>Continue<Icon name="arrow" size={13} /></Link>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
