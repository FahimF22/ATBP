# Fault-injection experiment (qwen2.5:7b, verifier=hybrid, 20 injected faults)

## Verifier on clean plans (false alarms)

- Clean pipeline accuracy: 75.0 (6/8)
- Claims wrongly flagged: 8.3 (4/48); plans with at least one false alarm: 25.0 (2/8)
- False alarms by check: {'llm': 4}

## Did the verifier find the injected fault?

| Fault kind | Position | Cases | Detected % | Other claims flagged |
|---|---|---|---|---|
| arithmetic | deep | 6 | 100.0 (6/6) | 4 |
| arithmetic | leaf | 6 | 100.0 (6/6) | 1 |
| operand | deep | 4 | 50.0 (2/4) | 3 |
| operand | leaf | 4 | 100.0 (4/4) | 0 |
| all | all | 20 | 90.0 (18/20) |  |

## Recovery accuracy - Oracle localization (injected claim is given)

| Fault kind | Position | N | None | Isolated | Branch | Agent | Full | A4 | Best possible | A4 = best scope |
|---|---|---|---|---|---|---|---|---|---|---|
| arithmetic | deep | 6 | 50.0 (3/6) | 100.0 (6/6) | 100.0 (6/6) | 83.3 (5/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 50.0 (3/6) |
| arithmetic | leaf | 6 | 66.7 (4/6) | 100.0 (6/6) | 100.0 (6/6) | 83.3 (5/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) |
| operand | deep | 4 | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 25.0 (1/4) |
| operand | leaf | 4 | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) |
| all | all | 20 | 75.0 (15/20) | 100.0 (20/20) | 100.0 (20/20) | 90.0 (18/20) | 100.0 (20/20) | 100.0 (20/20) | 100.0 (20/20) | 70.0 (14/20) |

Cost and collateral damage (oracle):

| Scope | Mean tokens per case | CDR % |
|---|---|---|
| none | 1417 | n/a |
| isolated | 2243 | 0.0 (0/86) |
| branch | 2272 | 18.6 (16/86) |
| agent | 4136 | 100.0 (86/86) |
| full | 3616 | 100.0 (86/86) |
| A4 | 2276 | 22.1 (19/86) |

A4 choices (oracle): {'branch': 7, 'isolated': 10, 'agent': 3}

Cheapest scope that gives a correct answer, by fault position (oracle):

| Position | none needed | isolated | branch | agent | full | unrecoverable |
|---|---|---|---|---|---|---|
| deep | 7 | 1 | 2 | 0 | 0 | 0 |
| leaf | 8 | 2 | 0 | 0 | 0 | 0 |

## Recovery accuracy - Detected localization (verifier decides)

| Fault kind | Position | N | None | Isolated | Branch | Agent | Full | A4 | Best possible | A4 = best scope |
|---|---|---|---|---|---|---|---|---|---|---|
| arithmetic | deep | 6 | 50.0 (3/6) | 100.0 (6/6) | 100.0 (6/6) | 83.3 (5/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 33.3 (2/6) |
| arithmetic | leaf | 6 | 66.7 (4/6) | 100.0 (6/6) | 100.0 (6/6) | 83.3 (5/6) | 100.0 (6/6) | 100.0 (6/6) | 100.0 (6/6) | 83.3 (5/6) |
| operand | deep | 4 | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 75.0 (3/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 0.0 (0/4) |
| operand | leaf | 4 | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) | 100.0 (4/4) |
| all | all | 20 | 75.0 (15/20) | 100.0 (20/20) | 100.0 (20/20) | 85.0 (17/20) | 100.0 (20/20) | 100.0 (20/20) | 100.0 (20/20) | 55.0 (11/20) |

Cost and collateral damage (detected):

| Scope | Mean tokens per case | CDR % |
|---|---|---|
| none | 1417 | n/a |
| isolated | 2301 | 0.0 (0/74) |
| branch | 2316 | 9.5 (7/74) |
| agent | 3777 | 100.0 (74/74) |
| full | 3505 | 100.0 (74/74) |
| A4 | 2461 | 13.5 (10/74) |

A4 choices (detected): {'branch': 7, 'isolated': 9, 'none': 1, 'full': 2, 'agent': 1}

Cheapest scope that gives a correct answer, by fault position (detected):

| Position | none needed | isolated | branch | agent | full | unrecoverable |
|---|---|---|---|---|---|---|
| deep | 7 | 1 | 2 | 0 | 0 | 0 |
| leaf | 8 | 2 | 0 | 0 | 0 | 0 |