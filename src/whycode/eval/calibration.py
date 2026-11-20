"""Calibration: does a stated confidence (High / Medium / Low) mean what it says?

Read from one run's output (`answers.jsonl` for each answer's confidence, `scores.jsonl` for the judged
correctness), so it needs no model and can be redrawn at any time:

    uv run whycode-eval calibration --run eval/results/dev-<time>     # writes calibration.md and calibration.svg

Each answer that was not refused counts once, at its stated confidence: its value is the judged answer correctness
(share of gold facts stated), or 0 when the question was unanswerable and the system answered anyway. Refusals
(always Low by contract, asserting nothing) and failed calls are left out and counted. Each level shows the mean,
its 95% bootstrap interval (resampling answers, as the results table does) and the number of answers.
"""

from __future__ import annotations

import html
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from whycode.eval.runner import read_records
from whycode.eval.scoring import ItemScore
from whycode.eval.stats import N_BOOT, SEED, Interval, boot, fmt

LEVELS = ("High", "Medium", "Low")


@dataclass(frozen=True)
class Level:
    values: tuple[float, ...]
    interval: Interval

    @property
    def n(self) -> int:
        return len(self.values)


@dataclass(frozen=True)
class SystemCalibration:
    name: str
    levels: dict[str, Level]
    refused: int
    failed: int


@dataclass(frozen=True)
class Calibration:
    run: str
    split: str
    systems: tuple[SystemCalibration, ...]

    def markdown(self, plot: str | None = "calibration.svg") -> str:
        names = [s.name for s in self.systems]
        lines = [f"# Calibration: `{self.split}` split, run `{self.run}`", "",
                 "Answer correctness by stated confidence, over the answers that were not refused (an unanswerable "
                 "question answered anyway counts as wrong). Each cell: mean, 95% bootstrap interval, number of "
                 "answers. High should be visibly above Medium, and Medium above Low.", "",
                 "| confidence | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for level in LEVELS:
            cells = [f"{fmt(s.levels[level].interval)} n={s.levels[level].n}" if s.levels[level].n else "-"
                     for s in self.systems]
            lines.append(f"| {level} | " + " | ".join(cells) + " |")
        lines.append("| refused (left out) | " + " | ".join(str(s.refused) for s in self.systems) + " |")
        if any(s.failed for s in self.systems):
            lines.append("| failed calls (left out) | " + " | ".join(str(s.failed) for s in self.systems) + " |")
        if plot:
            lines += ["", f"![Calibration plot]({plot})"]
        return "\n".join(lines) + "\n"

    def svg(self) -> str:
        return _svg(self)


def calibration(run_dir: Path, systems: Sequence[str] | None = None, n_boot: int = N_BOOT,
                seed: int = SEED) -> Calibration:
    import json

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    records = read_records(run_dir / "answers.jsonl")
    scores = {(s.case_id, s.system): s for s in (ItemScore.model_validate_json(line) for line in
              (run_dir / "scores.jsonl").read_text(encoding="utf-8").splitlines() if line)}
    order = list(dict.fromkeys(r.system for r in records))  # the order the run asked them in
    chosen = [n for n in order if systems is None or n in systems]
    out = []
    for name in chosen:
        values: dict[str, list[float]] = {level: [] for level in LEVELS}
        refused = failed = 0
        for r in records:
            if r.system != name:
                continue
            item = scores.get((r.case_id, name))
            if r.answer is None or item is None or item.error:
                failed += 1
            elif r.answer.refused:
                refused += 1
            elif (value := _correct(item)) is not None:
                values[r.answer.confidence].append(value)
        levels = {level: Level(tuple(v), boot(v, n_boot, seed)) for level, v in values.items()}
        out.append(SystemCalibration(name, levels, refused, failed))
    return Calibration(run_dir.name, manifest.get("split", "?"), tuple(out))


def _correct(item: ItemScore) -> float | None:
    if item.correctness is not None:
        return item.correctness
    return 0.0 if item.invented else None


# --- the plot: small multiples, one panel per system (one colour, so no legend), columns per confidence --------

PANEL_W, PANEL_H, PER_ROW = 230, 232, 3
PLOT_TOP, PLOT_BOTTOM, PLOT_LEFT, PLOT_RIGHT = 44, 186, 44, 14
HEADER_H = 58
BAR_W = 24
STYLE = """
.surface { fill: #fcfcfb; } .ink { fill: #0b0b0b; } .ink2 { fill: #52514e; } .muted { fill: #898781; }
.grid { stroke: #e1e0d9; stroke-width: 1; } .axis { stroke: #c3c2b7; stroke-width: 1; }
.bar { fill: #2a78d6; } .whisker { stroke: #0b0b0b; stroke-width: 1.5; stroke-linecap: round; }
.hit { fill: transparent; } .hit:hover { fill: rgba(11,11,11,0.05); }
text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
@media (prefers-color-scheme: dark) {
  .surface { fill: #1a1a19; } .ink { fill: #f0efec; } .ink2 { fill: #c3c2b7; }
  .grid { stroke: #2c2c2a; } .axis { stroke: #383835; } .bar { fill: #3987e5; } .whisker { stroke: #f0efec; }
  .hit:hover { fill: rgba(255,255,255,0.07); }
}"""


def _svg(cal: Calibration) -> str:
    n = max(len(cal.systems), 1)
    cols = min(n, PER_ROW)
    rows = math.ceil(n / PER_ROW)
    width, height = cols * PANEL_W + 16, HEADER_H + rows * PANEL_H
    e = html.escape
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
             f'height="{height}" role="img" aria-labelledby="cal-title cal-desc">',
             f"<style>{STYLE}</style>",
             f'<rect class="surface" width="{width}" height="{height}"/>',
             f'<text id="cal-title" class="ink" x="16" y="24" font-size="15" font-weight="600">'
             f"Answer correctness by stated confidence</text>",
             f'<text id="cal-desc" class="ink2" x="16" y="43" font-size="12">{e(cal.split)} split, run '
             f"{e(cal.run)}; answers not refused; whiskers are 95% bootstrap intervals</text>"]
    plot_h = PLOT_BOTTOM - PLOT_TOP
    for i, s in enumerate(cal.systems):
        ox, oy = 8 + (i % PER_ROW) * PANEL_W, HEADER_H + (i // PER_ROW) * PANEL_H
        parts.append(f'<g transform="translate({ox},{oy})">')
        parts.append(f'<text class="ink" x="{PLOT_LEFT}" y="22" font-size="13" font-weight="600">{e(s.name)}</text>')
        for tick in (0, 25, 50, 75, 100):
            y = PLOT_BOTTOM - plot_h * tick / 100
            line = "axis" if tick == 0 else "grid"
            parts.append(f'<line class="{line}" x1="{PLOT_LEFT}" x2="{PANEL_W - PLOT_RIGHT}" y1="{y:.1f}" y2="{y:.1f}"/>')
            if i % PER_ROW == 0:
                parts.append(f'<text class="muted" x="{PLOT_LEFT - 6}" y="{y + 4:.1f}" font-size="11" '
                             f'text-anchor="end">{tick}%</text>')
        band = (PANEL_W - PLOT_LEFT - PLOT_RIGHT) / len(LEVELS)
        for j, level in enumerate(reversed(LEVELS)):  # Low, Medium, High from left to right
            cx = PLOT_LEFT + band * (j + 0.5)
            stat = s.levels[level]
            mean, lo, hi = stat.interval
            if stat.n:
                tip = (f"{s.name}, {level}: {mean * 100:.0f}% correct, "
                       f"95% interval {lo * 100:.0f}-{hi * 100:.0f}%, n={stat.n}")
            else:
                tip = f"{s.name}, {level}: no answers"
            parts.append(f'<g><title>{e(tip)}</title>')
            parts.append(f'<rect class="hit" x="{cx - band / 2 + 2:.1f}" y="{PLOT_TOP - 8}" width="{band - 4:.1f}" '
                         f'height="{plot_h + 8}"/>')
            if stat.n:
                parts.append(_column(cx, PLOT_BOTTOM - plot_h * mean, PLOT_BOTTOM))
                y_lo, y_hi = PLOT_BOTTOM - plot_h * lo, PLOT_BOTTOM - plot_h * hi
                if y_lo - y_hi >= 1:
                    parts.append(f'<path class="whisker" fill="none" d="M{cx:.1f},{y_lo:.1f}V{y_hi:.1f}'
                                 f'M{cx - 4:.1f},{y_lo:.1f}h8M{cx - 4:.1f},{y_hi:.1f}h8"/>')
            parts.append("</g>")
            parts.append(f'<text class="ink2" x="{cx:.1f}" y="{PLOT_BOTTOM + 17}" font-size="11" '
                         f'text-anchor="middle">{level}</text>')
            parts.append(f'<text class="muted" x="{cx:.1f}" y="{PLOT_BOTTOM + 31}" font-size="10" '
                         f'text-anchor="middle">n={stat.n}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _column(cx: float, top: float, base: float) -> str:
    """A column with a 4px rounded data end, square at the baseline; a measured 0% shows as a 2px sliver, so it
    never looks like a level with no answers."""
    x0, x1, h = cx - BAR_W / 2, cx + BAR_W / 2, base - top
    if h < 2:
        return f'<rect class="bar" x="{x0:.1f}" y="{base - 2:.1f}" width="{BAR_W}" height="2"/>'
    r = min(4.0, h, BAR_W / 2)
    return (f'<path class="bar" d="M{x0:.1f},{base:.1f}V{top + r:.1f}Q{x0:.1f},{top:.1f} {x0 + r:.1f},{top:.1f}'
            f'H{x1 - r:.1f}Q{x1:.1f},{top:.1f} {x1:.1f},{top + r:.1f}V{base:.1f}Z"/>')
