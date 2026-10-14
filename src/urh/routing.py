"""Routing: which role (and so which model) answers each kind of model call, at what effort.

The rule the harness runs on is "the strong model decides, the cheap model does, code checks". Routes
make that rule configuration instead of code. A route names a call site, the roles to try in order,
and the effort hint to send:

    plan     the first plan for a goal
    expand   detailed steps for the next milestone, from verified facts
    replan   a step ran out of repairs: rewrite it

A route with several roles is a cascade: the first role answers, and only an answer the plan validator
rejects (after its own retry) falls through to the next role. So ``{"plan": {"roles": ["planner",
"manager"]}}`` with ``planner`` pinned to a cheap model plans cheaply and pays for the strong model only
when the cheap plan is unusable. Roles map to models through the run's pins, so a route never names a
vendor. Routes are pinned on the run at submit, so a resumed run routes exactly as it started.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SITES = ("plan", "expand", "replan")
EFFORTS = ("low", "medium", "high")


@dataclass(frozen=True)
class Route:
    roles: tuple[str, ...]
    effort: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"roles": list(self.roles), "effort": self.effort}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Route:
        roles = d.get("roles") or ([d["role"]] if d.get("role") else [])
        if not roles or not all(isinstance(r, str) and r for r in roles):
            raise ValueError(f"route needs at least one role: {d!r}")
        effort = d.get("effort")
        if effort is not None and effort not in EFFORTS:
            raise ValueError(f"route effort must be one of {EFFORTS}: {effort!r}")
        return cls(tuple(roles), effort)


def default_routes(plan_effort: str = "medium", replan_effort: str = "high") -> dict[str, Route]:
    """Today's behaviour: the planner role plans and expands, the manager replans after evidence."""
    return {
        "plan": Route(("planner", "manager"), plan_effort),
        "expand": Route(("planner", "manager"), plan_effort),
        "replan": Route(("manager",), replan_effort),
    }


# Named starting points for ``--routing``. Each pairs routes with the role->model overrides it needs;
# model ids here are only defaults and any ``--models`` entry wins.
PRESETS: dict[str, dict[str, Any]] = {
    # The strong model writes every plan.
    "strong-plan": {"routes": {}, "models": {}},
    # The cheap model writes the first plan and expansions; the strong model takes over when the cheap
    # plan is rejected and writes every replan. Escalation stays on the strong model.
    "cheap-plan": {"routes": {}, "models": {"planner": "claude-haiku-5-5"}},
}


def resolve_routes(
    overrides: dict[str, Any] | None,
    plan_effort: str = "medium",
    replan_effort: str = "high",
) -> dict[str, dict[str, Any]]:
    """Defaults merged with overrides, validated, in the plain-dict form pinned on a run."""
    routes = default_routes(plan_effort, replan_effort)
    for site, value in (overrides or {}).items():
        if site not in SITES:
            raise ValueError(f"unknown route site {site!r}; sites are {SITES}")
        value = value.to_dict() if isinstance(value, Route) else dict(value)
        if value.get("role"):
            value["roles"] = [value.pop("role")]
        routes[site] = Route.from_dict({**routes[site].to_dict(), **value})
    return {site: r.to_dict() for site, r in routes.items()}


def route_for(pins: dict[str, Any], site: str, fallback: Route) -> Route:
    """The run's pinned route for ``site``; runs pinned before routing existed use ``fallback``."""
    pinned = (pins.get("routes") or {}).get(site)
    return Route.from_dict(pinned) if pinned else fallback


def cascade(pins: dict[str, Any], route: Route) -> list[str]:
    """The route's roles that the run can serve, dropping any whose model repeats an earlier one's:
    a second try on the same model is the validator retry's job, not the cascade's."""
    models = pins.get("models", {})
    out: list[str] = []
    seen: set[str] = set()
    for role in route.roles:
        model = models.get(role)
        if model is None or model in seen:
            continue
        seen.add(model)
        out.append(role)
    return out


def load_routing(spec: str | None) -> tuple[dict[str, Any], dict[str, str]]:
    """``--routing`` value -> (route overrides, model overrides). Accepts a preset name, a JSON object
    of routes, or a JSON object ``{"preset": ..., "routes": {...}, "models": {...}}``."""
    if not spec:
        return {}, {}
    if spec in PRESETS:
        p = PRESETS[spec]
        return dict(p["routes"]), dict(p["models"])
    try:
        data = json.loads(spec)
    except json.JSONDecodeError as e:
        raise ValueError(f"--routing must be one of {sorted(PRESETS)} or JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("--routing JSON must be an object")
    if not ({"preset", "routes", "models"} & data.keys()):
        return data, {}
    base_routes, base_models = load_routing(data["preset"]) if data.get("preset") else ({}, {})
    return {**base_routes, **(data.get("routes") or {})}, {**base_models, **(data.get("models") or {})}
