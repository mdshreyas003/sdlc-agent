- Feature Name: online_schema_change
- Status: completed
- Start Date: 2015-10-14
- Authors: Vivek Menezes
- RFC PR: [#2842](https://github.com/cockroachdb/cockroach/pull/2842)
- Cockroach Issue: [#2036](https://github.com/cockroachdb/cockroach/issues/2036)

# Summary

Run schema changes such as adding an index or a column without taking the
table offline, while the cluster keeps serving reads and writes.

# Motivation

A schema change on a large table can take hours. Blocking all traffic to the
table for that long is not acceptable for an always-on database.

# Detailed design

A schema change is executed by the `SchemaChanger`, which moves the table
descriptor through the delete-only and write-only states before making the
new element public. Each state transition waits for all nodes to hold a lease
on the new descriptor version, so at most two versions of a descriptor are in
use at any time.

## Backfill

The backfill is run by `SchemaChanger.runBackfill` once all nodes have seen the
write-only state, so that no node can write a row the backfill misses.

# Alternatives

We considered running schema changes synchronously inside the transaction that
issued them, but rejected it because a long backfill would hold the transaction
open and block the client.
