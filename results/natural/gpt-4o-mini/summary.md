# Natural GSM8K evaluation (gpt-4o-mini, 30 problems, paired)

## Accuracy

| System | Correct | Acc % | 95% Wilson CI | No answer | vs A0 (fixed/broken, McNemar) |
|---|---|---|---|---|---|
| A0 | 28/30 | 93.3 | [78.7, 98.2] | 0 | - |
| A2 | 28/30 | 93.3 | [78.7, 98.2] | 0 | +0/-0, p=1.000 |
| A3 | 28/30 | 93.3 | [78.7, 98.2] | 0 | +0/-0, p=1.000 |
| A4 | 28/30 | 93.3 | [78.7, 98.2] | 0 | +0/-0, p=1.000 |

## Recovery metrics

ECR: share of examples with a detected fault that end wrong. RSR: recovery attempts accepted on re-verification. CDR: previously accepted claims that recovery rewrote or discarded. Plan accepted: recovered plans that pass verification.

| System | ECR % | RSR % | CDR % | Plan accepted after recovery % |
|---|---|---|---|---|
| A0 | n/a | n/a | n/a | n/a |
| A2 | 25.0 (1/4) | 57.1 (4/7) | 100.0 (30/30) | 100.0 (4/4) |
| A3 | 25.0 (1/4) | 16.7 (1/6) | 0.0 (0/30) | 25.0 (1/4) |
| A4 | 25.0 (1/4) | 16.7 (1/6) | 0.0 (0/30) | 25.0 (1/4) |

## Cost per problem (cached calls counted at their original cost)

| System | Mean tokens | vs A0 | Mean LLM calls | Mean model time (s) |
|---|---|---|---|---|
| A0 | 2168 | 1.00x | 3.0 | 6.6 |
| A2 | 4399 | 2.03x | 5.7 | 14.7 |
| A3 | 4127 | 1.90x | 5.3 | 13.8 |
| A4 | 4127 | 1.90x | 5.3 | 13.8 |

## A4 scope choices

| Scope | Count | Accuracy % |
|---|---|---|
| none | 26 | 96.2 (25/26) |
| isolated | 3 | 100.0 (3/3) |
| branch | 1 | 0.0 (0/1) |

All systems agree on 30/30 problems; they differ on 0.
Verification flagged a fault in 4/30 initial plans.