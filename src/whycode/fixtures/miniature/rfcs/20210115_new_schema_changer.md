- Feature Name: Declarative, state-based schema changer
- Status: draft
- Start Date: 2021-01-15
- Authors: Andrew Werner, Lucy Zhang
- RFC PR: #59288
- Cockroach Issue: #54584

# Summary

Replace the imperative schema changer with a declarative one that plans each
schema change as a graph of element status transitions.

# Detailed design

The declarative schema changer executes a planned schema change in three
phases: the statement phase, the pre-commit phase and the post-commit phase
run by a job. `scrun.RunStatementPhase` executes the statement phase inside the
user's transaction so that later statements in the same transaction observe
the change.

## Rollout

The declarative schema changer is gated by the
`sql.defaults.use_declarative_schema_changer` cluster setting so that it can be
enabled statement by statement and disabled in production if a bug is found,
without a binary change.

# Alternatives

Extending the existing schema changer with more special cases was rejected:
every new statement multiplied the states that had to be handled by hand.
