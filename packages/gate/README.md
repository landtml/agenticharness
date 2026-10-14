# urh-gate: the step gate

The gate decides whether a worker's step is done by testing the artifact the
worker left behind. It never reads the worker's report. It works the same
whichever model wrote the code, because it only judges the code.

Standard library only. Python 3.11 or newer.

```
python -m urh_gate check --contract _hidden/contract.py --workspace .   # exit 0 pass, 1 fail, 2 park
```

## What a contract holds

Each kind of step has a hidden contract (`hidden/contract.py`). Workers never see it:

- a reference implementation (the oracle)
- argument generators with edge cases, random draws and shrinkers
- hidden examples, relational properties, and regressions from past escapes
- an input domain for synthesized inputs

## How a candidate is judged

Phases run from cheapest to most expensive, and the first failure stops the run:

| phase | what it does |
|---|---|
| static | Blocks escape hatches: system modules, frame walking, monkeypatching, environment sniffing. |
| examples | Runs the hidden examples. |
| edges | Runs the generator's edge cases. |
| random | Runs seeded random cases. Half are seeded by the artifact and a secret salt. The other half come from a fixed stream. |
| targeted | Builds inputs from the candidate's own literals, such as a `[:8]` cap, a `> 3999` check or a special-cased string. The variant budget is shared round-robin across strategies. |
| properties | Checks multi-call relations such as round trips and idempotence. |
| determinism | Replays every case in one process, then a reversed sample in a fresh process with another hash seed. Catches stateful or call-counting code. |

A failure comes back with a shrunk counterexample. The repair note mentions no
paths and is safe to show the worker. A contract whose reference raises gets
`park`, not `fail`.

The sandbox is a child process with these protections:

- rlimits on memory, CPU time and file size
- an audit hook that denies open, process creation, sockets, ctypes, fresh imports, frame walking and gc
- hidden modules
- a builtins fingerprint that is restored after every call
- a private serializer, and exception classes checked with exact `type()`
- a nonce-framed report sent on a private fd

The secret salt comes from `URH_GATE_SALT` or `~/.config/urh/gate-salt`.
Keep it out of worker sandboxes.

## Planner-written checks

`plancheck.vet` audits a planner's shell check before that check may gate a
step. It runs these tests:

- **policy:** the check must not be trivially true, check only that a file exists, run tests the worker wrote, or use the network
- **positive:** the check passes on the candidate
- **vacuity:** the check fails on the parent tree
- **sabotage:** the check fails when the step's files are deleted, emptied or stubbed
- **mutation:** the check kills enough mutants of the step's code

`gate_step` returns pass only when at least one check is trusted. Otherwise it returns unsure, and the step goes back to the planner.

## Measuring it

```
python -m urh_gate.evaluate label     # ground truth: writer intent + deep differential + witness inputs
python -m urh_gate.evaluate run       # gate configs and ablations -> evalset/RESULTS.md
python -m urh_gate.audit evalset/tasks/*          # contract self-audit: reference, stubs, mutant gaps
python -m urh_gate.live --worker "claude -p --model claude-haiku-5-5"   # live workers + repair loop
```

`--worker` takes any command that reads a prompt on stdin and prints a reply,
so the live eval runs against any model or provider.

The blind corpus (`evalset/corpus`) was written by Haiku 5.5 agents from
`spec.md` alone. They never saw the contracts. Ground truth never comes from
the gate. Labels come from the writer's stated intent and a deep differential
run (25x the random budget, a different salt, no static or targeted phase),
plus the writer's own exposing input for rare-input bugs. Any disagreement
goes to `label_overrides.json` for a human ruling.

`crosscheck/slug` is a contract for the scaffold's slug example. It was
written from the step instructions alone, to check the gate against corpora
it was not built on.

Results: [evalset/RESULTS.md](evalset/RESULTS.md).

### Current numbers (2026-10-14)

Corpus: 223 labelled candidates (183 broken or gaming, 40 correct) across 8 tasks.

| | false accepts | false withholds | parks |
|---|---|---|---|
| hidden examples only (old-style gate) | 124 / 183 (67.8%) | 0 / 40 | 0 |
| full gate | **0 / 183** (95% CI 0.0–2.1%) | **0 / 40** | **0** |

For comparison, the prototype's gate in the artifact accepted 13 of 33 blind broken versions (39%).

Ablations show which phases pay for themselves:

- Without the targeted phase, the gate accepts 21 of 64 rare-input bugs.
- Without edge cases, it accepts 2 of 64.
- Without random cases and properties together, it accepts 4 of 183.
- Static policy and properties each catch nothing that a later phase misses on this corpus. They stay as defence in depth against gaming: static policy is the cheap first line, and properties cover multi-call contracts.

Caveat: the rare-input family was used while developing the targeted phase. It
is not a fresh test of that phase. Only the blind family (119) is fully
held out. The next round adds a fresh rare-input family.

Live run (`evalset/live/haiku-r1`): Haiku 5.5 workers wrote 40 solutions (8 tasks × 5) from `spec.md`.

- 40 of 40 passed on the first try, and the labeller confirmed all of them.
- 0 false withholds, 0 parks, 0 repairs needed.
- These tasks are within Haiku's reach, so this run measures false withholds and park rate. The corpus measures false accepts.

Cross-check (`crosscheck/slug`): the contract was written from the scaffold's
slug step instructions alone. It rejects all 35 of the scaffold's own slug
mutants, 15 known and 20 blind, and passes the reference.
