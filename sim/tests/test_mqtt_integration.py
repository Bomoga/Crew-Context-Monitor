"""Broker integration: 10 sim minutes at max speed, retained online, last will on a killed node."""

from __future__ import annotations

import json
import threading
import time
from collections import Counter

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from ccm_sim.clock import SimClock
from ccm_sim.engine import build_quiet
from ccm_sim.publisher import Publisher
from ccm_sim.sinks import MqttSink
from ccm_sim.timeutil import DEFAULT_START

CREW = ["W1", "W2", "W3"]
DURATION = 600.0


class Collector:
    """Subscribes to a topic filter and records ``(topic, payload, retain)``."""

    def __init__(self, host: str, port: int, topic_filter: str, name: str) -> None:
        self.items: list[tuple[str, dict[str, object], bool]] = []
        self._lock = threading.Lock()
        self._client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=name)
        self._client.on_message = self._on_message
        self._client.connect(host, port)
        self._client.subscribe(topic_filter, qos=1)
        self._client.loop_start()

    def _on_message(self, _c: mqtt.Client, _u: object, msg: mqtt.MQTTMessage) -> None:
        with self._lock:
            self.items.append((msg.topic, json.loads(msg.payload), bool(msg.retain)))

    def snapshot(self) -> list[tuple[str, dict[str, object], bool]]:
        with self._lock:
            return list(self.items)

    def wait_for(self, predicate: object, timeout: float = 15.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate(self.snapshot()):  # type: ignore[operator]
                return True
            time.sleep(0.05)
        return False

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()


def test_ten_sim_minutes_through_a_real_broker(broker: tuple[str, int]) -> None:
    host, port = broker
    everything = Collector(host, port, "ccm/#", "test-all")
    time.sleep(0.3)
    world = build_quiet(CREW, 21, DEFAULT_START, DURATION)
    sink = MqttSink(host, port)
    pub = Publisher(world.sources, sink, SimClock(world.t0, "max"), world.t0)
    pub.run(world.t0 + DURATION, finish=False)

    wearable, cabin = 3 * int(DURATION / 5), int(DURATION / 10)
    assert everything.wait_for(
        lambda items: (
            Counter(t for t, _, _ in items)["ccm/wearable/telemetry"] >= wearable
            and Counter(t for t, _, _ in items)["ccm/cabin/telemetry"] >= cabin
        )
    ), Counter(t for t, _, _ in everything.snapshot())
    counts = Counter(t for t, _, _ in everything.snapshot())
    assert counts["ccm/wearable/telemetry"] == wearable
    assert counts["ccm/cabin/telemetry"] == cabin

    late = Collector(host, port, "ccm/+/status/+", "test-late")
    expected = {f"ccm/wearable/status/{c}" for c in CREW} | {"ccm/cabin/status/C1"}
    assert late.wait_for(lambda items: {t for t, _, _ in items} >= expected)
    retained = {t: p for t, p, r in late.snapshot() if r}
    assert set(retained) == expected
    assert all(p["state"] == "online" for p in retained.values())

    sink.kill_node("W2")
    assert late.wait_for(
        lambda items: any(
            t == "ccm/wearable/status/W2" and p["state"] == "offline" for t, p, _ in items
        )
    ), late.snapshot()

    late.stop()
    everything.stop()
    sink.close()
