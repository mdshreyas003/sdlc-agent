"use client";
// Who is signed in (GET /api/me). With auth disabled (local default) everyone is the implicit local user and nothing
// redirects. With auth enabled, every route except `/` and `/login` sends a signed-out visitor to /login?next=<here>.
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { meApi } from "./api";
import type { Me } from "./types";

interface Auth {
  me: Me | null; // null until loaded or when the backend is unreachable
  loading: boolean;
  signedOut: boolean; // auth is on and nobody is signed in
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}
const Ctx = createContext<Auth>({ me: null, loading: true, signedOut: false, signOut: async () => {}, refresh: async () => {} });
export const useMe = () => useContext(Ctx);

export const PUBLIC_PATHS = ["/", "/login"];
/** Where sign-in returns to: a same-site relative path (never an absolute or protocol-relative URL), else the app. */
export const HOME = "/workspaces";
export const safeNext = (n: string | null | undefined) => (n && n.startsWith("/") && !n.startsWith("//") && !n.includes("\\") ? n : HOME);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try { setMe(await meApi.me()); } catch { setMe(null); } finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const signedOut = !!me && me.auth === "enabled" && !me.user;
  useEffect(() => {
    if (!signedOut || PUBLIC_PATHS.includes(path)) return;
    const here = typeof window === "undefined" ? path : path + window.location.search;
    router.replace(`/login?next=${encodeURIComponent(here)}`);
  }, [signedOut, path, router]);

  const signOut = useCallback(async () => {
    try { await meApi.logout(); } catch { /* the cookie may already be gone */ }
    await refresh();
    router.replace("/login");
  }, [refresh, router]);

  const value = useMemo(() => ({ me, loading, signedOut, signOut, refresh }), [me, loading, signedOut, signOut, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
