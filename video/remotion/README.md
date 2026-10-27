# Engineering Memory — Remotion scenes

Animated scenes for the hackathon video. Wired into `../rebuild.sh` (step 2): each composition
renders to `../seg/Sk.mp4` via the Remotion CLI. `S4` stays Playwright (`record_live.py` → `build_s4.py`).

| Composition | Source | Size / fps | Duration |
|---|---|---|---|
| `S1` `S2` `S3` `S5` `S6` `S7` `S8` `S9` | `src/scenes/Sk.tsx` | 1920×1080 @ 30 | `src/durations.ts` |

`S4` is not a Remotion composition.

## Preview

```bash
cd /workspace/video/remotion
npm install
npx remotion studio
npx remotion compositions
npx tsc --noEmit
```

After new Sarvam narration: `./scripts/sync-durations.sh` (reads `../aud/*.mp3`, writes `src/durations.ts`).
**S7–S9** use placeholders 65 / 55 / 50 s until those mp3s exist — re-measure before a final render.
Scene beat times still need retiming when narration length changes a lot.

## Pipeline render (via rebuild.sh)

`../rebuild.sh` syncs durations then runs, for each of S1 S2 S3 S5 S6 S7 S8 S9:

```bash
npx remotion render src/index.ts Sk ../seg/Sk.mp4 --codec h264 --crf 20 --pixel-format yuv420p --overwrite
```

Do not start a full rebuild unless you intend to render. Legacy Pillow `../render.py` remains as a fallback only.

## Layout

```
src/theme.ts       colors, Inter + JetBrains Mono, size/fps
src/motion.ts      enter / draw / stage / pop / exit (README §3 twelve principles)
src/primitives.tsx Scene, T, Tag, Box, Chip, Line, Dot
src/durations.ts   per-scene seconds (placeholders for S7–S9 until Sarvam TTS)
src/scenes/S*.tsx  one file per scene (S4.tsx is a placeholder comment only)
```
