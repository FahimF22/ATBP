# Natural GSM8K evaluation (qwen2.5:7b, 30 problems, paired)

## Accuracy

| System | Correct | Acc % | 95% Wilson CI | No answer | vs A0 (fixed/broken, McNemar) |
|---|---|---|---|---|---|
| A0 | 26/30 | 86.7 | [70.3, 94.7] | 0 | - |
| A2 | 25/30 | 83.3 | [66.4, 92.7] | 0 | +0/-1, p=1.000 |
| A3 | 25/30 | 83.3 | [66.4, 92.7] | 0 | +0/-1, p=1.000 |
| A4 | 25/30 | 83.3 | [66.4, 92.7] | 0 | +0/-1, p=1.000 |

## Recovery metrics

ECR: share of examples with a detected fault that end wrong. RSR: recovery attempts accepted on re-verification. CDR: previously accepted claims that recovery rewrote or discarded. Plan accepted: recovered plans that pass verification.

| System | ECR % | RSR % | CDR % | Plan accepted after recovery % |
|---|---|---|---|---|
| A0 | n/a | n/a | n/a | n/a |
| A2 | 66.7 (2/3) | 33.3 (2/6) | 100.0 (14/14) | 66.7 (2/3) |
| A3 | 66.7 (2/3) | 33.3 (2/6) | 0.0 (0/14) | 33.3 (1/3) |
| A4 | 66.7 (2/3) | 12.5 (1/8) | 28.6 (4/14) | 0.0 (0/3) |

## Cost per problem (cached calls counted at their original cost)

| System | Mean tokens | vs A0 | Mean LLM calls | Mean model time (s) |
|---|---|---|---|---|
| A0 | 2059 | 1.00x | 3.0 | 99.0 |
| A2 | 4435 | 2.15x | 6.5 | 245.5 |
| A3 | 4049 | 1.97x | 6.2 | 228.3 |
| A4 | 4219 | 2.05x | 6.4 | 236.2 |

## A4 scope choices

| Scope | Count | Accuracy % |
|---|---|---|
| none | 27 | 88.9 (24/27) |
| branch | 2 | 50.0 (1/2) |
| agent | 1 | 0.0 (0/1) |

All systems agree on 29/30 problems; they differ on 1.
Verification flagged a fault in 3/30 initial plans.