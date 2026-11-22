"use client";
// The landing page's call to action. The page itself is static, so this small client piece reads the session:
// signed in -> "Open app"; otherwise "Sign in" (which returns to /workspaces, not back to this marketing page).
import Link from "next/link";
import { useMe } from "@/lib/auth";

export default function LandingCta({ className }: { className: string }) {
  const { me } = useMe();
  const signedIn = !!me?.user && me.auth === "enabled";
  return signedIn
    ? <Link href="/workspaces" className={className}>Open app</Link>
    : <Link href="/login?next=%2Fworkspaces" className={className}>Sign in</Link>;
}
