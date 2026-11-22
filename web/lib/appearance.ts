// Per-browser look-and-feel preferences. Applied as data attributes on <html> (CSS in globals.css reads them); the same
// keys are read by the inline script in app/layout.tsx before first paint, so there is no flash. UI only.
export const ACCENTS = [
  { key: "blue", label: "Blue", light: "#4353e8", dark: "#8b9bff" },
  { key: "violet", label: "Violet", light: "#7048e8", dark: "#a78bfa" },
  { key: "teal", label: "Teal", light: "#0b8a7a", dark: "#2dd4bf" },
  { key: "orange", label: "Orange", light: "#c2570c", dark: "#fb923c" },
  { key: "rose", label: "Rose", light: "#d6336c", dark: "#fb7185" },
] as const;
export type Accent = (typeof ACCENTS)[number]["key"];
export type Contrast = "standard" | "high";
export type Font = "geist" | "system";
export interface Appearance { accent: Accent; contrast: Contrast; font: Font }

export const DEFAULT_APPEARANCE: Appearance = { accent: "blue", contrast: "standard", font: "geist" };
const KEY = { accent: "wb-accent", contrast: "wb-contrast", font: "wb-font" } as const;

export function readAppearance(): Appearance {
  try {
    const a = localStorage.getItem(KEY.accent), c = localStorage.getItem(KEY.contrast), f = localStorage.getItem(KEY.font);
    return {
      accent: ACCENTS.some((x) => x.key === a) ? (a as Accent) : "blue",
      contrast: c === "high" ? "high" : "standard",
      font: f === "system" ? "system" : "geist",
    };
  } catch { return DEFAULT_APPEARANCE; }
}

/** Apply and remember. Defaults remove the attribute and the stored key, so a reset leaves nothing behind. */
export function setAppearance(patch: Partial<Appearance>): Appearance {
  const next = { ...readAppearance(), ...patch };
  const root = document.documentElement;
  for (const k of ["accent", "contrast", "font"] as const) {
    const isDefault = next[k] === DEFAULT_APPEARANCE[k];
    if (isDefault) root.removeAttribute(`data-${k}`); else root.setAttribute(`data-${k}`, next[k]);
    try { if (isDefault) localStorage.removeItem(KEY[k]); else localStorage.setItem(KEY[k], next[k]); } catch { /* private mode */ }
  }
  return next;
}
