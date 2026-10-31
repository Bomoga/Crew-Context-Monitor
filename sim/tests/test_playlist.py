from __future__ import annotations

from pathlib import Path

import pytest

from ccm_sim.cli import main
from ccm_sim.messages import CABIN_TOPIC, SIM_EVENT_TOPIC, WEARABLE_TOPIC
from ccm_sim.playlist import load_playlist, run_playlist
from ccm_sim.scenario import ScenarioError
from ccm_sim.sinks import MemorySink, Record, read_jsonl
from ccm_sim.timeutil import DEFAULT_START


@pytest.fixture(scope="module")
def demo_records(tmp_path_factory: pytest.TempPathFactory) -> list[Record]:
    out = tmp_path_factory.mktemp("demo") / "demo.jsonl"
    assert main(["generate", "--playlist", "demo", "--out", str(out)]) == 0
    return read_jsonl(out)


def test_demo_playlist_steps_and_speeds() -> None:
    playlist = load_playlist("demo")
    assert [s.scenario for s in playlist.steps] == [
        "scrubber_failure",
        "individual_illness",
        "solar_particle_event",
    ]
    assert playlist.steps[0].speed == 60 and all(s.label for s in playlist.steps)


def test_sim_events_appear_in_order(demo_records: list[Record]) -> None:
    events = [r.payload for r in demo_records if r.topic == SIM_EVENT_TOPIC]
    assert [e["name"] for e in events] == [
        "demo_step_1",
        "scrubber_fault",
        "co2_passes_yellow",
        "co2_passes_red",
        "demo_step_2",
        "w2_illness",
        "demo_step_3",
        "solar_particle_event",
        "solar_particle_event_end",
    ]
    assert [e["t_meas"] for e in events] == sorted(e["t_meas"] for e in events)
    assert [e["label"] for e in events if e["name"].startswith("demo_step")] == [
        "CO2 scrubber failure",
        "One crew member changes",
        "Solar particle event",
    ]


def test_time_and_sequence_numbers_continue_across_steps(demo_records: list[Record]) -> None:
    for crew in ("W1", "W2", "W3"):
        wearable = [r.payload for r in demo_records if r.topic == WEARABLE_TOPIC]
        msgs = [m for m in wearable if m["crew"] == crew]
        assert [m["seq"] for m in msgs] == list(range(1, len(msgs) + 1))
        gaps = {round(b["t_meas"] - a["t_meas"], 3) for a, b in zip(msgs, msgs[1:], strict=False)}
        assert gaps == {5.0}
        assert len(msgs) == (4 + 8 + 3) * 720
    cabin = [r.payload for r in demo_records if r.topic == CABIN_TOPIC]
    assert [m["seq"] for m in cabin] == list(range(1, len(cabin) + 1))
    assert cabin[0]["t_meas"] == DEFAULT_START + 10


def test_nodes_stay_online_between_steps(demo_records: list[Record]) -> None:
    states = [r.payload["state"] for r in demo_records if "/status/" in r.topic]
    assert states == ["online"] * 4 + ["offline"] * 4


def test_run_playlist_returns_the_worlds_and_counts_published_records() -> None:
    sink = MemorySink()
    sent, worlds = run_playlist(load_playlist("demo"), sink, 1, DEFAULT_START, ["W1"], "max")
    assert [w.name for w in worlds] == [
        "scrubber_failure",
        "individual_illness",
        "solar_particle_event",
    ]
    statuses = [r for r in sink.records if "/status/" in r.topic]
    step_marks = [
        r
        for r in sink.records
        if r.topic == SIM_EVENT_TOPIC and r.payload["name"].startswith("demo_step")
    ]
    assert sent == len(sink.records) - len(statuses) - len(step_marks)
    assert {r.payload["crew"] for r in sink.records if r.topic == WEARABLE_TOPIC} == {"W1"}


def test_unknown_or_non_playlist_names_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError):
        load_playlist("nope")
    with pytest.raises(ScenarioError):
        load_playlist("quiet_day")
    with pytest.raises(SystemExit):
        main(["generate", "--playlist", "nope", "--out", str(tmp_path / "x.jsonl")])
