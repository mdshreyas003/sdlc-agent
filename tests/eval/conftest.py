"""Fixtures shared by the scoreboard tests."""

import os
import subprocess

import pytest

SETTING_GO = '''package sql

var forceDeclarative = settings.RegisterBoolSetting(
\t"sql.schema.force_declarative",
\t"forces every DDL statement through the declarative schema changer",
\tfalse,
)
'''
ZONE_GO = '''package sql

func configureZone() {
\t// Skip indexes in the DROP state: their descriptors may already be gone.
}
'''


@pytest.fixture(scope="session")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("crdb")

    def git(*args, date="2024-01-01T10:00:00"):
        env = {**os.environ, "GIT_AUTHOR_NAME": "rafiss", "GIT_AUTHOR_EMAIL": "rafiss@example.com",
               "GIT_COMMITTER_NAME": "craig", "GIT_COMMITTER_EMAIL": "craig@example.com",
               "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        return subprocess.run(["git", "-C", str(root), "-c", "commit.gpgsign=false", *args], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(path, text):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)

    git("init", "-q", "-b", "master")
    write("pkg/sql/exec_util.go", SETTING_GO)
    write("docs/RFCS/20181003_schemas.md", "- Status: superseded by #48276\n")
    git("add", "-A")
    git("commit", "-q", "-m", "sql: add sql.schema.force_declarative setting\n\n"
        "This adds a cluster setting that forces every DDL statement through the declarative schema changer.",
        date="2024-05-02T10:00:00")
    setting = git("rev-parse", "HEAD")
    write("pkg/sql/configure_zone.go", ZONE_GO)
    git("add", "-A")
    git("commit", "-q", "-m", "sql: skip dropped indexes when configuring zones\n\nFixes: #117574",
        date="2024-06-22T10:00:00")
    zone = git("rev-parse", "HEAD")
    write("pkg/sql/exec_util.go", "package sql\n")
    git("add", "-A")
    git("commit", "-q", "-m", 'Revert "sql: add sql.schema.force_declarative setting"\n\n'
        "The setting made upgrades fail on clusters with legacy descriptors.", date="2024-07-15T10:00:00")
    revert = git("rev-parse", "HEAD")
    return root, {"setting": setting, "zone": zone, "revert": revert}
