"""Automatic labels: questions parsed from history with no model, each passing the gold check."""

import datetime as dt

from eval_support import CUTOFF, FIXTURE_RECORDS

from whycode.contract import Anchor
from whycode.eval.corpus import CorpusRecord, MemoryCorpus
from whycode.eval.gold import GoldEvidence, check_gold
from whycode.eval.labels import generate_labels

REJECTED_RFC = CorpusRecord(
    id="rfc:20170101_shadow_tables", kind="rfc", title="20170101_shadow_tables.md", date=dt.date(2017, 1, 1),
    text="# Shadow tables\n- Feature Name: Shadow tables for online schema changes\n- Status: rejected\n"
         "- RFC PR: #12000\n\n# Summary\n\nKeep a full shadow copy of every table during a schema change.")
BACKPORT = CorpusRecord(id="pr:116900", kind="pr", number=116900, date=dt.date(2023, 12, 21),
                        title='release-23.2: Revert "schemachanger: Implement CREATE DATABASE"', text="Backport.")
DOMAIN_REVERT = CorpusRecord(id="pr:72619", kind="pr", number=72619, date=dt.date(2021, 11, 10),
                             title="sql/schemachanger: hook up reverting to the scjob",
                             text="A failed schema change now reverts its completed stages.")
CORPUS = MemoryCorpus([*FIXTURE_RECORDS, REJECTED_RFC, BACKPORT, DOMAIN_REVERT])


def labels():
    return {q.id: q for q in generate_labels(CORPUS, cutoff=CUTOFF)}


def test_every_automatic_label_passes_the_gold_check_and_waits_for_a_human():
    qs = list(labels().values())

    assert check_gold(qs, CORPUS, cutoff=CUTOFF) == []
    assert all(q.origin == "automatic" and not q.human_verified for q in qs)
    assert sorted(labels()) == ["auto-fixes-pr-121026-issue-117574", "auto-revert-pr-116879", "auto-revert-pr-127500",
                                "auto-rfc-rfc-20170101-shadow-tables", "auto-rfc-rfc-20181003-schemas"]


def test_superseded_rfc_status_becomes_a_supersession_question():
    q = labels()["auto-rfc-rfc-20181003-schemas"]

    assert q.type == "supersession"
    assert q.gold_evidence == [
        GoldEvidence(node_id="rfc:20181003_schemas", quote="Status: superseded by #48276"),
        GoldEvidence(node_id="rfc:20200501_user_defined_schemas",
                     quote="RFC PR: [#48276](https://github.com/cockroachdb/cockroach/pull/48276)")]
    assert q.gold_facts == ['The "User-defined SQL logical schemas" RFC was superseded by the "User Defined Schemas" RFC']
    assert q.superseded_facts == ['The design in the "User-defined SQL logical schemas" RFC is the live Decision']


def test_rejected_rfc_is_a_dead_decision():
    q = labels()["auto-rfc-rfc-20170101-shadow-tables"]

    assert q.gold_facts == ['The "Shadow tables for online schema changes" RFC was rejected']
    assert q.gold_evidence == [GoldEvidence(node_id="rfc:20170101_shadow_tables", quote="Status: rejected")]


def test_fixes_link_to_a_regression_becomes_an_incident_question_anchored_on_the_changed_file():
    q = labels()["auto-fixes-pr-121026-issue-117574"]

    assert (q.type, q.anchor) == ("incident", Anchor(kind="file", id="pkg/sql/configure_zone.go"))
    assert q.question == 'What problem was the change "sql: skip dropped indexes when configuring zones" made to fix?'
    assert q.gold_evidence[0] == GoldEvidence(node_id="pr:121026", quote="Fixes: #117574")
    assert q.gold_facts == ['It fixes the issue "sql: ALTER TABLE CONFIGURE ZONE panics on a dropped index"']


def test_revert_before_the_cutoff_is_a_supersession_question():
    q = labels()["auto-revert-pr-116879"]

    assert q.type == "supersession"
    assert q.gold_facts == ['The change "schemachanger: Implement CREATE DATABASE" was reverted']
    assert q.superseded_facts == ['The change "schemachanger: Implement CREATE DATABASE" is in effect']
    assert [e.node_id for e in q.gold_evidence] == ["pr:116879", "pr:116000"]


def test_revert_inside_the_held_out_window_has_an_answer_before_and_after_the_cutoff():
    q = labels()["auto-revert-pr-127500"]

    assert q.type == "window"
    assert q.gold_facts == ['The change "sql: add sql.schema.force_declarative setting" is in effect']
    assert [e.node_id for e in q.gold_evidence] == ["pr:125000"]
    assert q.after.gold_facts == ['The change "sql: add sql.schema.force_declarative setting" was reverted']
    assert q.after.superseded_facts == q.gold_facts
    assert [e.node_id for e in q.after.gold_evidence] == ["pr:127500", "pr:125000"]


def test_revert_by_commit_sha_resolves_without_a_title_match():
    revert = CorpusRecord(id="pr:118000", kind="pr", number=118000, date=dt.date(2024, 1, 5),
                          title="sql: undo the declarative CREATE DATABASE",
                          text="This reverts commit 2222222222222222222222222222222222222222.")
    qs = generate_labels(MemoryCorpus([*FIXTURE_RECORDS, revert]), cutoff=CUTOFF)

    q = next(q for q in qs if q.id == "auto-revert-pr-118000")
    assert q.gold_evidence[0] == GoldEvidence(
        node_id="pr:118000", quote="This reverts commit 2222222222222222222222222222222222222222")


def test_labels_beyond_the_window_end_are_left_out():
    qs = generate_labels(CORPUS, cutoff=CUTOFF, window_end=dt.date(2024, 7, 1))

    assert "auto-revert-pr-127500" not in {q.id for q in qs}
