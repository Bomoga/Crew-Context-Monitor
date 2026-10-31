from collections import Counter
from pathlib import Path

import pytest

from ccm_sim import contracts
from ccm_sim.cli import main
from ccm_sim.engine import build_quiet, run_world
from ccm_sim.messages import CABIN_TOPIC, WEARABLE_TOPIC
from ccm_sim.sinks import JsonlSink, MemorySink, Record, read_jsonl, record_to_line
from ccm_sim.timeutil import DEFAULT_START, parse_duration, parse_iso


def test_generate_two_hours_counts_and_order(tmp_path: Path) -> None:
    out = tmp_path / "q.jsonl"
    assert main(["generate", "--scenario", "quiet", "--duration", "2h", "--out", str(out)]) == 0
    records = read_jsonl(out)
    topics = Counter(r.topic for r in records)
    assert topics[WEARABLE_TOPIC] == 3 * 1440
    assert topics[CABIN_TOPIC] == 720
    per_crew = Counter(r.payload["crew"] for r in records if r.topic == WEARABLE_TOPIC)
    assert per_crew == {"W1": 1440, "W2": 1440, "W3": 1440}
    status = [r for r in records if "/status/" in r.topic]
    assert len(status) == 8  # online and offline for W1 W2 W3 and C1
    assert all(r.retain for r in status)
    telemetry = [r.payload["t_meas"] for r in records if "/telemetry" in r.topic]
    assert telemetry == sorted(telemetry)
    for r in records:
        kind = "node_status" if "/status/" in r.topic else None
        if kind is None:
            kind = "wearable_telemetry" if r.topic == WEARABLE_TOPIC else "cabin_telemetry"
        contracts.validate(kind, r.payload)


def test_jsonl_round_trip(tmp_path: Path) -> None:
    sink = MemorySink()
    run_world(build_quiet(["W1"], 3, DEFAULT_START, 600.0), sink)
    path = tmp_path / "rt.jsonl"
    file_sink = JsonlSink(path)
    for rec in sink.records:
        file_sink.publish(rec)
    file_sink.close()
    back = read_jsonl(path)
    assert [(r.topic, r.payload, r.retain) for r in back] == [
        (r.topic, r.payload, r.retain) for r in sink.records
    ]


def test_statuses_bracket_the_run() -> None:
    sink = MemorySink()
    run_world(build_quiet(["W1", "W2"], 1, DEFAULT_START, 120.0), sink)
    assert [r.payload["state"] for r in sink.records[:3]] == ["online"] * 3
    assert [r.payload["state"] for r in sink.records[-3:]] == ["offline"] * 3
    assert sink.records[0].qos == 1


def test_same_seed_gives_identical_output() -> None:
    a, b = MemorySink(), MemorySink()
    run_world(build_quiet(["W1", "W2"], 5, DEFAULT_START, 300.0), a)
    run_world(build_quiet(["W1", "W2"], 5, DEFAULT_START, 300.0), b)
    assert [record_to_line(r) for r in a.records] == [record_to_line(r) for r in b.records]


def test_adding_w3_leaves_w1_messages_identical() -> None:
    a, b = MemorySink(), MemorySink()
    run_world(build_quiet(["W1"], 5, DEFAULT_START, 600.0), a)
    run_world(build_quiet(["W1", "W3"], 5, DEFAULT_START, 600.0), b)

    def w1(records: list[Record]) -> list[str]:
        return [
            record_to_line(r)
            for r in records
            if r.topic == WEARABLE_TOPIC and r.payload["crew"] == "W1"
        ]

    assert w1(a.records) == w1(b.records)


def test_unknown_scenario_exits_with_message() -> None:
    with pytest.raises(SystemExit):
        main(["generate", "--scenario", "nope", "--out", "unused.jsonl"])


def test_time_helpers() -> None:
    assert parse_duration("2h") == 7200.0
    assert parse_duration("30m") == 1800.0
    assert parse_duration("7d") == 604800.0
    assert parse_duration("90") == 90.0
    with pytest.raises(ValueError):
        parse_duration("soon")
    assert parse_iso("2026-11-01T00:00:00Z") == DEFAULT_START
