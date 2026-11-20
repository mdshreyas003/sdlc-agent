"""The scoped slice of CockroachDB history (ADR-0002): which code, RFCs, pull requests and issues are ingested.

- Pull requests: merged into `base_ref` on or before the cutoff, found through the commit history of
  `pr_paths` at `pr_history_commit` (the schema-changer code): the cutoff commit, or for a Held-out Window build
  (cutoff at the window's end) the window's last commit, `history_commit`.
- Issues: those carrying an `issue_labels` label (as GitHub labels them today; label-at-cutoff is not
  replayed), plus those the ingested pull requests and RFCs link to.
- RFCs: `rfc_stems` under `rfc_dir`, read from the checkout at the cutoff commit.
- Code index: `code_paths` (directories recursively, or single files) at the cutoff commit, always (Code
  Entities carry no date, so a window build must not move them); a superset of `pr_paths` with the neighbouring
  files that register schema-change cluster settings. The catalog packages (`pkg/sql/catalog/lease`,
  `.../schemadesc`, ...) are not neighbours in this sense: their design reaches the graph through the RFCs and
  `A-schema-*` issues, so gold questions about them anchor on scoped code (e.g. `pkg/sql.WaitToUpdateLeases`), and a
  committed-files test keeps every gold anchor inside `code_paths`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Scope:
    repo: str
    cutoff_commit: str
    pr_paths: tuple[str, ...]
    code_paths: tuple[str, ...]
    rfc_dir: str
    rfc_stems: tuple[str, ...]
    issue_labels: tuple[str, ...]
    base_ref: str = "master"
    history_commit: str | None = None  # Held-out Window builds: the last commit on or before the window's end

    @property
    def pr_history_commit(self) -> str:
        """The commit whose history pull requests are discovered from."""
        return self.history_commit or self.cutoff_commit

    @property
    def checkout_paths(self) -> tuple[str, ...]:
        return (*self.code_paths, self.rfc_dir)

    @property
    def repo_url(self) -> str:
        return f"https://github.com/{self.repo}.git"


CUTOFF_COMMIT = "d13253527955eaa2da09394b8a2729627ab25c48"
"""craig[bot] "Merge #126456", 2024-06-29T21:36:20Z: the last merge into master before 2024-06-30."""

SCHEMA_CHANGES = Scope(
    repo="cockroachdb/cockroach",
    cutoff_commit=CUTOFF_COMMIT,
    pr_paths=(
        "pkg/sql/schemachanger",
        "pkg/sql/schema_changer.go",
        "pkg/sql/schemachange",
        "pkg/sql/schema_change_cluster_setting.go",
    ),
    code_paths=(
        "pkg/sql/schemachanger",
        "pkg/sql/schema_changer.go",
        "pkg/sql/schemachange",
        "pkg/sql/schema_change_cluster_setting.go",
        "pkg/sql/backfill.go",
        "pkg/sql/index_backfiller.go",
        "pkg/sql/exec_util.go",  # sql.defaults.use_declarative_schema_changer
    ),
    rfc_dir="docs/RFCS",
    rfc_stems=(
        "20150720_schema_gossip",
        "20151009_table_descriptor_lease",
        "20151014_online_schema_change",
        "20151214_sql_column_families",
        "20160426_fk",
        "20160624_sql_interleaved_tables",
        "20160830_views",
        "20171102_sql_sequences",
        "20171214_computed_columns",
        "20180411_alter_column_type",
        "20180413_alter_primary_key",
        "20181003_schemas",
        "20191009_temp_tables",
        "20191028_easier_hash_sharded_indexes",
        "20200331_enums",
        "20200401_alter_column_type",
        "20200501_user_defined_schemas",
        "20200507_partial_indexes",
        "20200909_transactional_schema_changes",
        "20210115_new_schema_changer",
        "20210527_default_privileges",
        "20210615_expression_indexes",
        "20210722_on_update_and_row_rehoming",
        "20210825_mvcc_bulk_ops",
        "20211004_incremental_index_backfiller",
        "20220120_row_level_ttl",
        "20220628_invisible_index",
        "20220706_user_defined_functions",
    ),
    issue_labels=(
        "A-schema-changes",
        "A-schema-descriptors",
        "A-schema-catalog",
        "A-schema-transactional",
        "A-schema-leasing",
        "A-schema-changer-impl",
        "A-schema-fixed-by-declarative",
    ),
)
