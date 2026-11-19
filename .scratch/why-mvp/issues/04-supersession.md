# 04: Supersession

**What to build:** `why` stops quoting dead Decisions. **Explicit** Supersession is parsed with no model, from RFC `Status:` (superseded / obsolete / rejected), "Revert …" Changes and "supersedes #N". **Inferred** Supersession works like this:
- Pairs of Decisions that govern the same Code Entity, where B is later than A, become candidates.
- Opus 5.5 labels each pair supersedes / refines / unrelated, with a quoted justification.
- The resulting edges are stored tagged `derived`.

The answer contract then shows each Decision's status (live, superseded or refined), what superseded it and when, and whether that was explicit or inferred. Confidence takes this into account.

**Blocked by:** 01 (scoring on real data also needs 02 and 03)

**Status:** ready-for-agent

- [ ] Seam 1 tests: a fixture revert and an RFC with a superseded status produce explicit edges; scripted judge labels produce the right `supersedes` / `refines` edges.
- [ ] Seam 2 tests: a superseded Decision is never presented as live; a Refinement is shown as partly live.
- [ ] On real data, the judge's precision and recall against the explicit cases are reported.
- [ ] The Held-out Window questions are scored for our system with and without supersession, and the difference appears in the results table.
