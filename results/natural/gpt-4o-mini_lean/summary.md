# Natural GSM8K evaluation (gpt-4o-mini, 30 problems, paired)

## Accuracy

| System | Correct | Acc % | 95% Wilson CI | No answer | vs A0 (fixed/broken, McNemar) |
|---|---|---|---|---|---|
| A0 | 27/30 | 90.0 | [74.4, 96.5] | 0 | - |
| A2 | 27/30 | 90.0 | [74.4, 96.5] | 0 | +0/-0, p=1.000 |
| A3 | 27/30 | 90.0 | [74.4, 96.5] | 0 | +0/-0, p=1.000 |
| A4 | 27/30 | 90.0 | [74.4, 96.5] | 0 | +0/-0, p=1.000 |

## Recovery metrics

ECR: share of examples with a detected fault that end wrong. RSR: recovery attempts accepted on re-verification. CDR: previously accepted claims that recovery rewrote or discarded. Plan accepted: recovered plans that pass verification.

| System | ECR % | RSR % | CDR % | Plan accepted after recovery % |
|---|---|---|---|---|
| A0 | n/a | n/a | n/a | n/a |
| A2 | 16.7 (1/6) | 66.7 (6/9) | 100.0 (47/47) | 100.0 (6/6) |
| A3 | 16.7 (1/6) | 27.3 (3/11) | 0.0 (0/47) | 16.7 (1/6) |
| A4 | 16.7 (1/6) | 20.0 (2/10) | 14.9 (7/47) | 33.3 (2/6) |

## Cost per problem (cached calls counted at their original cost)

| System | Mean tokens | vs A0 | Mean LLM calls | Mean model time (s) |
|---|---|---|---|---|
| A0 | 1383 | 1.00x | 3.0 | 4.4 |
| A2 | 3691 | 2.67x | 5.9 | 12.4 |
| A3 | 3324 | 2.40x | 5.6 | 11.1 |
| A4 | 3499 | 2.53x | 5.7 | 11.6 |

## A4 scope choices

| Scope | Count | Accuracy % |
|---|---|---|
| none | 24 | 91.7 (22/24) |
| isolated | 4 | 100.0 (4/4) |
| branch | 1 | 0.0 (0/1) |
| agent | 1 | 100.0 (1/1) |

All systems agree on 30/30 problems; they differ on 0.
Verification flagged a fault in 6/30 initial plans.