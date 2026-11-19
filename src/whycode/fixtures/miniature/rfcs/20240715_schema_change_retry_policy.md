- Feature Name: Schema change retry policy
- Status: draft
- Start Date: 2024-07-15
- Authors: Faizan Qazi
- RFC PR: #127100
- Cockroach Issue: #121000

# Summary

This RFC is dated after the cutoff and must never be ingested. It proposes
lowering the schema change retry backoff cap to ten seconds.

# Detailed design

Schema change jobs should retry with a backoff capped at ten seconds, because
twenty seconds left stuck jobs waiting too long after short outages.
