#!/usr/bin/env bash
# One-command rebuild: Remotion animated scenes + Playwright S4 demo → final MP4 (<=25 MB).
# Usage: ./rebuild.sh [marks.json]   (default: marks_live.json if present, else marks_local.json)
# The marks file's "mode" (local | live | live_ask) picks the S4 narration variant from s4_variants.json.
set -euo pipefail
cd /workspace/video
MARKS=${1:-$( [ -f marks_live.json ] && echo marks_live.json || echo marks_local.json )}
MODE=$(python3 -c "import json;print(json.load(open('$MARKS')).get('mode','local'))")
echo "marks=$MARKS mode=$MODE"

# 1) S4 narration variant -> script.md, regenerate S4 voice only if text changed
CHANGED=$(python3 - "$MODE" <<'PY'
import json,re,sys
v=json.load(open('s4_variants.json'))[sys.argv[1]]
s=open('script.md').read()
new=re.sub(r'(## S4 Demo\n)(.+?)(\n\n## )',lambda m:m.group(1)+v+m.group(3),s,flags=re.S)
print('1' if new!=s else '0'); open('script.md','w').write(new)
PY
)
if [ "$CHANGED" = 1 ] || [ ! -f aud/S4.mp3 ]; then venv/bin/python tts.py en-US-ChristopherNeural S4; fi
D4=$(python3 -c "import subprocess;print(float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0','aud/S4.mp3']))+0.3)")
ffmpeg -y -loglevel error -i aud/S4.mp3 -af apad -t "$D4" -ar 48000 -ac 2 aud/S4.wav

# 2) Remotion animated segments → seg/Sk.mp4 (replaces Pillow render.py for these ids)
#    S4 stays Playwright (step 3). Re-sync durations from aud/*.mp3 first (S7–S9 use 65/55/50
#    placeholders until Sarvam TTS exists — re-measure before a final render).
ANIM_SCENES=(S1 S2 S3 S5 S6 S7 S8 S9)
echo "remotion: sync durations + render ${ANIM_SCENES[*]}"
( cd remotion && ./scripts/sync-durations.sh > /tmp/remotion-durations.txt )
# Prefer system Chrome when Remotion's bundled browser is unavailable
export REMOTION_BROWSER_EXECUTABLE="${REMOTION_BROWSER_EXECUTABLE:-${PUPPETEER_EXECUTABLE_PATH:-$(command -v google-chrome || command -v chromium || true)}}"
mkdir -p seg
for k in "${ANIM_SCENES[@]}"; do
  echo "  render $k → seg/$k.mp4"
  ( cd remotion && npx remotion render src/index.ts "$k" "../seg/$k.mp4" \
      --codec h264 --crf 20 --pixel-format yuv420p --overwrite )
done

# 3) demo clip (Playwright capture via marks → build_s4.py → seg/S4.mp4)
python3 build_s4.py "$MARKS"

# 4) subtitles, audio mix, concat
python3 subs.py
ffmpeg -y -loglevel error -f concat -safe 0 -i alist.txt -c copy aud/voice.wav
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 aud/voice.wav)
ffmpeg -y -loglevel error -f lavfi -i "sine=f=55:d=$D" -f lavfi -i "sine=f=82.5:d=$D" -f lavfi -i "anoisesrc=d=$D:c=brown:a=0.3" -filter_complex "[0][1][2]amix=inputs=3,lowpass=f=300,tremolo=f=0.1:d=0.5,volume=-36dB,afade=t=in:d=3,afade=t=out:st=$(python3 -c "print($D-4)"):d=4,aformat=channel_layouts=stereo:sample_rates=48000[b]" -map "[b]" aud/bed.wav
ffmpeg -y -loglevel error -i aud/voice.wav -i aud/bed.wav -filter_complex "[0][1]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5" -ar 48000 aud/mix.wav
ffmpeg -y -loglevel error -f concat -safe 0 -i vlist.txt -c copy seg/all.mp4

# 5) final encode with burned subtitles; raise CRF until <= 25 MB
VF="subtitles=out/engineering-memory.ass:fontsdir=/usr/share/fonts/truetype/sand-box/google/Inter"
for CRF in 22 25 28 31; do
  ffmpeg -y -loglevel error -i seg/all.mp4 -i aud/mix.wav -vf "$VF" -c:v libx264 -preset slow -crf $CRF -maxrate 4000k -bufsize 8000k -pix_fmt yuv420p -c:a aac -b:a 128k -shortest -movflags +faststart out/engineering-memory.mp4
  SZ=$(stat -c %s out/engineering-memory.mp4); [ "$SZ" -le 26214400 ] && break
done
cp out/engineering-memory.mp4 engineering-memory-hackathon.mp4
cp out/engineering-memory.srt engineering-memory-hackathon.srt

# 6) verification frames
rm -f out/frames/*.png; i=0
for t in 10 30 60 90 112 125 140 150 165 190 215 235; do i=$((i+1)); ffmpeg -y -loglevel error -ss $t -i out/engineering-memory.mp4 -frames:v 1 out/frames/f$(printf %02d $i)_${t}s.png; done
ffprobe -v error -show_entries format=duration,size:stream=codec_name,duration -of compact out/engineering-memory.mp4
echo "final: /workspace/video/engineering-memory-hackathon.mp4 (CRF $CRF)"
