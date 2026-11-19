# 05: `check_change`, Fence Warnings and the agent comparison

**What to build:** A coding agent can call `check_change` with a proposed diff. For every Live Decision whose governed Code Entities the diff contradicts or reverses, it gets a Fence Warning carrying the Decision, its quote, the Incidents it prevented, and confidence. A diff touching no governed entity gets no warnings.

Then run the agent comparison:
- Take about 8 real Changes from after the cutoff that were later reverted or caused an Incident.
- Give a coding agent each task (the issue text) on the pre-cutoff code, once with the MCP tools and once without.
- Count how often each version repeats the real pitfall, and how often a Fence Warning changes its course.

Fall back to hand-built "remove this odd-looking check" tasks if fewer than about 8 real tasks qualify.

**Blocked by:** 02, 04

**Status:** ready-for-agent

- [ ] Seam 2 tests: a diff that reverses a fixture Decision returns a Fence Warning; an unrelated diff returns none; a superseded Decision never triggers a warning.
- [ ] Each comparison task records the task text, the pre-cutoff commit, the real pitfall and the grading rule before any run.
- [ ] The results are a with/without table (pitfalls repeated, warnings that led to a change of course), plus one transcript chosen for the demo.
