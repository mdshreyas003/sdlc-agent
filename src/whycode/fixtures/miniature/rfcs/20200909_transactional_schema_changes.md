- Feature Name: Transactional schema changes
- Status: superseded by #59288
- Start Date: 2020-09-09
- Authors: Andrew Werner
- RFC PR: #55047
- Cockroach Issue: #42061

# Summary

Make schema changes inside explicit transactions behave transactionally, so a
failure part way through never leaves the table half changed.

# Detailed design

`scrun.RunStatementPhase` runs each schema change statement in a child
transaction that commits before the user's transaction, so a failed backfill
never rolls back the user's other writes. The user's transaction then waits
for the new descriptor version before it continues.

# Alternatives

Running the whole schema change inside the user's transaction was rejected:
the backfill would hold the transaction open for hours.
