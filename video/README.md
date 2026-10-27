# Engineering Memory — video how-to

Working folder: `/workspace/video/`

**Story source of truth:** `script.md` — it is its own file in this folder. All story and wording changes go there first, before any TTS or render.

**Locked stack:** Remotion (`remotion/`) for animated scenes, Playwright for the live demo, `rebuild.sh` for concat / encode / subtitles, Sarvam Instant Voice Cloning via `tts.py` (voice `svc-3f50a02f-39c5-4325-9037-13daa5bdc7e2` in `aud/clone/`), `script.md` for the script.

Remotion lives at `remotion/` (S1–S3, S5–S9 compositions; S4 is Playwright). `rebuild.sh` step 2 renders those compositions to `seg/`. Legacy Pillow path `render.py` remains as fallback only. `tts.py` calls Sarvam Instant Voice Cloning (not edge-tts). Final file must stay under **25 MB**.

---

## 1. How to render

Do this from `/workspace/video/`. Use the local `venv`.

### A. Edit the story
1. Change the words in `script.md` (one `## S…` section = one segment).
2. Keep segment IDs in sync with `alist.txt` / `vlist.txt` (S1–S9).

### B. Voice (per segment or all) — Sarvam Instant Voice Cloning
```bash
venv/bin/python tts.py          # all segments in script.md
venv/bin/python tts.py S3       # one segment
```
Uses voice ID from `aud/clone/voice_id.txt` (`svc-3f50a02f-39c5-4325-9037-13daa5bdc7e2`), pace 0.95, writes `aud/Sk.mp3` + `aud/Sk.srt`. Then pad to wav:
`D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 aud/Sk.mp3); ffmpeg -y -i aud/Sk.mp3 -af apad -t "$(python3 -c "print($D+0.3)")" -ar 48000 -ac 2 aud/Sk.wav`

### C. Animated segments (non-demo)
Animated segments S1, S2, S3, S5, S6, S7, S8, S9 are rendered by Remotion inside `./rebuild.sh` (not S4).

Manual one-off:
```bash
cd remotion && ./scripts/sync-durations.sh
npx remotion render src/index.ts Sk ../seg/Sk.mp4 --codec h264 --crf 20 --overwrite
```

Legacy Pillow `render.py` still writes `seg/Sk.mp4` if you need a fallback. **S7–S9 durations** in `remotion/src/durations.ts` are placeholders (65 / 55 / 50) until Sarvam TTS mp3s exist — re-measure before a final render.

### D. Live demo segment (S4) — Playwright
Only when the hosted Kafka workspace has the saved investigation:

```bash
venv/bin/python record_live.py
# optional live ask: venv/bin/python record_live.py --ask
./rebuild.sh marks_live.json
```

`record_live.py` writes `rec_live/*.webm` + `marks_live.json`. `rebuild.sh` calls `build_s4.py` to cut that into `seg/S4.mp4`.

Local fallback (old footage): `./rebuild.sh marks_local.json`

### E. Final stitch (always)
```bash
./rebuild.sh [marks.json]
```

That script: picks S4 narration variant → may re-tts S4 → builds S4 clip → `subs.py` → mixes voice + quiet bed → concatenates `vlist.txt` → burns Inter subtitles → encodes H.264 (CRF 22→31) until ≤25 MB → copies:

- `engineering-memory-hackathon.mp4`
- `engineering-memory-hackathon.srt`

Check frames land in `out/frames/`.

### Three-second slice (re-render one beat)
1. Fix the line in `script.md` for that `Sk`.
2. Re-tts only that segment.
3. Re-render only that `seg/Sk.mp4` (or re-record S4 if it’s the demo).
4. Run `./rebuild.sh` — do not re-do untouched segments.

---

## 2. Where to change things

| You want to change… | Touch this |
|---|---|
| Story, wording, segment order | `script.md` |
| Demo narration variants (local / live / live_ask) | `s4_variants.json` (and `script.md` S4 via `rebuild.sh`) |
| Animated scenes (Remotion, preferred) | `remotion/` (S1–S3, S5–S9) → `seg/Sk.mp4` via `rebuild.sh` |
| Animated scenes (Pillow fallback) | `render.py` |
| Live demo clicks, URL, Q041 flow | `record_live.py` (or `record.py` for local) |
| How the demo webm is cut into S4 | `build_s4.py` + the marks JSON |
| Subtitle style / timing assembly | `subs.py` (fonts: Inter) |
| Final concat, audio bed, burn-in, size ≤25 MB | `rebuild.sh` |
| Voice engine / clone ID | `tts.py` (Sarvam clone); ID + sample in `aud/clone/voice_id.txt` and `voice_meta.json` |
| Segment list for concat | `alist.txt` (audio), `vlist.txt` (video) |

**Do not** treat `prev/`, `out/frames/`, `manim.log`, or the old MP4s as sources of truth — they are checks or leftovers. Story source of truth is `script.md` alone (change it first, then render). Pipeline source of truth is the scripts in this folder.

---

## 3. Motion principles (render.py and Remotion)

Use these when editing or creating animated scenes. Our style is a dark 2D explainer for hackathon / board judges — clear, active, not decorative.

### Practical rules (always)
- **No passive slides** — nothing just drifts on and sits; every entrance earns attention, then settles.
- **Every scene answers a judge question** — what is broken, what we built, why it is trustworthy, what the numbers say, what is next.
- **Holds matter more than speed** — land the point, hold it long enough to read, then move; rushing kills trust.

### Twelve principles (one line each, for our explainer)
1. **Squash and stretch** — give cards and nodes a slight scale pulse on land so they feel weighty, not cardboard.
2. **Anticipation** — lead every move with a small opposite wind-up before the main travel.
3. **Staging** — one clear focal point per beat; dim or push everything else back so the eye knows where to look.
4. **Straight ahead vs pose to pose** — build scenes pose to pose (key layouts on narration beats); fill the in-betweens, don’t freestyle frame by frame.
5. **Follow through and overlapping action** — when a box stops, let labels or chips settle a frame later so the stop isn’t stiff.
6. **Slow in and slow out** — ease every fade and slide; never linear; start soft, end soft.
7. **Arcs** — move elements on gentle curves, not ruler-straight lines, unless the story is “exact / mechanical.”
8. **Secondary action** — a small pulse, underline, or chip pop can support the main reveal; it must never steal the beat.
9. **Timing** — match motion length to the spoken phrase; short words get snappy moves, long ideas get longer travel and a hold.
10. **Exaggeration** — push contrast and accent color a bit past “UI realism” so the proof moment reads at a glance.
11. **Solid drawing** — keep alignment, spacing, and hierarchy consistent across scenes so the system feels designed, not collage.
12. **Appeal** — dark theme, one accent, readable Inter type, breathing room — make judges want to keep watching.

---

## 4. Storyline principles

Narrative rules for this video. Edit story in `script.md` first; motion follows the beats.

1. **Active journey, not a feature tour** — problem → path → MVPs → vs existing tools → live app → plain-word proof → architecture → future.
2. **Every scene answers a judge question** — what hurts, what we chose, why trust it, what we can show, what comes next.
3. **Memory is present** — frame Engineering Memory as part of the system now; no gap language like “missing,” “not built,” or “coming later” on the core idea.
4. **Close bigger than one agent** — end on a central knowledge base for the team’s engineering history, not only a single Q&A bot.
5. **Sharper hook** — open on the human cost: when the person who knew why leaves, the reasoning disappears.
6. **Plain-word proof** — numbers and results in everyday language; skip jargon the judges would have to decode.
