"""The Brightcart pitch story (ingest/demo/story.py): the data is controlled, so its integrity is tested."""

import importlib
import re

import pytest

from hackfront.ingest.demo import story as story_module


@pytest.fixture
def story():
    s = importlib.reload(story_module)  # the module is a singleton: start every test at stage 0 and leave it there
    yield s
    importlib.reload(story_module)


def texts(s):
    for repo in s.REPOS.values():
        for p in repo.PULLS:
            yield p["title"], p["body"]
        for c in repo.COMMITS:
            yield c["commit"]["message"], ""
    for issues in s.JIRA_ISSUES.values():
        for i in issues:
            yield i["fields"]["summary"], i["fields"]["description"]["content"][0]["content"][0]["text"]
    for channel in s.SLACK_THREADS.values():
        for thread in channel.values():
            for m in thread:
                yield m["text"], ""


def test_base_story_is_what_the_pitch_says_and_later_arrivals_are_absent(story):
    assert story.STAGE == 0
    keys = {i["key"] for i in story.JIRA_ISSUES["SHOP"]}
    assert {"SHOP-412", "SHOP-377", "SHOP-455"} <= keys and "SHOP-470" not in keys
    assert 301 not in {p["number"] for p in story.REPOS["brightcart/payments"].PULLS}
    assert story.T_RAISE not in story.SLACK_THREADS["C7CHK"]
    numbers = [p["number"] for r in story.REPOS.values() for p in r.PULLS]
    assert len(numbers) == len(set(numbers)), "PR numbers are unique across the three repos (bare #N is per repo, but the story quotes them plainly)"


def test_every_reference_in_the_story_points_at_something_that_exists(story):
    story.apply_stage(4)
    threads = {ts for c in story.SLACK_THREADS.values() for ts in c}
    keys = {i["key"] for i in story.JIRA_ISSUES["SHOP"]}
    prs = {(r.full, p["number"]) for r in map(lambda n: n, [])}  # placeholder to keep the comprehension below readable
    prs = {f"https://github.com/{full}/pull/{p['number']}" for full, r in story.REPOS.items() for p in r.PULLS}
    for title, body in texts(story):
        blob = f"{title} {body}"
        for ch, raw in re.findall(r"slack\.com/archives/([A-Z0-9]+)/p(\d{16})", blob):
            assert f"{raw[:10]}.{raw[10:]}" in threads, f"dangling Slack link in: {title}"
        for key in re.findall(r"\bSHOP-\d+\b", blob):
            assert key in keys, f"{key} is mentioned but does not exist"
        for url in re.findall(r"https://github\.com/brightcart/\w+-?\w*/pull/\d+", blob):
            assert url in prs, f"dangling PR link {url}"


def test_stages_add_what_they_promise_and_are_idempotent(story):
    story.apply_stage(1)
    assert "SHOP-470" in {i["key"] for i in story.JIRA_ISSUES["SHOP"]} and story.T_RAISE in story.SLACK_THREADS["C7CHK"]
    story.apply_stage(2)
    pr = next(p for p in story.REPOS["brightcart/payments"].PULLS if p["number"] == 301)
    assert pr["state"] == "open" and story.REPOS["brightcart/payments"].PR_FILES[301][0]["filename"] == "src/payments/charge.py"
    story.apply_stage(4)
    story.apply_stage(4)
    issues = story.JIRA_ISSUES["SHOP"]
    assert len(issues) == len({i["key"] for i in issues})
    by_key = {i["key"]: i for i in issues}
    assert by_key["SHOP-470"]["fields"]["status"]["name"] == "Done"
    assert by_key["SHOP-412"]["fields"]["description"]["content"][0]["content"][0]["text"].startswith("Update 24 April")
    pulls = {p["number"]: p for p in story.REPOS["brightcart/payments"].PULLS}
    assert pulls[301]["state"] == "closed" and not pulls[301]["merged"] and pulls[310]["merged"]
    assert sum(1 for p in story.REPOS["brightcart/payments"].PULLS if p["number"] == 301) == 1


def test_patches_replay_to_the_final_file_texts(story):
    story.apply_stage(3)
    for repo in (story.pay, story.acc, story.store):
        for path, final in repo.files.items():
            lines = []
            for c in repo.commits:
                for f in c["files"]:
                    if f["filename"] != path:
                        continue
                    new = []
                    old = iter(lines)
                    for row in f["patch"].splitlines():
                        if row.startswith("@@"):
                            continue
                        new.append(row[1:]) if row[:1] in "+ " else None
                    lines = new if not lines else _apply(lines, f["patch"])
            assert "\n".join(lines).strip() == final.strip(), f"{repo.name}:{path}"


def _apply(old, patch):
    out, i = [], 0
    for row in patch.splitlines():
        if row.startswith("@@"):
            start = int(row.split()[1].split(",")[0][1:])
            out += old[i:max(start - 1, 0)]
            i = max(start - 1, 0)
        elif row.startswith("-"):
            i += 1
        elif row.startswith("+"):
            out.append(row[1:])
        else:
            out.append(row[1:])
            i += 1
    return out + old[i:]
