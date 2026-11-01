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
| A2 | 50.0 (1/2) | 25.0 (1/4) | 100.0 (22/22) | 50.0 (1/2) |
| A3 | 50.0 (1/2) | 0.0 (0/2) | 0.0 (0/22) | 0.0 (0/2) |
| A4 | 50.0 (1/2) | 28.6 (2/7) | 22.7 (5/22) | 0.0 (0/2) |

## Cost per problem (cached calls counted at their original cost)

| System | Mean tokens | vs A0 | Mean LLM calls | Mean model time (s) |
|---|---|---|---|---|
| A0 | 2168 | 1.00x | 3.0 | 6.6 |
| A2 | 4705 | 2.17x | 6.5 | 17.1 |
| A3 | 4141 | 1.91x | 5.2 | 14.4 |
| A4 | 4184 | 1.93x | 5.4 | 14.5 |

## A4 scope choices

| Scope | Count | Accuracy % |
|---|---|---|
| none | 28 | 96.4 (27/28) |
| isolated | 1 | 0.0 (0/1) |
| branch | 1 | 100.0 (1/1) |

All systems agree on 30/30 problems; they differ on 0.
Verification flagged a fault in 2/30 initial plans.