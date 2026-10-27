# v5 cut vs kept (from v4.2)

Script: 1,289 → ~715 spoken words (≈45% shorter); 9 segments → 8. Voice: Sarvam Bulbul v3 `ratan`, en-IN, pace 0.92 (was 1.05), no cloning. Each segment padded +0.8 s and the voice wav is cut to the exact video length.

## Kept
- Arc: problem → direction (two rules) → 3 MVPs → vs search/chatbots/RAG → verification → live demo → proof → linkage engine → future.
- All good Remotion scenes: S1, S2, S3, S5 (verification), S7 (proof), S8 (linkage/agent), S9 (future).
- Locked numbers only: 1,201 / 2,194 (demo); 1,191 / 1,786 (eval); 5/7 gate; 1→9 of 18; 445 passed / 7 skipped; 75-question gold with traps, no accuracy %. Q041 idempotence investigation is the demo question.
- REPLIES_TO / REFERENCES / CONTAINS as "engineering evidence linking"; "Not established"; "discussion chats" wording.
- Memory framed positively as present now (graph + cites); versioned memory as "next".

## Cut
- YouTube chapter block; repeated "wasted time / effort / context switching" lists; restatements of "no guessed edges".
- MVP detail: Neo4j, FastAPI, Next.js, ID-guard naming, seed/evaluate step list.
- Old S4 "how this differs" as its own segment (it had no visual: the Playwright demo played under it). It is now the opening beat of S5, with a new Remotion beat (Search / Chatbots / RAG cards → "None of them can show you why").
- Old S6 Remotion mock-browser "landing → onboard → ask" + "not a toy Acme sample": replaced by real app footage in S4.
- S7: "intended outcome" kept as one line (goal, not measured); dropped duplicate number readouts.
- S8: "new category / black-box score" filler. S9: long multi-agent paragraph.

## Pipeline fixes
- Play order S1 S2 S3 S5 S4 S7 S8 S9 (alist/vlist); S4 = demo slot, all Remotion ids 1:1.
- rebuild.sh: S4 regex matches `## S4…`; S4 re-TTS uses Sarvam (TTS-only key file), not ChristopherNeural; S6 dropped from render list; all wavs padded to seg length; copy to /workspace/docs/engineering-memory.mp4.
- subs.py: was hard-coded to S1–S6 (subtitles stopped after S6); now follows vlist order + video durations.
- build_s4.py: freezes the last frame if narration outruns footage (no black tail).
- Previous files saved in prev/*-v4.2.*.
