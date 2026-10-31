"""Where simulated messages go: memory, a JSONL file, or an MQTT broker."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


@dataclass(frozen=True)
class Record:
    """One message to publish."""

    topic: str
    payload: dict[str, Any]
    retain: bool = False
    qos: int = 0
    node: str | None = None
    action: str | None = None  # "drop" or "restore": a node connection event


class Sink(Protocol):
    def open_node(
        self, key: str, will_topic: str | None, will_payload: dict[str, Any] | None
    ) -> None: ...

    def publish(self, record: Record) -> None: ...

    def drop_node(self, key: str, offline: Record) -> None: ...

    def restore_node(self, key: str) -> None: ...

    def close(self) -> None: ...


@dataclass
class MemorySink:
    records: list[Record] = field(default_factory=list)

    def open_node(
        self, key: str, will_topic: str | None, will_payload: dict[str, Any] | None
    ) -> None:
        return None

    def publish(self, record: Record) -> None:
        self.records.append(record)

    def drop_node(self, key: str, offline: Record) -> None:
        """Without a broker there is no last will, so the offline status is written directly."""
        self.records.append(offline)

    def restore_node(self, key: str) -> None:
        return None

    def close(self) -> None:
        return None


def record_to_line(record: Record) -> str:
    return json.dumps(
        {"topic": record.topic, "payload": record.payload, "retain": record.retain},
        separators=(",", ":"),
    )


class JsonlSink:
    """One ``{"topic":..., "payload":..., "retain":...}`` per line; ``-`` writes to stdout."""

    def __init__(self, path: str | Path) -> None:
        self._own = str(path) != "-"
        self._fh: TextIO
        if self._own:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(path, "w", encoding="utf-8", newline="\n")  # noqa: SIM115
        else:
            self._fh = sys.stdout

    def open_node(
        self, key: str, will_topic: str | None, will_payload: dict[str, Any] | None
    ) -> None:
        return None

    def publish(self, record: Record) -> None:
        self._fh.write(record_to_line(record) + "\n")

    def drop_node(self, key: str, offline: Record) -> None:
        self.publish(offline)

    def restore_node(self, key: str) -> None:
        return None

    def close(self) -> None:
        if self._own:
            self._fh.close()
        else:
            self._fh.flush()


def read_jsonl(path: str | Path) -> list[Record]:
    out: list[Record] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line)
            out.append(Record(obj["topic"], obj["payload"], bool(obj.get("retain", False))))
    return out


class MqttSink:
    """Publishes through one paho client per node, each with its own last will (D10)."""

    def __init__(self, host: str, port: int, client_prefix: str = "ccm-sim") -> None:
        self._host = host
        self._port = port
        self._prefix = client_prefix
        self._clients: dict[str, mqtt.Client] = {}
        self._last: dict[str, mqtt.MQTTMessageInfo] = {}
        self._wills: dict[str, tuple[str | None, dict[str, Any] | None]] = {}

    def open_node(
        self, key: str, will_topic: str | None, will_payload: dict[str, Any] | None
    ) -> None:
        if key in self._clients:
            return
        self._wills[key] = (will_topic, will_payload)
        client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"{self._prefix}-{key}")
        if will_topic is not None and will_payload is not None:
            client.will_set(will_topic, json.dumps(will_payload), qos=1, retain=True)
        client.connect(self._host, self._port, keepalive=30)
        client.loop_start()
        self._clients[key] = client

    def client(self, key: str) -> mqtt.Client:
        return self._clients[key]

    def publish(self, record: Record) -> None:
        key = record.node or "sim"
        if key not in self._clients:
            self.open_node(key, None, None)
        self._last[key] = self._clients[key].publish(
            record.topic, json.dumps(record.payload), qos=record.qos, retain=record.retain
        )

    def kill_node(self, key: str) -> None:
        """Drop a node's connection without DISCONNECT so the broker fires its last will."""
        client = self._clients.pop(key)
        self._last.pop(key, None)
        sock = client.socket()
        client.loop_stop()
        if sock is not None:
            sock.close()

    def drop_node(self, key: str, offline: Record) -> None:
        """Cut the connection without DISCONNECT; the broker publishes the last will."""
        self.kill_node(key)
        time.sleep(0.2)  # let the broker fire the will before this node reconnects

    def restore_node(self, key: str) -> None:
        will_topic, will_payload = self._wills.get(key, (None, None))
        self.open_node(key, will_topic, will_payload)

    def close(self) -> None:
        for info in self._last.values():
            info.wait_for_publish(timeout=10)
        for client in self._clients.values():
            client.disconnect()
            client.loop_stop()
        self._clients.clear()
        self._last.clear()
