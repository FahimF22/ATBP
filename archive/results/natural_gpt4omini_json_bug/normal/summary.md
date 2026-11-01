# Natural GSM8K evaluation (gpt-4o-mini, 30 problems, paired)

## Accuracy

| System | Correct | Acc % | 95% Wilson CI | No answer | vs A0 (fixed/broken, McNemar) |
|---|---|---|---|---|---|
| A0 | 28/30 | 93.3 | [78.7, 98.2] | 0 | - |
| A2 | 28/30 | 93.3 | [78.7, 98.2] | 0 | +0/-0, p=1.000 |
| A3 | 26/30 | 86.7 | [70.3, 94.7] | 0 | +1/-3, p=0.625 |
| A4 | 28/30 | 93.3 | [78.7, 98.2] | 0 | +0/-0, p=1.000 |

## Recovery metrics

ECR: share of examples with a detected fault that end wrong. RSR: recovery attempts accepted on re-verification. CDR: previously accepted claims that recovery rewrote or discarded. Plan accepted: recovered plans that pass verification.

| System | ECR % | RSR % | CDR % | Plan accepted after recovery % |
|---|---|---|---|---|
| A0 | n/a | n/a | n/a | n/a |
| A2 | 6.7 (2/30) | 0.0 (0/90) | n/a | 0.0 (0/30) |
| A3 | 13.3 (4/30) | 0.0 (0/275) | n/a | 0.0 (0/30) |
| A4 | 6.7 (2/30) | 0.0 (0/90) | n/a | 0.0 (0/30) |

## Cost per problem (cached calls counted at their original cost)

| System | Mean tokens | vs A0 | Mean LLM calls | Mean model time (s) |
|---|---|---|---|---|
| A0 | 2168 | 1.00x | 3.0 | 6.6 |
| A2 | 25416 | 11.72x | 50.5 | 81.2 |
| A3 | 15357 | 7.08x | 33.5 | 47.4 |
| A4 | 25416 | 11.72x | 50.5 | 81.2 |

## A4 scope choices

| Scope | Count | Accuracy % |
|---|---|---|
| full | 30 | 93.3 (28/30) |

All systems agree on 26/30 problems; they differ on 4.
Verification flagged a fault in 30/30 initial plans.