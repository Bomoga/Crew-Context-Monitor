"""Mock API: each endpoint, for each scenario, at five sim times, validates against the contract."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ccm_sim import contracts
from ccm_sim.expectations import states_at
from ccm_sim.mockapi.app import create_app
from ccm_sim.mockapi.state import METRICS, MockState
from ccm_sim.scenario import list_scenarios, load_scenario

T0 = 1_793_491_200.0  # 2026-11-01T00:00:00Z


def make(scenario: str, **kw: Any) -> tuple[MockState, TestClient]:
    state = MockState(scenario, "max", t0=T0, **kw)
    return state, TestClient(create_app(state))


def sample_times(state: MockState) -> list[float]:
    """Five sim times spread over the scenario, skipping the first two minutes."""
    span = state.t_end - state.t0
    return [state.t0 + 120.0 + (span - 120.0) * k / 4 for k in range(5)]


def check_all_endpoints(client: TestClient, state: MockState) -> None:
    r = client.get("/api/status")
    assert r.status_code == 200
    contracts.validate("status", r.json())
    for metric, (_, is_crew) in METRICS.items():
        params = {"metric": metric, "hours": 6, "step": 60}
        if is_crew:
            params["crew"] = state.world.crew[0]
        r = client.get("/api/history", params=params)
        assert r.status_code == 200, (metric, r.text)
        contracts.validate("history", r.json())
    r = client.get("/api/events")
    assert r.status_code == 200
    contracts.validate("events", r.json())


def _scenario_params() -> list[Any]:
    """Multi-day scenarios are slow (a week of data per run), so they run under sim-eval."""
    return [
        pytest.param(n, marks=pytest.mark.slow) if load_scenario(n).duration > 86400 else n
        for n in list_scenarios()
    ]


@pytest.mark.parametrize("name", _scenario_params())
def test_every_endpoint_validates_at_five_times_and_levels_match_expectations(name: str) -> None:
    state, client = make(name)
    for t in sample_times(state):
        state.advance_to(t)
        check_all_endpoints(client, state)
        body = client.get("/api/status").json()
        expected = states_at(state.world, state.t_now)
        for card in body["cards"]:
            want = expected[card["domain"]]
            assert card["level"] == want.level, (name, card["domain"], t - state.t0)
            assert card["attribution"] == want.attribution
        assert [c["domain"] for c in body["cards"]] == ["cardio", "air", "thermal", "radiation"]
        assert body["source_mode"] == "mock"


def test_scrubber_status_tells_the_story() -> None:
    state, client = make("scrubber_failure")
    marks = {e.name: e.t for e in state.world.events}
    state.advance_to(T0 + 20 * 60)
    calm = client.get("/api/status").json()
    assert calm["crew_status"]["level"] == "green" and calm["correlation"] is None
    state.advance_to(marks["co2_passes_red"] + 600)
    red = client.get("/api/status").json()
    assert red["crew_status"]["level"] == "red" and red["crew_status"]["domain"] == "air"
    co2 = next(n for n in red["cards"][1]["numbers"] if n["label"] == "CO2")
    assert co2["value"] >= 3.0 and co2["baseline"] == 0.6
    state.advance_to(marks["co2_passes_yellow"] + 85 * 60)
    late = client.get("/api/status").json()
    assert late["cards"][0]["level"] == "yellow" and late["cards"][0]["attribution"] == "cabin"
    assert late["correlation"] is not None and late["correlation"]["lag_min"] == 20
    assert "consistent with a cabin cause" in late["crew_status"]["sentence"]
    assert [c["level"] for c in late["crew"]] == ["yellow", "yellow", "yellow"]


def test_individual_illness_names_only_w2() -> None:
    state, client = make("individual_illness")
    state.advance_to(T0 + 4 * 3600)
    body = client.get("/api/status").json()
    assert body["cards"][0]["crew"] == ["W2"] and body["cards"][0]["attribution"] == "individual"
    assert [c["level"] for c in body["crew"]] == ["green", "yellow", "green"]
    assert body["cards"][1]["level"] == "green"
    assert "Only W2 changed; cabin within normal" in body["cards"][0]["reason"]


def test_dropout_marks_the_node_offline_then_online() -> None:
    state, client = make("wifi_dropout")
    state.advance_to(T0 + 14 * 60)
    mid = client.get("/api/status").json()
    assert {n["id"]: n["state"] for n in mid["nodes"]}["C1"] == "offline"
    state.advance_to(T0 + 25 * 60)
    after = client.get("/api/status").json()
    assert {n["id"]: n["state"] for n in after["nodes"]}["C1"] == "online"
    kinds = [e["kind"] for e in client.get("/api/events").json()["events"]]
    assert kinds.count("node") == 2
    assert client.get("/api/events").json()["events"][0]["id"] == "e-1"


def test_history_shape_and_parameters() -> None:
    state, client = make("scrubber_failure")
    state.advance_to(T0 + 3 * 3600)
    body = client.get("/api/history", params={"metric": "co2_mmhg", "hours": 3, "step": 300}).json()
    assert body["crew"] is None and body["unit"] == "mmHg"
    assert body["limits"] == {"yellow": 2.5, "red": 3.0}
    times = [p["t"] for p in body["points"]]
    assert times == sorted(times) and all(
        b - a == 300 for a, b in zip(times, times[1:], strict=False)
    )
    assert body["points"][-1]["mean"] > body["points"][0]["mean"]
    prv = client.get("/api/history", params={"metric": "prv", "crew": "W2"}).json()
    assert prv["crew"] == "W2" and prv["cusum"] is not None and prv["baseline"] is not None
    assert client.get("/api/history", params={"metric": "nope"}).status_code == 422
    assert client.get("/api/history", params={"metric": "hr", "crew": "W9"}).status_code == 404


def test_events_since_and_limit_and_sim_flag() -> None:
    state, client = make("scrubber_failure")
    state.advance_to(T0 + 4 * 3600)
    events = client.get("/api/events").json()["events"]
    sims = [e for e in events if e["kind"] == "sim_event"]
    assert [e["sentence"] for e in sims] == [
        "Simulated: Scrubber fault begins",
        "Simulated: CO2 passes 2.5 mmHg",
        "Simulated: CO2 passes 3.0 mmHg",
    ]
    assert all(e["simulated"] for e in sims) and not any(
        e["simulated"] for e in events if e["kind"] != "sim_event"
    )
    assert {"drift", "correlation", "spike"} <= {e["kind"] for e in events}
    t_mid = events[len(events) // 2]["t"]
    newer = client.get("/api/events", params={"since": t_mid}).json()["events"]
    assert all(e["t"] > t_mid for e in newer)
    assert len(client.get("/api/events", params={"limit": 2}).json()["events"]) == 2
    ids = [e["id"] for e in events]
    assert len(set(ids)) == len(ids)


def test_learning_mode_shows_the_time_until_alerts_start() -> None:
    state, client = make("quiet_day", learning=True)
    state.advance_to(T0 + 3600)
    body = client.get("/api/status").json()
    assert all(c["baseline"] == "learning" and c["learning_ends_t"] for c in body["crew"])
    assert "alerts start in 1 h 0 min" in body["crew_status"]["sentence"]
    assert all(n["baseline"] is None for c in body["cards"] for n in c["numbers"])
    state.advance_to(T0 + 3 * 3600)
    assert all(c["baseline"] == "ready" for c in client.get("/api/status").json()["crew"])


def test_scenario_switch_endpoint() -> None:
    state, client = make("quiet_day")
    r = client.post("/api/_mock/scenario", json={"name": "thermal_fault", "speed": "max"})
    assert r.status_code == 200 and state.scenario_name == "thermal_fault"
    assert (
        client.post("/api/_mock/scenario", json={"name": "nope", "speed": "max"}).status_code == 404
    )
    state.advance_to(state.t0 + 3 * 3600)
    assert client.get("/api/status").json()["cards"][2]["level"] in ("yellow", "red")
    assert client.get("/api/_mock/info").json()["scenario"] == "thermal_fault"


def test_background_thread_runs_the_scenario_to_the_end() -> None:
    state = MockState("ble_dropout", "max", t0=T0)
    state.speed = 100000.0
    state.start()
    state._thread.join(timeout=30)  # type: ignore[union-attr]
    assert state.finished and state.t_now == state.t_end


@pytest.fixture(autouse=True)
def _stop_threads() -> Iterator[None]:
    yield


def test_scenario_switch_can_start_already_part_way_in() -> None:
    state, client = make("quiet_day")
    r = client.post(
        "/api/_mock/scenario",
        json={"name": "scrubber_failure", "speed": "max", "fast_forward": 13200},
    )
    assert r.status_code == 200
    assert state.t_now >= state.t0 + 13200 - 10
    body = client.get("/api/status").json()
    assert body["cards"][1]["level"] == "red" and body["cards"][0]["level"] == "yellow"
    bad = client.post("/api/_mock/scenario", json={"name": "quiet_day", "fast_forward": -5})
    assert bad.status_code == 422
