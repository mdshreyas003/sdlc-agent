"""Code index over a Go checkout: the Code Entities a scope yields, and the names an Anchor may use for them."""

from __future__ import annotations

from pathlib import Path

from whycode.codeindex.go import parse_go_tree
from whycode.history.records import FileChange

KNOBS = '''package scexec

import "github.com/cockroachdb/cockroach/pkg/settings"

// BackfillChunkSizeSettingName is the user-visible name.
const BackfillChunkSizeSettingName = "sql.schemachanger.backfill.chunk_size"

var backfillChunkSize = settings.RegisterIntSetting(
	settings.ApplicationLevel,
	BackfillChunkSizeSettingName,
	"number of rows to backfill at a time",
	5000,
)

var mergeTimeout = settings.RegisterDurationSetting(
	settings.ApplicationLevel,
	"bulkio.schemachanger.merge.timeout",
	"how long to wait for an index merge",
	0,
	settings.WithName("sql.schemachanger.merge.timeout"),
	settings.WithRetiredName("schemachanger.merge.timeout"),
	settings.WithPublic,
)

var fromAnotherPackage = settings.RegisterBoolSetting(
	settings.ApplicationLevel,
	otherpkg.SettingKey,
	"a key this index cannot see, so it is skipped rather than guessed",
	false,
)
'''

KEYS = '''package scexec

const (
	jobPollKey = "sql.schemachanger.job.poll_interval"
	unrelated  = 7
)

func exec() {}
'''

POLL = '''package scexec

import "github.com/cockroachdb/cockroach/pkg/settings"

var jobPoll = settings.RegisterDurationSetting(settings.ApplicationLevel, jobPollKey, "poll interval", 0)
'''

LEGACY = '''package sql

func (sc *SchemaChanger) exec() error { return nil }
'''

UNSCOPED = '''package sql

func notInScope() {}
'''


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_setting_keys_given_by_constants_in_the_same_package_are_resolved_and_extra_names_become_aliases(tmp_path):
    root = write(tmp_path, {
        "pkg/sql/schemachanger/scexec/knobs.go": KNOBS,
        "pkg/sql/schemachanger/scexec/keys.go": KEYS,
        "pkg/sql/schemachanger/scexec/poll.go": POLL,
    })
    index = parse_go_tree(root, scope=["pkg/sql/schemachanger"])

    settings = {e.key: e for e in index.entities if e.kind == "setting"}
    assert set(settings) == {
        "sql.schemachanger.backfill.chunk_size",  # a const in the same file
        "sql.schemachanger.job.poll_interval",  # a const in another file of the package
        "bulkio.schemachanger.merge.timeout",
    }
    assert settings["sql.schemachanger.job.poll_interval"].parent == "pkg/sql/schemachanger/scexec/poll.go"
    merge = settings["bulkio.schemachanger.merge.timeout"]
    assert {"sql.schemachanger.merge.timeout", "schemachanger.merge.timeout", "mergeTimeout"} <= set(merge.aliases)
    # A user-visible name written in text links to the setting it names, and a diff that edits it touches it.
    assert index.mentions("raise sql.schemachanger.merge.timeout when merges time out") == {merge}
    patch = '@@ -20,1 +20,1 @@\n-\tsettings.WithName("sql.schemachanger.merge.timeout"),\n+\tsettings.WithPublic,'
    touched = index.touched_by(FileChange(path="pkg/sql/schemachanger/scexec/knobs.go", status="modified",
                                          patch=patch))
    assert merge in touched


def test_a_scope_entry_may_name_a_single_file(tmp_path):
    root = write(tmp_path, {
        "pkg/sql/schema_changer.go": LEGACY,
        "pkg/sql/unscoped.go": UNSCOPED,
        "pkg/sql/schemachanger/scexec/keys.go": KEYS,
    })
    index = parse_go_tree(root, scope=["pkg/sql/schema_changer.go", "pkg/sql/schemachanger"])

    keys = {e.key for e in index.entities}
    assert {"pkg/sql/schema_changer.go", "pkg/sql.(*SchemaChanger).exec", "pkg/sql",
            "pkg/sql/schemachanger/scexec/keys.go"} <= keys
    assert "pkg/sql/unscoped.go" not in keys
    assert "pkg/sql.notInScope" not in keys
