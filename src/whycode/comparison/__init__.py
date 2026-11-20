"""The agent comparison (ticket 05): coding agents given real tasks on pre-cutoff code, with and without our MCP
tools, graded on whether they repeat the real pitfall and whether a Fence Warning changed their course.

- `tasks`: task records (task text, pre-cutoff commit, real pitfall, grading rule), frozen before any run, and
  the grading of a diff against a record.
- `runner`: workspaces at the base commit, the coding-agent seam (Claude Code headless, or a scripted agent in
  tests), run records, the with/without table and the demo transcript.
- `cli`: `whycode-agents freeze | run | report | demo`.

Data lives in `eval/agent-comparison/` (see its README).
"""
