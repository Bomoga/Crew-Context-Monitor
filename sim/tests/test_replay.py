from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ccm_sim import contracts
from ccm_sim.cli import main
from ccm_sim.clock import SimClock
from ccm_sim.engine import build_world, run_world
from ccm_sim.replay import (
    CSV_FIELDS,
    TIME_FIELDS,
    read_csv,
    read_rows,
    replay,
    retime_shift,
    write_csv,
)
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import MemorySink, Record
from ccm_sim.timeutil import DEFAULT_START

NOW = 2_000_000_000.0


def generated(name: str = "wifi_dropout", seed: int = 3) -> list[Record]:
    sink = MemorySink()
    run_world(build_world(load_scenario(name), seed, DEFAULT_START), sink)
    return sink.records


def key(record: Record) -> tuple[str, str, bool]:
    return (record.topic, json.dumps(record.payload, sort_keys=True), record.retain)


class FakeReal:
    def __init__(self) -> None:
        self.t = 100.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[Record]]:
    records = generated()
    path = tmp_path_factory.mktemp("rec") / "rec.csv"
    assert write_csv(path, records) == len(records)
    return path, records


def test_csv_format_one_row_per_message(recorded: tuple[Path, list[Record]]) -> None:
    path, records = recorded
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["topic", "t_meas", "retain", "payload_json"] == CSV_FIELDS
    assert len(rows) == len(records) + 1
    for row, record in zip(rows[1:], records, strict=True):
        assert row[0] == record.topic and row[2] == ("1" if record.retain else "0")
        assert json.loads(row[3]) == record.payload
        t = record.payload.get("t_meas", record.payload.get("t"))
        assert float(row[1]) == t


def test_round_trip_through_the_file_is_lossless(recorded: tuple[Path, list[Record]]) -> None:
    path, records = recorded
    assert [key(r) for r in read_csv(path)] == [key(r) for r in records]


def test_replay_without_retime_is_identical(recorded: tuple[Path, list[Record]]) -> None:
    path, records = recorded
    sink = MemorySink()
    assert replay(read_rows(path), sink, "max") == len(records)
    assert [key(r) for r in sink.records] == [key(r) for r in records]


def test_replay_with_retime_only_time_fields_differ_and_spacing_holds(
    recorded: tuple[Path, list[Record]],
) -> None:
    path, records = recorded
    sink = MemorySink()
    replay(read_rows(path), sink, "max", retime=True, now=NOW)
    assert len(sink.records) == len(records)
    shifts = set()
    for new, old in zip(sink.records, records, strict=True):
        assert new.topic == old.topic and new.retain == old.retain
        rest_new = {k: v for k, v in new.payload.items() if k not in TIME_FIELDS}
        rest_old = {k: v for k, v in old.payload.items() if k not in TIME_FIELDS}
        assert rest_new == rest_old
        for field in TIME_FIELDS:
            if field in old.payload:
                shifts.add(round(new.payload[field] - old.payload[field], 3))
    assert len(shifts) == 1  # one constant shift, so spacing is preserved
    last_old = max(r.payload.get("t_meas", r.payload.get("t")) for r in records)
    last_new = max(r.payload.get("t_meas", r.payload.get("t")) for r in sink.records)
    assert last_new == pytest.approx(NOW, abs=0.001)
    assert last_new - last_old == pytest.approx(shifts.pop(), abs=0.001)


def test_retime_lands_the_last_message_when_the_replay_finishes() -> None:
    assert retime_shift(1000.0, 4600.0, "max", NOW) == NOW - 4600.0
    assert retime_shift(1000.0, 4600.0, 60.0, NOW) == NOW + 60.0 - 4600.0
    assert retime_shift(1000.0, 4600.0, 1.0, NOW) == NOW + 3600.0 - 4600.0


def test_replayed_payloads_validate(recorded: tuple[Path, list[Record]]) -> None:
    path, _ = recorded
    sink = MemorySink()
    replay(read_rows(path), sink, "max", retime=True, now=NOW)
    for r in sink.records:
        kind = (
            "node_status"
            if "/status/" in r.topic
            else {
                "ccm/wearable/telemetry": "wearable_telemetry",
                "ccm/cabin/telemetry": "cabin_telemetry",
                "ccm/sim/event": "sim_event",
            }[r.topic]
        )
        contracts.validate(kind, r.payload)


def test_replay_paces_by_t_meas_and_does_not_wait_for_a_buffered_flush(
    recorded: tuple[Path, list[Record]],
) -> None:
    path, _ = recorded
    rows = read_rows(path)
    fake = FakeReal()
    clock = SimClock(rows[0][0], 60.0, real_now=fake.now, sleep=fake.sleep)
    replay(rows, MemorySink(), 60.0, clock=clock)
    span = max(t for t, _ in rows) - rows[0][0]
    assert sum(fake.sleeps) == pytest.approx(span / 60.0, rel=0.01)
    assert all(s >= 0 for s in fake.sleeps)


def test_replay_publishes_each_record_for_its_own_node(
    recorded: tuple[Path, list[Record]],
) -> None:
    path, _ = recorded
    sink = MemorySink()
    replay(read_rows(path), sink, "max")
    nodes = {r.node for r in sink.records}
    assert {"W1", "W2", "W3", "C1", "sim"} <= nodes


def test_cli_replay_prints_jsonl_and_rejects_a_bad_file(
    recorded: tuple[Path, list[Record]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, records = recorded
    assert main(["replay", "--file", str(path), "--speed", "max"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == len(records)
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected columns"):
        read_rows(bad)
