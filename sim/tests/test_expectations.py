from __future__ import annotations

import copy
from typing import Any

import pytest

from ccm_sim.cli import main
from ccm_sim.engine import World, build_world
from ccm_sim.expectations import (
    ExpectError,
    check_expectations,
    correlation_at,
    resolve_time,
    states_at,
)
from ccm_sim.scenario import list_scenarios, load_scenario, scenario_from_dict
from ccm_sim.timeutil import DEFAULT_START

M = 60.0
H = 3600.0
T0 = DEFAULT_START


def world_of(name: str, expect: list[dict[str, Any]] | None = None) -> World:
    scenario = load_scenario(name)
    if expect is not None:
        raw = copy.deepcopy(scenario.raw)
        raw["expect"] = expect
        scenario = scenario_from_dict(raw)
    return build_world(scenario, 1, T0)


def test_every_scenario_has_an_expect_block_and_is_consistent() -> None:
    names = list_scenarios()
    assert len(names) >= 11
    for name in names:
        world = world_of(name)
        assert world.scenario.expect, name
        assert check_expectations(world) == [], name


def test_scenarios_check_command_lists_all_consistent(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["scenarios", "check"]) == 0
    out = capsys.readouterr().out
    assert "INCONSISTENT" not in out
    assert out.count("consistent") == len(list_scenarios())


def test_air_red_window_must_lie_where_co2_is_at_or_above_red() -> None:
    bad = [{"card": "air", "level": "red", "from": "cabin.co2 >= air.co2.yellow"}]
    problems = check_expectations(world_of("scrubber_failure", bad))
    assert problems and "air red" in problems[0]


def test_quiet_claim_is_rejected_when_the_truth_is_not_green() -> None:
    problems = check_expectations(world_of("scrubber_failure", [{"quiet": ["air"]}]))
    assert problems and "quiet air" in problems[0]


def test_cardio_yellow_before_detectable_is_rejected() -> None:
    early = [
        {
            "card": "cardio",
            "level": "yellow",
            "from": "mark:co2_passes_yellow + 25m",
            "attribution": "cabin",
            "crew": "*",
        }
    ]
    assert check_expectations(world_of("scrubber_failure", early))


def test_wrong_attribution_and_wrong_crew_are_rejected() -> None:
    wrong_attr = [
        {"card": "cardio", "level": "yellow", "from": "3h", "attribution": "cabin", "crew": ["W2"]}
    ]
    assert any(
        "attribution" in p for p in check_expectations(world_of("individual_illness", wrong_attr))
    )
    wrong_crew = [{"card": "cardio", "level": "yellow", "from": "3h", "crew": ["W1"]}]
    assert check_expectations(world_of("individual_illness", wrong_crew))


def test_correlation_lag_and_no_correlation_claims() -> None:
    assert check_expectations(
        world_of("scrubber_failure", [{"correlation": {"x": "a", "y": "b", "lag_min": [1, 5]}}])
    )
    assert check_expectations(world_of("scrubber_failure", [{"no_correlation": True}]))
    assert check_expectations(world_of("coincident_trends", [{"no_correlation": True}])) == []


def test_node_window_must_match_the_silence() -> None:
    off = [{"node": "C1", "state": "offline", "from": "11m", "until": "18m"}]
    assert check_expectations(world_of("wifi_dropout", off))
    assert check_expectations(world_of("quiet_day", [{"node": "C1", "state": "offline"}]))


def test_unresolvable_mark_and_condition_are_reported() -> None:
    assert check_expectations(
        world_of("quiet_day", [{"card": "air", "level": "red", "from": "mark:nope"}])
    )
    assert check_expectations(
        world_of("quiet_day", [{"card": "air", "level": "red", "from": "cabin.co2 >= air.co2.red"}])
    )
    with pytest.raises(ExpectError):
        resolve_time("mark:nope", world_of("quiet_day"), 0.0)


def test_resolve_time_forms() -> None:
    w = world_of("scrubber_failure")
    t_yellow = next(e.t for e in w.events if e.name == "co2_passes_yellow")
    assert resolve_time("3h", w, 0) == T0 + 3 * H
    assert resolve_time("mark:co2_passes_yellow + 25m", w, 0) == t_yellow + 25 * M
    assert resolve_time("mark:co2_passes_yellow - 5m", w, 0) == t_yellow - 5 * M
    assert resolve_time("cabin.co2 >= air.co2.yellow", w, 0) == t_yellow
    assert resolve_time(None, w, 123.0) == 123.0


def test_states_over_the_scrubber_timeline() -> None:
    w = world_of("scrubber_failure")
    marks = {e.name: e.t for e in w.events}
    assert {s.level for s in states_at(w, T0 + 10 * M).values()} == {"green"}
    mid = states_at(w, marks["co2_passes_yellow"] + 5 * M)
    assert mid["air"].level == "yellow" and mid["cardio"].level == "green"
    red = states_at(w, marks["co2_passes_red"] + 5 * M)
    assert red["air"].level == "red"
    late = states_at(w, marks["co2_passes_yellow"] + 80 * M)
    assert late["cardio"].level == "yellow" and late["cardio"].attribution == "cabin"
    assert late["cardio"].crew == ("W1", "W2", "W3")
    assert correlation_at(w, T0 + 10 * M) is None
    corr = correlation_at(w, marks["co2_passes_yellow"] + 80 * M)
    assert corr is not None and corr["lag_min"] == [15, 25]


def test_individual_illness_states_name_only_w2() -> None:
    w = world_of("individual_illness")
    s = states_at(w, T0 + 4 * H)
    assert s["cardio"].level == "yellow" and s["cardio"].crew == ("W2",)
    assert s["cardio"].attribution == "individual" and s["air"].level == "green"
    assert states_at(w, T0 + 2 * H)["cardio"].level == "green"


def test_radiation_states_follow_the_windows() -> None:
    w = world_of("solar_particle_event")
    levels = {m: states_at(w, T0 + m * M)["radiation"].level for m in (65, 75, 85, 105, 115)}
    assert levels == {65: "green", 75: "yellow", 85: "red", 105: "red", 115: "green"}


def test_checkpoints_cover_each_expected_state() -> None:
    from ccm_sim.expectations import checkpoints

    cps = checkpoints(world_of("scrubber_failure"))
    domains = ("cardio", "air", "thermal", "radiation")
    summary = ["".join(c["cards"][d]["level"][0] for d in domains) for c in cps]
    assert (
        summary[0] == "gggg" and "gygg" in summary and "grgg" in summary and summary[-1] == "yrgg"
    )
    assert [c["correlation"] for c in cps][-1] is True
    assert cps[-1]["cards"]["cardio"]["attribution"] == "cabin"
    assert cps[-1]["sim_events"] == [
        "Scrubber fault begins",
        "CO2 passes 2.5 mmHg",
        "CO2 passes 3.0 mmHg",
    ]
    offsets = [c["offset"] for c in cps]
    assert offsets == sorted(offsets) and all(120 <= o <= 14400 - 60 for o in offsets)


def test_checkpoints_name_the_offline_node_during_a_dropout() -> None:
    from ccm_sim.expectations import checkpoints

    cps = checkpoints(world_of("ble_dropout"))
    assert [c["offline"] for c in cps] == [[], ["W1"], []]
    cps = checkpoints(world_of("sleep_debt_drift"), max_points=2)
    assert len(cps) == 2 and cps[-1]["cards"]["cardio"]["crew"] == ["W1"]
