# Natural GSM8K evaluation (gpt-4o-mini, 30 problems, paired)

## Accuracy

| System | Correct | Acc % | 95% Wilson CI | No answer | vs A0 (fixed/broken, McNemar) |
|---|---|---|---|---|---|
| A0 | 27/30 | 90.0 | [74.4, 96.5] | 0 | - |
| A2 | 27/30 | 90.0 | [74.4, 96.5] | 0 | +1/-1, p=1.000 |
| A3 | 23/30 | 76.7 | [59.1, 88.2] | 0 | +0/-4, p=0.125 |
| A4 | 27/30 | 90.0 | [74.4, 96.5] | 0 | +1/-1, p=1.000 |

## Recovery metrics

ECR: share of examples with a detected fault that end wrong. RSR: recovery attempts accepted on re-verification. CDR: previously accepted claims that recovery rewrote or discarded. Plan accepted: recovered plans that pass verification.

| System | ECR % | RSR % | CDR % | Plan accepted after recovery % |
|---|---|---|---|---|
| A0 | n/a | n/a | n/a | n/a |
| A2 | 10.0 (3/30) | 0.0 (0/90) | n/a | 0.0 (0/30) |
| A3 | 23.3 (7/30) | 0.0 (0/275) | n/a | 0.0 (0/30) |
| A4 | 10.0 (3/30) | 0.0 (0/90) | n/a | 0.0 (0/30) |

## Cost per problem (cached calls counted at their original cost)

| System | Mean tokens | vs A0 | Mean LLM calls | Mean model time (s) |
|---|---|---|---|---|
| A0 | 1383 | 1.00x | 3.0 | 4.4 |
| A2 | 23832 | 17.24x | 50.5 | 72.1 |
| A3 | 14198 | 10.27x | 33.5 | 40.7 |
| A4 | 23832 | 17.24x | 50.5 | 72.1 |

## A4 scope choices

| Scope | Count | Accuracy % |
|---|---|---|
| full | 30 | 90.0 (27/30) |

All systems agree on 25/30 problems; they differ on 5.
Verification flagged a fault in 30/30 initial plans.