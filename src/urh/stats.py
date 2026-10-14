"""Outcome metrics across a journal: the numbers each round is judged by.

The recipe measures a harness by what reaches a person, not by what it does
internally. ``human_touches`` counts parks a person had to answer (or that are
still waiting); parks the harness answered itself (``auto:`` answers, such as an
outage wake) are reported separately and cost nobody anything.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .journal import Journal

AUTO_PREFIX = "auto:"


def compute(journal: Journal) -> dict[str, Any]:
    runs = journal.list_runs()
    parks = journal.parks()
    by_status = Counter(r.status for r in runs)
    done = [r for r in runs if r.status == "done"]
    human = [p for p in parks if not (p["answer"] or "").startswith(AUTO_PREFIX)]
    touched_runs = {p["run_id"] for p in human}
    calls = [c for r in runs for c in journal.model_calls(r.id)]
    done_ids = {r.id for r in done}
    cache_read = sum(c["cache_read"] or 0 for c in calls)
    input_tokens = sum(c["input_tokens"] or 0 for c in calls)
    n_done = len(done) or 1
    return {
        "runs": len(runs),
        "by_status": dict(by_status),
        "human_touches": len(human),
        "human_touches_per_run": round(len(human) / (len(runs) or 1), 4),
        # the headline: share of runs that needed a person at least once
        "park_rate": round(len(touched_runs) / (len(runs) or 1), 4),
        "headless_done": sum(1 for r in done if r.id not in touched_runs),
        "auto_resolved_parks": len(parks) - len(human),
        "parks_by_reason": dict(Counter(p["reason"] for p in human)),
        "cost_per_done_usd": round(sum(r.spent_usd for r in done) / n_done, 6) if done else None,
        "calls_per_done": round(sum(1 for c in calls if c["run_id"] in done_ids) / n_done, 2)
        if done
        else None,
        "calls_by_role": dict(Counter(c["role"] for c in calls)),
        "cache_hit_ratio": round(cache_read / (cache_read + input_tokens), 4)
        if cache_read + input_tokens
        else None,
    }
