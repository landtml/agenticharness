# Round 4: sessions, and a jail that holds

Round 3 made runs start themselves. This round adds the shape a person actually works in: a session, where
each message is a follow-up on the same codebase. A worker escape that another thread caught in a live
bench forced the sandbox up the list.

## A worker wrote into the real repository

On the planner thread's live bench, a Haiku worker ran `cd /home/user/agenticharness && ...` through the
bash tool and wrote a whole package into the repository root. `urh.sandbox.run` cut only the network. The
worker's file tools refuse paths outside the workspace, but bash had the whole host filesystem.

Commands from the worker and from the gate now run in new user, mount, PID and network namespaces (no
root, no bwrap needed):

- The new root is a tmpfs holding read-only binds of the host's top-level directories. Nothing is created
  on the host.
- `/home`, `/root`, `/tmp`, `/mnt`, `/srv`, `/var/tmp`, `/run`, `/media` and the harness home are empty
  tmpfs. Only `/tmp` is writable.
- The interpreter, its site-packages and any `URH_SANDBOX_RO` paths are bound back read-only, so
  `python -m pytest` works even from a virtualenv under `/home`.
- The command's folder is mounted read-write at `/work`. It is the cwd and `$HOME`.
- A fresh `/proc` in the new PID namespace makes host processes (and their `/proc/<pid>/cwd`) unreachable.
- `URH_SANDBOX=require` refuses to run commands on a host without the namespaces.

`tests/test_sandbox.py` runs the attack: `cd /; ls /home; touch /home/x; touch /usr/x`, reads a hidden
harness home and the test file itself. Every write fails as read-only and every read finds nothing. It
also checks that the workspace stays writable and is shared with the host, that `/proc` holds only the
jail's processes, that there is no network, and that pytest runs. The jail costs about 0.2 s per command.
On hosts that block unprivileged user namespaces (some CI kernels), the jail tests skip and commands fall
back to the old behaviour unless `require` is set.

A second sandbox bug came in from the cost-routing thread. `scrubbed_env` resolved the `python3` symlink,
which in a virtualenv points at the system interpreter without the venv's packages, so `pytest` went
missing on live runs. The PATH now keeps `dirname(sys.executable)` unresolved, the same fix as on their
branch, so the stack merges cleanly.

## Sessions

`urh session new/send/show`, `/v1/sessions`. Each message becomes its own durable run, under the dedupe key
`session:<id>:<seq>`. A run starts from the previous run's last verified commit, never from half-finished
work. Order is strict: a message waits until the run before it is `done` or `failed`, and a parked one holds
the session. Earlier messages and their outcomes reach the planner as untrusted inputs, not instructions.

### The first live session parked, and why

Two messages, the slug task's two step instructions, on the template's gate. Haiku 5.5 did the work and
the default manager planned.

| Run | Result |
| --- | --- |
| Message 1 (ASCII slug) | **parked** `repairs_exhausted` after 3 worker attempts and 1 escalation, $0.28 |
| Message 2 | never started: the park held the session, as designed |

Every attempt passed `basic` and `ascii_property` and failed the unicode checks. Those checks belong to
message 2. Message 1's instructions say "replace every run of characters that are not a-z or 0-9 with a
hyphen", which turns `Crème Brûlée` into `cr-me-br-l-e`, and the unicode test expects `creme-brulee`. The goal contradicted the gate,
so no worker could ever pass, and the repairs and escalation were money spent on an impossible step.

The fix is structural, not a smarter worker. A message names the gate checks it adds (`send(..., checks=)`,
`--check`, `{"checks": [...]}`). A run is gated by its message's checks plus every earlier message's, so
verified behaviour keeps being checked, and a later message's check cannot fail an earlier one. Unknown
check names are rejected at send time. If no message names any, every check applies, as before.

### Rerun

| Message | Checks | Result | Cost |
| --- | --- | --- | --- |
| 1 ASCII slug | basic, ascii_property | done | $0.080 |
| 2 unicode folding | + unicode, unicode_property | done, built on message 1's verified tree | $0.060 |

Park rate 0/2, 2 headless done, 8 model calls (4 manager, 4 worker), prompt cache hit 99.9%, 72 s wall
clock, with every command inside the jail. Raw: `r4-live-session.json`.

## Lessons

- **A check that contradicts the goal is a guaranteed park, and it is expensive.** The harness spent three
  repairs and an escalation before parking. Scoping checks to messages removes the case we hit. A goal and
  a check can still contradict each other inside one message. Detecting that early (the judge or planner
  reading the failing test against the goal before the second repair) is open work.
- **Cutting the network is not a sandbox.** The worker's file tools had path checks, but bash did not.
  Anything a model can run has to be confined at the OS level, and the escape test belongs in the suite.
- **Fixes from other threads should land in the base.** Taking the venv PATH fix in identical form on #1
  keeps the stacked branches conflict-free.

## Next

- Merge order #1 → #2 (planner) → #3 (urh-gate). Then the slug checks move to urh-gate contracts.
- Early contradiction detection, so an impossible step parks after one attempt, not four.
- A per-session spend cap alongside the per-message budget.
