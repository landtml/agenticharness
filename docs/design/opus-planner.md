# Planner: one strong model plans, cheap workers execute

Status: draft · 2026-10-14 (updated after bench rounds 1–4) · `src/urh/planner.py`, stacked on the scaffold (PR #1)

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
next_step:  latest plan from the journal, or plan the goal            (manager, medium effort)
            if the plan has no detailed step at step_index:
                expand the next milestone from verified facts          (manager, medium effort)
            no milestone left -> done

on a step:  worker attempt -> gate (own checks + every earlier step's checks as regressions)
            fail   -> repair at one effort level higher (low -> medium -> high)
            unsure -> the step's planner checks could not be trusted: replan it, then park
            repairs exhausted:
                plan-shaped failure (missing file or symbol, untrusted checks, or a second
                struggling step on the run) -> replan first
                otherwise -> one escalation attempt if the budget affords it, then replan
                -> park only if the replan fails or the caps are hit
```

`journal.replan_step` is fenced like every other write: it swaps the step, marks its failed
attempts `superseded`, and records `step_replanned`, so the repair counter starts fresh for
the new step and a stale process cannot apply a replan.

## No drift, no false done

- **Regression checks.** Every later step reruns the plan checks of the steps before it. A step
  that breaks verified work fails its own gate, where the failure is cheap to repair, instead of
  surfacing at the end. A step that changes earlier behaviour on purpose names the checks it
  retires (`retire_checks`), and the validator rejects retiring a check nobody wrote.
- **Vetted planner checks.** A step decided only by planner-written checks passes only if the
  gate package's `plancheck` vetting trusts at least one of them: the check must fail on the parent
  tree, on sabotaged copies and on most mutants of the step's files. An untrusted check sends the
  step back to the planner. The validator also rejects checks that run tests the workers write.
- **Fixes in code, not retries.** A plan whose last step forgets the task's own checks gets them
  added in code; asking the model again cost a second planner call for a fix with one answer.

## Balancing cost and judgment over long horizons

The rule: the strong model decides what to do, the cheap model does it, code and gates
decide whether it worked. The strong model never runs a tool or checks a result.

| Moment | Who | Why it is worth it |
| --- | --- | --- |
| Initial plan | manager, effort `medium` | Decomposition and check design are where a wrong call costs every later step. |
| Milestone expansion | manager, effort `medium` | Rolling horizon: detailed steps only for the next milestone, written from what the gates verified. |
| Replan | manager, effort `high` | Only after evidence the plan was wrong. Capped per run (`max_replans`, `max_plan_calls`). |
| Step attempt | worker, effort from the plan | `low` for scaffolding, higher for tricky logic. |
| Repair | worker, one effort level higher | Gets the gate's failure, never the worker's story. |
| Escalation | escalation role (stronger model) | One attempt, only for a plan that looks right, only if the budget affords it. |
| Judging done | gate scripts | No model call where a command decides. |

Measured on the bench (goal-only tasks, hidden tests as the spec check):

| Planner effort | Verified | False done | Parks | Cost per verified run |
| --- | --- | --- | --- | --- |
| high (round 1) | 5 of 6 | 0 | 1 (budget, after escalation ate it) | about $0.50 |
| medium (round 2) | 6 of 6 | 0 | 0 | $0.14 |
| plain single worker, no planner or gate | 2 of 6 | 4 | 0 | $0.04 |

Medium effort verified as often as high at about a third of the cost, so it is the default;
replans keep high effort. Escalation was the largest cost on failing steps before it was capped
and moved behind plan-shaped replans.

## Measuring it

`bench/run.py` gives the harness only each task's goal; hidden tests are the gate's spec check,
so `done` means they passed in the gate's own checkout, and the final tree is scored again
outside the harness. It reports verified rate, false done, park rate, replans, escalations,
cost by role and `urh.stats`, and `--mode plain` runs the single-worker baseline. Outage parks
are retried after their cooldown, as the daemon does. Results are in `bench/results/`.

## Not in this change

- Codifying recurring plans into templates (the journal keeps every plan as data for it).
- A model judge for checks a command cannot decide; that belongs to the gate module.
