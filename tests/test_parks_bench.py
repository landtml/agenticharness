from urh.bench.parks import SCENARIOS, run_scenario


def test_headless_policy_parks_only_where_a_person_is_needed():
    for name, (_, expected) in SCENARIOS.items():
        row = run_scenario(name, "headless")
        assert row["status"] == expected, row
        assert bool(row["human_touches"]) == (expected == "parked"), row


def test_strict_policy_parks_every_trouble():
    assert run_scenario("provider_outage", "strict")["parks"] == ["outage"]
    assert run_scenario("hard_step", "strict")["parks"] == ["repairs_exhausted"]
