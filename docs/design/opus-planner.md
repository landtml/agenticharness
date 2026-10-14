# Planner: one strong model plans, cheap workers execute

Status: draft · 2026-10-14 · `src/urh/planner.py`, stacked on the scaffold (PR #1)

## Why

The scaffold's orchestrator runs any step list, but a person has to write that list for
every new kind of task. The recipe names this as the main wall on the headless axis. The
planner removes it: given only a goal, a strong model writes a schema-checked plan, and the
scaffold runs it with cheap workers, the same gates, the same journal and the same effect
guard.

The whole value of the harness is that a run finishes durably and headless, without drift
and without a person rescuing it. A park is a failure to minimize, not a safe default. The
planner's job is therefore twofold: plan well up front, and resolve stuck work on its own
when a step will not converge.

## Roles, not models

The planner is a manager like `CodeManager` and the stepwise `LLMManager`. It calls the
model gateway with role `manager`; the gateway's pins map roles to models and providers.
Nothing in the planner, the orchestrator or the gate assumes a vendor:

- Requests are canonical: system blocks, messages, `effort`, `response_schema`. Each provider
  maps them (Anthropic native, OpenAI-compatible endpoints such as OpenRouter, the `claude`
  CLI). Providers without structured output still work: the planner parses JSON and retries
  once with the validator's errors.
- Effort is a hint (`low | medium | high`). Providers that do not support it ignore it.
- Development and tests here use Opus 5.5 as manager and Haiku 5.5 as worker through the
  `claude-cli` provider, because the container has a signed-in CLI and no API key. That
  provider is one adapter among several; the CLI's own tools are switched off and the
  harness worker's sandboxed tools do all the work.

## The plan

```
Plan
  milestones[]   id, title, outline          # later milestones stay outlines
  steps[]        id, milestone, title,
                 instructions                # one fresh worker context
                 expected_output             # the shape: files, symbols, CLI output
                 files[]                     # what the step should write
                 plan_checks[]               # shell commands the planner writes
                 spec_checks[]               # names of the task's own gate checks
                 effort                      # first-attempt worker effort
```

`plan_errors` rejects duplicate or unknown ids, steps out of milestone order, a step with no
check at all, unknown spec checks, a missing `expected_output`, a bad effort, steps after an
empty milestone, more than 40 steps, and a fully expanded plan whose last step does not run
every spec check. A rejected plan goes back once with the errors; a second rejection parks
the run with reason `plan`.

`plan_checks` exist so intermediate steps can verify before the task's own checks apply.
They run in the gate's checkout, which the worker cannot write to; the planner is told never
to write a check that runs tests the worker wrote.

Every plan, expansion and replan is journaled as a `plan` event before a step runs, so a
restart reads the plan back and never pays for it twice.

## Control loop

```
next_step:  latest plan from the journal, or plan the goal       (one strong call)
            if the plan has no detailed step at step_index:
                expand the next milestone from verified facts     (one strong call)
            no milestone left -> done

on a step:  worker attempt -> gate
            fail -> repair at one effort level higher (low -> medium -> high)
            repairs exhausted, or a repair rebuilds the same failed tree (no progress)
                -> replan the step (verified steps locked, the step must change)
                -> only if the replan fails or the cap is hit: park
```

`journal.replan_step` is fenced like every other write: it swaps the step, marks its failed
attempts `superseded`, and records `step_replanned`, so the repair counter starts fresh for
the new step and a stale process cannot apply a replan.

## Balancing cost and judgment over long horizons

The rule: the strong model decides what to do, the cheap model does it, code and gates
decide whether it worked. The strong model never runs a tool or checks a result.

| Moment | Who | Why it is worth it |
| --- | --- | --- |
| Initial plan | manager, effort `high` | Decomposition and check design are where a wrong call costs every later step. |
| Milestone expansion | manager | Rolling horizon: detailed steps only for the next milestone, written from what the gates verified. |
| Replan | manager | Only after repairs fail. Capped per run (`max_replans`, `max_plan_calls`). |
| Step attempt | worker, effort from the plan | `low` for scaffolding, higher for tricky logic. |
| Repair | worker, one effort level higher | Escalation stays on the cheap model and gets the gate's failure, never the worker's story. |
| Judging done | gate scripts | No model call where a command decides. |

What keeps a long run cheap and on track:

- **Rolling horizon.** A failed early milestone never wastes detailed planning of later ones.
- **No-progress tripwire.** A repair that rebuilds the same failed tree goes straight to a replan.
- **Expected output in every step**, so a milestone is built in the shape its check expects.
- **Byte-stable planner prompt.** Everything per-run goes in the user turn, so the prefix caches.

On the first live runs the planner was about 92% of the dollars on small goals (about $0.065
for the plan against about $0.006 of worker spend). That is acceptable for novel goals but is
the main economic lever: lower planner effort for small goals, and codify recurring plans into
templates so repeat task types skip the planner call.

## Measuring it

`bench/run.py` gives the harness only each task's goal; hidden tests are the gate's spec check,
so `done` means they passed in the gate's own checkout. It reports verified rate, park rate,
replans, cost per verified run and the planner's share of spend. Park rate and drift on long
runs are the headline numbers.

## Not in this change

- Codifying recurring plans into templates (the journal keeps every plan as data for it).
- A model judge for checks a command cannot decide; that belongs to the gate module.
