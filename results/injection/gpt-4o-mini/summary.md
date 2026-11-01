# Fault-injection experiment (gpt-4o-mini, verifier=hybrid, 16 injected faults)

## Verifier on clean plans (false alarms)

- Clean pipeline accuracy: 87.5 (7/8)
- Claims wrongly flagged: 0.0 (0/64); plans with at least one false alarm: 0.0 (0/8)
- False alarms by check: {}

## Did the verifier find the injected fault?

| Fault kind | Position | Cases | Detected % | Other claims flagged |
|---|---|---|---|---|
| arithmetic | deep | 6 | 100.0 (6/6) | 10 |
| arithmetic | leaf | 3 | 100.0 (3/3) | 0 |
| operand | deep | 5 | 100.0 (5/5) | 12 |
| operand | leaf | 2 | 100.0 (2/2) | 0 |
| all | all | 16 | 100.0 (16/16) |  |

## Recovery accuracy - Oracle localization (injected claim is given)

| Fault kind | Position | N | None | Isolated | Branch | Agent | Full | A4 | Best possible | A4 = best scope |
|---|---|---|---|---|---|---|---|---|---|---|
| arithmetic | deep | 6 | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 83.3 (5/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 33.3 (2/6) |
| arithmetic | leaf | 3 | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) |
| operand | deep | 5 | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 40.0 (2/5) |
| operand | leaf | 2 | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) |
| all | all | 16 | 100.0 (16/16) | 100.0 (16/16) | 100.0 (16/16) | 93.8 (15/16) | 100.0 (16/16) | 100.0 (16/16) | 100.0 (16/16) | 56.2 (9/16) |

Cost and collateral damage (oracle):

| Scope | Mean tokens per case | CDR % |
|---|---|---|
| none | 1496 | n/a |
| isolated | 2287 | 0.0 (0/98) |
| branch | 2465 | 31.6 (31/98) |
| agent | 3463 | 100.0 (98/98) |
| full | 3434 | 100.0 (98/98) |
| A4 | 2551 | 37.8 (37/98) |

A4 choices (oracle): {'agent': 4, 'branch': 7, 'isolated': 5}

Cheapest scope that gives a correct answer, by fault position (oracle):

| Position | none needed | isolated | branch | agent | full | unrecoverable |
|---|---|---|---|---|---|---|
| deep | 11 | 0 | 0 | 0 | 0 | 0 |
| leaf | 5 | 0 | 0 | 0 | 0 | 0 |

## Recovery accuracy - Detected localization (verifier decides)

| Fault kind | Position | N | None | Isolated | Branch | Agent | Full | A4 | Best possible | A4 = best scope |
|---|---|---|---|---|---|---|---|---|---|---|
| arithmetic | deep | 6 | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 16.7 (1/6) |
| arithmetic | leaf | 3 | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) | 100.0 (3/3) |
| operand | deep | 5 | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 80.0 (4/5) | 100.0 (5/5) | 100.0 (5/5) | 100.0 (5/5) | 0.0 (0/5) |
| operand | leaf | 2 | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) | 100.0 (2/2) |
| all | all | 16 | 100.0 (16/16) | 100.0 (16/16) | 100.0 (16/16) | 93.8 (15/16) | 100.0 (16/16) | 100.0 (16/16) | 100.0 (16/16) | 37.5 (6/16) |

Cost and collateral damage (detected):

| Scope | Mean tokens per case | CDR % |
|---|---|---|
| none | 1496 | n/a |
| isolated | 2641 | 0.0 (0/76) |
| branch | 2744 | 11.8 (9/76) |
| agent | 3561 | 100.0 (76/76) |
| full | 3434 | 100.0 (76/76) |
| A4 | 2793 | 30.3 (23/76) |

A4 choices (detected): {'full': 4, 'agent': 2, 'branch': 5, 'isolated': 5}

Cheapest scope that gives a correct answer, by fault position (detected):

| Position | none needed | isolated | branch | agent | full | unrecoverable |
|---|---|---|---|---|---|---|
| deep | 11 | 0 | 0 | 0 | 0 | 0 |
| leaf | 5 | 0 | 0 | 0 | 0 | 0 |