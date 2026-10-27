#!/usr/bin/env python3
"""Synthesize script.md segments with Sarvam Bulbul text-to-speech (default catalog voices).

Usage:
  venv/bin/python tts.py [ignored-legacy-voice-name] [S1 S2 ...]
  venv/bin/python tts.py S3
  venv/bin/python tts.py          # all segments

Default: model bulbul:v3, speaker ratan (en-IN recommended male), pace 1.05.
Override: SARVAM_SPEAKER=ishita SARVAM_MODEL=bulbul:v3
API key: SARVAM_API_KEY env, or /home/box/.secrets/sdlc-agent-llm.env
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECRETS = Path("/home/box/.secrets/sdlc-agent-llm.env")
API = "https://api.sarvam.ai/text-to-speech"
LANG = "en-IN"
MODEL = os.environ.get("SARVAM_MODEL", "bulbul:v3")
SPEAKER = os.environ.get("SARVAM_SPEAKER", "ratan")
PACE = float(os.environ.get("SARVAM_PACE", "1.05"))
SAMPLE_RATE = 48000
MAX_CHARS = 2200  # bulbul:v3 limit 2500; leave headroom


def load_key() -> str:
    k = os.environ.get("SARVAM_API_KEY", "").strip()
    if k:
        return k
    if SECRETS.is_file():
        for line in SECRETS.read_text().splitlines():
            if line.startswith("SARVAM_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("SARVAM_API_KEY not found in env or /home/box/.secrets/sdlc-agent-llm.env")


def parse_args(argv: list[str]) -> list[str]:
    args = argv[1:]
    if args and re.fullmatch(r"en-[A-Z]{2}-.+", args[0]):
        args = args[1:]
    if args and args[0] in ("sarvam", "clone", "bulbul", "--"):
        args = args[1:]
    return args


def segments(script: str) -> list[tuple[str, str]]:
    return [
        (k, t.strip())
        for k, t in re.findall(r"## (S\d+)[^\n]*\n(.+?)(?=\n## |\Z)", script, re.S)
    ]


def chunk_text(text: str, limit: int = MAX_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf = ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for s in sentences:
        if not s:
            continue
        if len(s) > limit:
            if buf:
                parts.append(buf.strip())
                buf = ""
            for i in range(0, len(s), limit):
                parts.append(s[i : i + limit])
            continue
        if len(buf) + len(s) + 1 <= limit:
            buf = f"{buf} {s}".strip()
        else:
            if buf:
                parts.append(buf)
            buf = s
    if buf:
        parts.append(buf)
    return parts


def synthesize_chunk(key: str, text: str) -> tuple[bytes, str, float | None]:
    """Returns (audio_bytes, format_hint 'mp3'|'wav', duration_or_None)."""
    payload = {
        "text": text,
        "language_code": LANG,
        "model": MODEL,
        "speaker": SPEAKER,
        "pace": PACE,
        "speech_sample_rate": SAMPLE_RATE,
        "output_audio_codec": "mp3",
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "api-subscription-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        # Retry without codec if API rejects it
        body = e.read().decode("utf-8", "replace")
        if e.code in (400, 422) and "output_audio_codec" in body.lower():
            payload.pop("output_audio_codec", None)
            req = urllib.request.Request(
                API,
                data=json.dumps(payload).encode(),
                method="POST",
                headers={
                    "api-subscription-key": key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = resp.read()
        else:
            raise SystemExit(f"Sarvam TTS HTTP {e.code}: {body[:800]}") from e
    data = json.loads(raw)
    audios = data.get("audios") or []
    if not audios:
        b64 = data.get("audio_b64") or data.get("audio")
        if not b64:
            raise SystemExit(f"Sarvam response missing audio: {list(data)[:20]}")
        audios = [b64]
    blob = base64.b64decode("".join(audios))
    # WAV starts with RIFF; else treat as mp3
    fmt = "wav" if blob[:4] == b"RIFF" else "mp3"
    dur = data.get("audio_duration") or data.get("duration")
    return blob, fmt, float(dur) if dur is not None else None


def write_srt(path: Path, chunks: list[tuple[str, float]]) -> None:
    lines = []
    t = 0.0
    i = 1
    for text, dur in chunks:
        words = text.split()
        pieces: list[str] = []
        cur = ""
        for w in words:
            if len(cur) + len(w) + 1 > 52 and cur:
                pieces.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            pieces.append(cur)
        tot = sum(len(p) for p in pieces) or 1
        for p in pieces:
            d = dur * len(p) / tot
            a, b = t, t + d
            lines.append(f"{i}\n{fmt_srt(a)} --> {fmt_srt(max(b - 0.02, a + 0.05))}\n{p}\n")
            t = b
            i += 1
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def fmt_srt(x: float) -> str:
    ms = int(round(max(0, x) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def probe_dur(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        text=True,
    ).strip()
    return float(out)


def one(key: str, k: str, text: str) -> None:
    (ROOT / "aud").mkdir(exist_ok=True)
    chunks_txt = chunk_text(text)
    audio_parts: list[tuple[bytes, str]] = []
    timed: list[tuple[str, float]] = []
    for part in chunks_txt:
        audio, fmt, dur = synthesize_chunk(key, part)
        audio_parts.append((audio, fmt))
        if dur is None:
            # rough: ~15 chars/sec at pace 1.05
            dur = max(0.8, len(part) / 15.0)
        timed.append((part, float(dur)))

    out_mp3 = ROOT / "aud" / f"{k}.mp3"
    tmpdir = ROOT / "aud" / f"_parts_{k}"
    tmpdir.mkdir(exist_ok=True)
    paths = []
    for i, (blob, fmt) in enumerate(audio_parts):
        src = tmpdir / f"{i}.{fmt}"
        src.write_bytes(blob)
        mp3 = tmpdir / f"{i}.mp3"
        if fmt == "mp3":
            src.rename(mp3)
        else:
            subprocess.check_call(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3)]
            )
            src.unlink(missing_ok=True)
        paths.append(mp3)

    if len(paths) == 1:
        out_mp3.write_bytes(paths[0].read_bytes())
    else:
        lst = tmpdir / "list.txt"
        lst.write_text("".join(f"file '{fp.name}'\n" for fp in paths))
        subprocess.check_call(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out_mp3)],
            cwd=str(tmpdir),
        )
        lst.unlink(missing_ok=True)

    # Prefer real duration from file for SRT scale
    real = probe_dur(out_mp3)
    est = sum(d for _, d in timed) or real
    scale = real / est if est > 0 else 1.0
    timed = [(t, d * scale) for t, d in timed]
    write_srt(ROOT / "aud" / f"{k}.srt", timed)

    for fp in paths:
        fp.unlink(missing_ok=True)
    try:
        tmpdir.rmdir()
    except OSError:
        pass
    print("done", k, "chunks", len(chunks_txt), "bytes", out_mp3.stat().st_size, f"dur={real:.2f}s")


def main() -> None:
    only = set(parse_args(sys.argv))
    segs = segments((ROOT / "script.md").read_text())
    if only:
        segs = [(k, t) for k, t in segs if k in only]
        missing = only - {k for k, _ in segs}
        if missing:
            raise SystemExit(f"unknown segments: {sorted(missing)}")
    key = load_key()
    print("model", MODEL, "speaker", SPEAKER, "pace", PACE, "lang", LANG)
    for k, t in segs:
        one(key, k, t)


if __name__ == "__main__":
    main()
