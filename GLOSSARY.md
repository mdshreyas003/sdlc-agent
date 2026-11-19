# Why The Code Is Like This

Answers "why is this code the way it is?" for a real codebase, by connecting code to the decisions, discussions and people behind it, with evidence attached.

## Language

**Decision**:
A choice extracted from project history, made up of what was chosen, the rationale, and (when recorded) the alternatives rejected. One Change or Discussion can hold zero or many Decisions, and one Decision can span several.
_Avoid_: Commit, PR, change (when you mean the choice itself)

**Supersession**:
The relationship where a later Decision overrides an earlier one on the same subject, leaving the earlier one dead. It is either *explicit* (stated in history, e.g. a revert or "superseded by") or *inferred* (a later, contradicting choice with no stated link).
_Avoid_: Override, replacement, reversal

**Live Decision**:
A Decision that no later Decision supersedes.
_Avoid_: Current decision, active decision

**Refinement**:
The relationship where a later Decision narrows or extends an earlier one on the same subject, leaving the earlier one partly live.
_Avoid_: Amendment, partial supersession

**Evidence Chain**:
The linked path behind an answer: the Decision, its verbatim quote, the Discussion it came from, its Supersession history, the Person to Ask, and the date.
_Avoid_: Sources, references, citations (when meaning the whole chain)

**Stated Link**:
A connection between two records that a source states outright, such as a PR closing an issue, a commit inside a PR, or an identifier written in text.
_Avoid_: Hard fact, explicit edge

**Derived**:
Produced by model judgment rather than stated by a source, such as an extracted Decision or an inferred Supersession. Anything derived always points back to the verbatim quote it rests on.
_Avoid_: Inferred fact, semantic edge, AI-generated

**Code Entity**:
A part of the codebase that a Decision can govern: a package, file, function or cluster setting.
_Avoid_: Symbol, artifact, component

**Anchor**:
The Code Entity a question is asked about, the starting point for finding the Decisions that govern it.
_Avoid_: Target, location

**Incident**:
An issue labelled as a regression, release blocker or bug that a later Change closes. It stands in for production incidents, which public history does not record.
_Avoid_: Outage, bug (when you mean the linked, closed issue)

**Fence Warning**:
A notice that a proposed Change would contradict or reverse a Live Decision, together with that Decision's evidence.
_Avoid_: Alert, violation, guardrail

**Person to Ask**:
The author or approving reviewer of a Decision who is still active in that area of the code. Someone inactive for 12 months or more is shown as departed.
_Avoid_: Owner, expert, blame author

**Held-out Window**:
A stretch of recent history hidden from the system during evaluation, so the evaluation can test whether answers that changed in that window are reported as changed.
_Avoid_: Test split, cutoff

**Change**:
A unit of history that alters the code, such as a commit or a merged pull request. A Change may implement a Decision but is not one.
_Avoid_: Decision

**Discussion**:
The conversation a Decision came out of, such as a PR review thread, an issue thread or a design document.
_Avoid_: Context, thread (when used loosely)
