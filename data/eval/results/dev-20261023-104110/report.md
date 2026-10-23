split `dev` · 2 questions (0 human-verified) · answers by `azure` · judge `azure` · prompt v4 · workspace `eval`

# Benchmark results

Mean over questions with 95% bootstrap interval in brackets. Differences smaller than the interval width are noise.

## Answerable questions (tiers A, B)

| system | n | correct | evidence recall | wrongly refused |
|---|---|---|---|---|
| B1 | 0 | - | - | - |

## Questions with no evidence: false-answer rate (lower is better)

| system | C n | C | N n | N | T n | T | all |
|---|---|---|---|---|---|---|---|
| B1 | 0 | - | 1 | 100% [100-100] | 1 | 100% [100-100] | 100% [100-100] |

## Citations, cost, failures

| system | cites | hallucinated cites | seconds/question | tokens/question | errors |
|---|---|---|---|---|---|
| B1 | 4 | 25% | 15.8 | 4542 | 0 |
