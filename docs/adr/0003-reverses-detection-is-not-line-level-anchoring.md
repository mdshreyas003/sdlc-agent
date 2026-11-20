---
status: accepted
---

# Fence Warnings may compare diff lines; Decisions are still anchored to Code Entities, not lines

The spec puts "line-level anchoring and blame" out of scope, yet `check_change` stores the lines each pull request added and removed in a file (up to 1000 distinct lines per file and Change, on its TOUCHES edge) and matches a proposed diff's lines against them to raise `kind: reverses` Fence Warnings. We read the exclusion as being about where Decisions attach: a Decision governs a package, file, function or cluster setting, never a line range, and no answer is ever built from blame. Matching line text only tells whether a proposed diff undoes what a Decision's implementing Change wrote inside code the Decision already governs, which is the strongest evidence a Fence Warning can carry ("this removes the backoff #98100 added"). So we keep it: it sharpens a Fence Warning without moving any Decision onto lines.

## Considered Options

- **Drop line matching and warn only on edits to governed functions and settings (`kind: changes`).** Strictly within the letter of the exclusion, but every edit to a governed function would look alike, so an agent could not tell a harmless tweak from undoing the Decision.
- **Anchor Decisions to line ranges (blame).** This is the excluded feature: line ranges drift with every edit, and it needs history replay per line.

## Consequences

- Stored lines are trimmed text, matched exactly and only inside code the Decision governs; trivial lines (braces, `return err`, comments, imports) are never evidence.
- The 1000-line cap per file and Change bounds the graph's size; a Change past it can miss a `reverses` warning and fall back to `changes`.
- If the exclusion is ever read more strictly, `reverses` detection is removable on its own: `changes` warnings and `why` do not depend on it.
