You grade one answer to a question about why a piece of CockroachDB SQL schema-change code is the way it is.

You get the question, a numbered list of required facts, a numbered list of superseded facts (possibly "(none)"), and the answer. The answer lists the Decisions it reports, each with a status (live, superseded or refined), followed by its text.

Judge only what the answer says. Do not use your own knowledge of CockroachDB, and do not reward an answer for being plausible.

Return:
- covered: one entry per required fact, in order. True when the answer states the fact or clearly implies it; a paraphrase counts, a related but different claim does not. An answer that refuses, or says the reason is unknown, covers no fact.
- presented_as_live: one entry per superseded fact, in order. True when the answer presents that fact as still live, that is as how things work now: for example as a live Decision, or in the present tense without saying it changed. Mentioning it as past, reverted, superseded or narrowed is false.
- reports_change: true when the answer says that an earlier choice was reversed, replaced, reverted or narrowed by a later one. With no superseded facts, return false.
