"""The mock API running a playlist (the demo): steps run in turn as one unbroken run."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ccm_sim import contracts
from ccm_sim.cli import main
from ccm_sim.mockapi.app import create_app
from ccm_sim.mockapi.state import MockState
from ccm_sim.playlist import is_playlist
from ccm_sim.replay import read_rows, replay
from ccm_sim.sinks import MemorySink

T0 = 1_793_491_200.0
H = 3600.0


def make() -> tuple[MockState, TestClient]:
    state = MockState("demo", "max", t0=T0)
    return state, TestClient(create_app(state))


def test_demo_is_a_playlist_and_a_scenario_is_not() -> None:
    assert is_playlist("demo") and not is_playlist("scrubber_failure")
    assert not is_playlist("no_such_thing")


def test_the_run_covers_all_three_steps() -> None:
    state, _ = make()
    assert state.t_end - state.t0 == (4 + 8 + 3) * H


def test_each_step_shows_its_own_story_and_every_response_validates() -> None:
    state, client = make()
    checks = [
        (T0 + 3 * H + 40 * 60, "scrubber_failure", ("yellow", "red", "green", "green")),
        (T0 + 4 * H + 5 * H, "individual_illness", ("yellow", "green", "green", "green")),
        (T0 + 12 * H + 85 * 60, "solar_particle_event", ("green", "green", "green", "red")),
    ]
    for t, scenario, levels in checks:
        state.advance_to(t)
        assert state.world.name == scenario
        body = client.get("/api/status").json()
        contracts.validate("status", body)
        assert tuple(c["level"] for c in body["cards"]) == levels, scenario
        contracts.validate("events", client.get("/api/events").json())
        contracts.validate("earth_queue", client.get("/api/earth-queue").json())
        contracts.validate(
            "history", client.get("/api/history", params={"metric": "co2_mmhg"}).json()
        )


def test_events_keep_earlier_steps_and_the_step_marks_in_order() -> None:
    state, client = make()
    state.advance_to(T0 + 14 * H)
    events = client.get("/api/events", params={"limit": 1000}).json()["events"]
    sim = [e["sentence"] for e in events if e["kind"] == "sim_event"]
    assert sim[:5] == [
        "Simulated: Scrubber fault begins",
        "Simulated: CO2 passes 2.5 mmHg",
        "Simulated: CO2 passes 3.0 mmHg",
        "Simulated: One crew member changes",
        "Simulated: W2 illness begins",
    ]
    assert sim[-1].startswith("Simulated: Solar particle event")
    assert [e["t"] for e in events] == sorted(e["t"] for e in events)
    assert {"drift", "spike", "correlation"} <= {e["kind"] for e in events}
    ids = [e["id"] for e in events]
    assert len(set(ids)) == len(ids)


def test_nodes_stay_online_across_steps_and_red_summaries_are_queued() -> None:
    state, client = make()
    state.advance_to(T0 + 13 * H + 30 * 60)
    status = client.get("/api/status").json()
    assert {n["state"] for n in status["nodes"]} == {"online"}
    assert not any(e["kind"] == "node" for e in client.get("/api/events").json()["events"])
    tiers = [i["tier"] for i in client.get("/api/earth-queue").json()["items"]]
    assert tiers[3:] == ["flight_surgeon", "urgent"]  # Air red in step 1, radiation red in step 3


def test_the_background_thread_runs_every_step_to_the_end() -> None:
    state = MockState("demo", 3_000_000.0, t0=T0)
    state.start()
    state._thread.join(timeout=90)  # type: ignore[union-attr]
    assert state.finished and state.t_now == state.t_end
    assert [w.name for w in state.worlds] == [
        "scrubber_failure",
        "individual_illness",
        "solar_particle_event",
    ]


def test_generate_writes_a_replay_csv_that_replays_in_order(tmp_path: Path) -> None:
    out = tmp_path / "demo.csv"
    assert main(["generate", "--playlist", "demo", "--duration", "1h", "--out", str(out)]) == 0
    rows = read_rows(out)
    assert len(rows) > 5000
    sink = MemorySink()
    replay(rows, sink, "max", retime=True, now=2_000_000_000.0)
    assert len(sink.records) == len(rows)
    for record in sink.records[:50]:
        kind = "node_status" if "/status/" in record.topic else None
        if kind is None and record.topic == "ccm/wearable/telemetry":
            kind = "wearable_telemetry"
        if kind:
            contracts.validate(kind, record.payload)


@pytest.mark.parametrize("name", ["scrubber_failure", "quiet_day"])
def test_single_scenarios_still_default_to_sixty_times(name: str) -> None:
    state = MockState(name, None, t0=T0)
    assert state.speed == 60.0 and state.playlist is None
