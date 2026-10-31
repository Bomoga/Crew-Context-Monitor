from __future__ import annotations

from typing import Any

import pytest

from ccm_sim.engine import build_world, run_world
from ccm_sim.messages import CABIN_TOPIC, SIM_EVENT_TOPIC, WEARABLE_TOPIC
from ccm_sim.scenario import load_scenario, scenario_from_dict
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.timeutil import DEFAULT_START

M = 60.0
T0 = DEFAULT_START


def run(name: str, seed: int = 1) -> tuple[Any, list[Record]]:
    world = build_world(load_scenario(name), seed, T0)
    sink = MemorySink()
    run_world(world, sink)
    return world, sink.records


def node_records(records: list[Record], node: str) -> list[Record]:
    return [r for r in records if r.payload.get("id") == node]


def status_states(records: list[Record], node: str) -> list[tuple[str, float]]:
    return [
        (r.payload["state"], r.payload["t"])
        for r in node_records(records, node)
        if "/status/" in r.topic
    ]


def test_wifi_dropout_status_sequence_and_silence() -> None:
    _, records = run("wifi_dropout")
    assert status_states(records, "C1") == [
        ("online", T0),
        ("offline", T0 + 10 * M),
        ("online", T0 + 18 * M),
        ("offline", T0 + 40 * M),
    ]
    # nothing from C1 is published between the offline and the online status
    c1 = node_records(records, "C1")
    i_off = next(i for i, r in enumerate(c1) if r.payload.get("state") == "offline")
    i_on = next(i for i, r in enumerate(c1) if i > i_off and r.payload.get("state") == "online")
    assert i_on == i_off + 1


def test_wifi_flush_has_no_seq_gaps_and_original_times() -> None:
    _, records = run("wifi_dropout")
    cabin = [r.payload for r in records if r.topic == CABIN_TOPIC]
    assert [m["seq"] for m in cabin] == list(range(1, len(cabin) + 1))
    c1 = node_records(records, "C1")
    i_on = next(i for i, r in enumerate(c1) if r.payload.get("state") == "online" and i > 0)
    flushed = [r.payload for r in c1[i_on + 1 :] if r.topic == CABIN_TOPIC][:48]
    assert len(flushed) == 48  # 8 minutes at one message per 10 s
    assert all(T0 + 10 * M <= m["t_meas"] < T0 + 18 * M for m in flushed)
    assert [m["t_meas"] for m in flushed] == sorted(m["t_meas"] for m in flushed)
    after = [r.payload for r in c1[i_on + 49 :] if r.topic == CABIN_TOPIC][0]
    assert after["t_meas"] == T0 + 18 * M  # the first message after the silence


def test_wifi_every_minute_has_a_cabin_message_by_t_meas() -> None:
    world, records = run("wifi_dropout")
    minutes = {
        int((r.payload["t_meas"] - T0 - 1e-6) // M) for r in records if r.topic == CABIN_TOPIC
    }
    assert minutes == set(range(int(world.duration // M)))


def test_wifi_wearables_are_unaffected() -> None:
    _, records = run("wifi_dropout")
    for crew in ("W1", "W2", "W3"):
        seqs = [
            r.payload["seq"]
            for r in records
            if r.topic == WEARABLE_TOPIC and r.payload["crew"] == crew
        ]
        assert seqs == list(range(1, len(seqs) + 1))


def test_ble_dropout_resends_the_last_sixty_seconds() -> None:
    world, records = run("ble_dropout")
    assert status_states(records, "W1")[:3] == [
        ("online", T0),
        ("offline", T0 + 10 * M),
        ("online", T0 + 11 * M),
    ]
    w1 = [r.payload for r in records if r.topic == WEARABLE_TOPIC and r.payload["crew"] == "W1"]
    assert [m["seq"] for m in w1] == list(range(1, len(w1) + 1))
    gap = [m for m in w1 if T0 + 10 * M <= m["t_meas"] < T0 + 11 * M]
    assert len(gap) == 12
    times = sorted(m["t_meas"] for m in w1)
    assert all(b - a == pytest.approx(5.0) for a, b in zip(times, times[1:], strict=False))
    assert world.missing_marks == []


def test_events_name_the_node_and_publish_start_and_end() -> None:
    _, records = run("ble_dropout")
    events = [r.payload for r in records if r.topic == SIM_EVENT_TOPIC]
    assert [(e["label"], e["phase"], e["crew"]) for e in events] == [
        ("W1 Bluetooth link drops", "start", "W1"),
        ("W1 Bluetooth link returns", "end", "W1"),
    ]


def test_unbuffered_silence_leaves_a_seq_gap() -> None:
    effect = {"op": "silence", "node": "C1", "for": "2m", "buffer": False}
    raw = {
        "name": "lossy",
        "title": "Lossy",
        "duration": "20m",
        "crew": ["W1"],
        "marks": [],
        "expect": [],
        "events": [{"at": "5m", "name": "loss", "label": "Link drops", "effects": [effect]}],
    }
    world = build_world(scenario_from_dict(raw), 1, T0)
    sink = MemorySink()
    run_world(world, sink)
    seqs = [r.payload["seq"] for r in sink.records if r.topic == CABIN_TOPIC]
    assert len(seqs) == 120 - 12 and seqs[0] == 1
    assert max(b - a for a, b in zip(seqs, seqs[1:], strict=False)) == 13
