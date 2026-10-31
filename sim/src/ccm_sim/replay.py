"""Record and replay: the CSV format of ``contracts/replay_csv.md`` and the replay publisher."""

from __future__ import annotations

import csv
import json
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TextIO

from ccm_sim.clock import SimClock
from ccm_sim.messages import status_message, status_topic
from ccm_sim.sinks import Record, Sink

CSV_FIELDS = ["topic", "t_meas", "retain", "payload_json"]
TIME_FIELDS = ("t_meas", "t_node", "t")


def qos_for(topic: str) -> int:
    return 0 if topic.endswith("/telemetry") else 1


def row_time(payload: dict[str, Any], received: float) -> float:
    """The ordering time of a message: ``t_meas``, else status ``t``, else when it arrived."""
    for key in ("t_meas", "t"):
        if isinstance(payload.get(key), int | float):
            return float(payload[key])
    return received


class CsvWriter:
    """Appends rows to a replay CSV; safe to call from the MQTT network thread."""

    def __init__(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = open(path, "w", encoding="utf-8", newline="")  # noqa: SIM115
        self._writer = csv.writer(self._fh, lineterminator="\n")
        self._writer.writerow(CSV_FIELDS)
        self._lock = threading.Lock()
        self.rows = 0

    def add(self, record: Record, received: float | None = None) -> None:
        t = row_time(record.payload, received if received is not None else time.time())
        line = [
            record.topic,
            repr(t),
            "1" if record.retain else "0",
            json.dumps(record.payload, separators=(",", ":")),
        ]
        with self._lock:
            self._writer.writerow(line)
            self._fh.flush()
            self.rows += 1

    def close(self) -> None:
        with self._lock:
            self._fh.close()


def write_csv(path: str | Path, records: Iterable[Record]) -> int:
    writer = CsvWriter(path)
    try:
        for record in records:
            writer.add(record)
    finally:
        writer.close()
    return writer.rows


def read_rows(path: str | Path) -> list[tuple[float, Record]]:
    """Read ``(t_meas, record)`` pairs in file order."""
    rows: list[tuple[float, Record]] = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != CSV_FIELDS:
            raise ValueError(f"{path}: expected columns {CSV_FIELDS}, got {reader.fieldnames}")
        for row in reader:
            topic = row["topic"]
            record = Record(
                topic,
                json.loads(row["payload_json"]),
                retain=row["retain"] == "1",
                qos=qos_for(topic),
            )
            rows.append((float(row["t_meas"]), record))
    return rows


def read_csv(path: str | Path) -> list[Record]:
    return [record for _, record in read_rows(path)]


def retime_shift(first_t: float, last_t: float, speed: float | str, now: float) -> float:
    """The constant that makes the last message land when the replay finishes (D25)."""
    span = last_t - first_t
    run_length = 0.0 if speed == "max" else span / float(speed)
    return now + run_length - last_t


def shifted(record: Record, shift: float) -> Record:
    payload = dict(record.payload)
    for key in TIME_FIELDS:
        if isinstance(payload.get(key), int | float):
            payload[key] = round(payload[key] + shift, 3)
    return Record(record.topic, payload, record.retain, record.qos, record.node)


def node_key(record: Record) -> str:
    if record.topic == "ccm/sim/event":
        return "sim"
    return str(record.payload.get("id", "sim"))


def replay(
    rows: Sequence[tuple[float, Record]],
    sink: Sink,
    speed: float | str = 1.0,
    retime: bool = False,
    now: float | None = None,
    clock: SimClock | None = None,
) -> int:
    """Publish recorded rows in file order, paced by their ``t_meas``; return the row count."""
    if not rows:
        return 0
    first_t, last_t = rows[0][0], max(t for t, _ in rows)
    when = time.time() if now is None else now
    shift = retime_shift(first_t, last_t, speed, when) if retime else 0.0
    clock = clock or SimClock(first_t, speed)
    for _, record in rows:
        if "/status/" in record.topic:
            node, node_id = record.payload["node"], record.payload["id"]
            sink.open_node(
                node_id,
                status_topic(node, node_id),
                status_message(node, node_id, "offline", record.payload["t"] + shift),
            )
    for t, record in rows:
        clock.sleep_until(t)
        out = shifted(record, shift) if retime else record
        sink.publish(Record(out.topic, out.payload, out.retain, out.qos, node_key(out)))
    return len(rows)


class MqttRecorder:
    """Subscribes to ``ccm/#`` and writes every message to a replay CSV."""

    def __init__(self, host: str, port: int, writer: CsvWriter) -> None:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion

        self._writer = writer
        self._client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="ccm-sim-recorder")
        self._client.on_message = self._on_message
        self._client.connect(host, port)
        self._client.subscribe("ccm/#", qos=1)
        self._client.loop_start()

    def _on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            return
        if isinstance(payload, dict):
            record = Record(msg.topic, payload, bool(msg.retain), int(msg.qos))
            self._writer.add(record, time.time())

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()
        self._writer.close()
