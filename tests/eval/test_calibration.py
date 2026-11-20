"""The calibration plot: stated confidence against judged correctness, produced from a run's output by one command."""

import datetime as dt
import io
import xml.etree.ElementTree as ET

from eval_support import CUTOFF, FIXTURE_RECORDS

from whycode.contract import Answer, EvidenceItem, Sentence
from whycode.eval.cli import Deps, main
from whycode.eval.corpus import MemoryCorpus
from whycode.eval.gold import GoldEvidence, GoldQuestion, save_gold
from whycode.eval.judge import Verdict
from whycode.eval.runner import Query, System
from whycode.eval.scoreboard import run_eval

ZONE_QUOTE = "because their descriptors may already be gone"
SVG = "{http://www.w3.org/2000/svg}"


def gold(id, **kw):
    base = dict(id=id, type="lookup", origin="human", question=f"Why {id}?", split="dev", human_verified=True,
                gold_facts=["Dropped indexes may have no descriptor"],
                gold_evidence=[GoldEvidence(node_id="pr:121026", quote=ZONE_QUOTE)])
    return GoldQuestion(**(base | kw))


QUESTIONS = [gold(f"L{i}") for i in range(1, 6)] + [
    gold("U1", type="unanswerable", answerable=False, gold_facts=[], gold_evidence=[], ablates="L1")]

# (confidence, right?) per question; None means a refusal.
CALIBRATED = {"L1": ("High", True), "L2": ("High", True), "L3": ("Medium", True), "L4": ("Medium", False),
              "L5": ("Low", False), "U1": None}
OVERCONFIDENT = {"L1": ("High", True), "L2": ("High", False), "L3": ("High", False), "L4": ("High", False),
                 "L5": ("High", False), "U1": ("High", False)}


def stub(script):
    def run(query: Query) -> Answer:
        said = script[query.question.removeprefix("Why ").removesuffix("?")]
        if said is None:
            return Answer(anchor=None, refused=True, confidence="Low")
        confidence, right = said
        return Answer(anchor=None, refused=False, confidence=confidence,
                      evidence_chain=[EvidenceItem(node_id="pr:121026", kind="pr", quote=ZONE_QUOTE)],
                      sentences=[Sentence(text="right" if right else "wrong", cites=["pr:121026"])])
    return run


def judge(item):
    return Verdict(covered=[item.answer_text.endswith("right")] * len(item.gold_facts))


def harness_output(root):
    for sub in ("gold", "prompts", "results"):
        (root / sub).mkdir(parents=True)
    save_gold(root / "gold" / "human.yaml", QUESTIONS)
    (root / "prompts" / "judge.md").write_text("Grade the answer.\n")
    clock = iter(x * 0.5 for x in range(10_000))
    return run_eval("dev", eval_dir=root, corpus=MemoryCorpus(FIXTURE_RECORDS), cutoff=CUTOFF, judge=judge,
                    judge_model="scripted-judge", clock=lambda: next(clock),
                    now=lambda: dt.datetime(2026, 11, 20, 10, 15, 0),
                    systems=[System("ours", stub(CALIBRATED)), System("overconfident", stub(OVERCONFIDENT))]).run_dir


def calibration(run_dir, *extra):
    out = io.StringIO()
    code = main(["calibration", "--run", str(run_dir), *extra],
                Deps(structured=None, tool_loop=None, embedder=None, out=out))
    return code, out.getvalue()


def test_one_command_turns_a_run_into_a_calibration_table_and_plot(tmp_path):
    run_dir = harness_output(tmp_path / "eval")

    code, printed = calibration(run_dir)

    assert code == 0
    table = (run_dir / "calibration.md").read_text()
    assert printed.startswith(table.split("\n\n![")[0])
    assert "| confidence | ours | overconfident |" in table
    assert "| High | 100% [100-100] n=2 | 17% [" in table and "n=6 |" in table  # U1 answered anyway: wrong
    assert "| Medium | 50% [" in table
    assert "| Low | 0% [0-0] n=1 | - |" in table
    assert "| refused (left out) | 1 | 0 |" in table
    assert "![Calibration plot](calibration.svg)" in table


def test_the_plot_has_one_panel_per_system_and_a_tooltip_per_confidence_level(tmp_path):
    run_dir = harness_output(tmp_path / "eval")
    calibration(run_dir)

    svg = ET.parse(run_dir / "calibration.svg").getroot()

    assert svg.tag == f"{SVG}svg"
    texts = [t.text for t in svg.iter(f"{SVG}text")]
    assert "ours" in texts and "overconfident" in texts
    tips = [t.text for t in svg.iter(f"{SVG}title")]
    assert "ours, High: 100% correct, 95% interval 100-100%, n=2" in tips
    assert "ours, Low: 0% correct, 95% interval 0-0%, n=1" in tips
    assert "overconfident, Medium: no answers" in tips


def test_systems_and_output_directory_can_be_chosen(tmp_path):
    run_dir = harness_output(tmp_path / "eval")

    code, printed = calibration(run_dir, "--systems", "ours", "--out", str(tmp_path / "plots"))

    assert code == 0
    assert "| confidence | ours |" in printed and "overconfident" not in printed
    assert (tmp_path / "plots" / "calibration.svg").exists() and not (run_dir / "calibration.svg").exists()
