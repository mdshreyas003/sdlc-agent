# Brightcart explainer (silent video + voice-over script)

A short (about 2 minutes 25), silent, black-and-white explainer. It uses 10 scenes: BC1-BC6, BC8, BC9, BC11, BC12 (BC7 and BC10 are cut). You record the voice yourself.
No audio, no music, no TTS is used.

Files:
- `script-brightcart.md`: the lines you read, one section per scene (BC1 to BC12), with the text shown on screen.
- `remotion/src/bc/scenes.tsx`: the scenes (what appears on screen, in order).
- `remotion/src/bc/engine.tsx`: the look (black, white bold text, one grey) and the motion.
- `remotion/src/bc/shots.ts`: which screenshots exist. A slide with a missing screenshot is skipped.
- `remotion/src/durations.ts`: seconds per scene (keys `BC1` to `BC12`).
- `remotion/public/brightcart/`: the screenshots (copied from `docs/story-assets/`).
- `seg-brightcart/BCn.mp4`: one silent clip per scene.
- `brightcart-silent.mp4`: all scenes joined, no audio track.

## Preview

```bash
cd video/remotion
npm ci                      # first time only
npx remotion studio         # pick BC1 to BC12 in the left list
```

If port 3000 is busy (the web app uses it), add `--port 3111`.

## Render

One scene:
```bash
cd video/remotion
npx remotion render src/index.ts BC8 ../seg-brightcart/BC8.mp4 --codec h264 --crf 20 --port 3111
```

All scenes, then join (Remotion ships its own ffmpeg, so a system ffmpeg is not needed):
```bash
cd video/remotion
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  npx remotion render src/index.ts BC$i ../seg-brightcart/BC$i.mp4 --codec h264 --crf 20 --port 3111
done
cd ../seg-brightcart
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do echo "file 'BC$i.mp4'"; done > list.txt
cd ../remotion
npx remotion ffmpeg -y -f concat -safe 0 -i ../seg-brightcart/list-short.txt -c copy -an ../brightcart-silent.mp4
```

## Lay your voice over the video

Record one audio file, for example `voice.wav` or `voice.m4a`, reading `script-brightcart.md` from start to end.
Then run (system ffmpeg, or `npx remotion ffmpeg` in place of `ffmpeg`):

```bash
ffmpeg -i video/brightcart-silent.mp4 -i voice.wav -map 0:v -map 1:a -c:v copy -c:a aac -shortest video/brightcart-final.mp4
```

Tip: record each scene on its own and keep each take close to the scene length in the script heading.
If a take is longer than its scene, change the scene length (below) and re-render that scene.

## Edit the script and the lengths

1. Edit the sentences in `script-brightcart.md`.
2. Count the words in the scene. Length in seconds = words / 2.3 + 1.
3. Put the new number in `remotion/src/durations.ts` (key `BCn`) and update the heading in the script.
4. To change the text on screen, edit the matching scene in `remotion/src/bc/scenes.tsx`.
   Each scene is a list of slides. Each slide has a weight `w`: a bigger `w` keeps it on screen longer.
   Slide types: `big` (large lines), `type` (typed code line), `list`, `shot` (screenshot in a white frame), `card`, `stats`.
5. Re-render the scene and join again.

## Notes

- Everything about Brightcart is simulated. The video says so in BC3 and BC12.
- Numbers in BC11 are the only claims about evidence. Do not add others.
- The price in BC10 is the one already on the landing page.
- `remotion/src/theme.ts` now skips the Inter and JetBrains Mono font files when `public/fonts/` is missing (it is not in git). The BC scenes use system fonts (Helvetica Neue or Arial) anyway.
