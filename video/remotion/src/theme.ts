import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

// 1:1 with render.py (Pillow) so Remotion segments drop into the same pipeline.
export const W = 1920;
export const H = 1080;
export const FPS = 30;

export const C = {
  BG: "#0B0F16",
  FG: "#F2F5FA",
  DIM: "#A0AABC",
  AC: "#7CB4FF",
  LINE: "#3A4558",
  CARD: "#161C28",
  INSET: "#0E1117", // render.py (14,17,23) — inner quote boxes
  WELL: "#0E1014", // render.py (14,16,20) — dashed memory / next boxes
} as const;

// Fonts are copies of the system files (see README) so the project is self-contained:
//   Inter          <- /usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf
//   JetBrains Mono <- /usr/share/fonts/truetype/sand-box/google/JetBrains Mono/JetBrainsMono-VariableFont_wght.ttf
export const SANS = "Inter";
export const MONO = "JetBrains Mono";

loadFont({ family: SANS, url: staticFile("fonts/Inter.ttf"), weight: "100 900" });
loadFont({ family: MONO, url: staticFile("fonts/JetBrainsMono.ttf"), weight: "100 800" });

// script.md rule: on-screen text never says "mail", "email" or "Slack" — always "discussion chats".
// render.py still said "Mailing lists" / "Mail"; flip these two constants to restore the old wording.
export const SOURCE_CHATS_LABEL = "Discussion chats";
export const SOURCE_CHATS_NODE = "Chat";
