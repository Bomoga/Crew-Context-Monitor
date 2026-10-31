"""Merge node streams by measured time and publish them to a sink, paced by the clock."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ccm_sim.clock import SimClock
from ccm_sim.messages import (
    CABIN_TOPIC,
    WEARABLE_TOPIC,
    CabinNode,
    WearableNode,
    status_message,
    status_topic,
)
from ccm_sim.sinks import Record, Sink


class Source(Protocol):
    """Anything that yields records in order of ``t_meas``."""

    @property
    def key(self) -> str: ...

    @property
    def node_type(self) -> str | None: ...

    @property
    def node_id(self) -> str | None: ...

    @property
    def next_t(self) -> float: ...

    def pop(self) -> list[Record]: ...


class NodeSource:
    """Adapts a wearable or cabin node to the ``Source`` protocol."""

    def __init__(self, node: WearableNode | CabinNode) -> None:
        self.node = node
        self.key = node.id
        self.node_id = node.id
        self.node_type = "wearable" if isinstance(node, WearableNode) else "cabin"
        self._topic = WEARABLE_TOPIC if isinstance(node, WearableNode) else CABIN_TOPIC

    @property
    def next_t(self) -> float:
        return self.node.next_t

    def pop(self) -> list[Record]:
        return [Record(self._topic, self.node.next_message(), node=self.key)]


class Publisher:
    """Publishes statuses, then every source's records in non-decreasing ``t_meas`` order."""

    def __init__(self, sources: Sequence[Source], sink: Sink, clock: SimClock, t0: float) -> None:
        self.sources = list(sources)
        self.sink = sink
        self.clock = clock
        self.t0 = t0

    def _status(self, source: Source, state: str, t: float) -> Record | None:
        if source.node_type is None or source.node_id is None:
            return None
        return Record(
            status_topic(source.node_type, source.node_id),
            status_message(source.node_type, source.node_id, state, t),
            retain=True,
            qos=1,
            node=source.key,
        )

    def start(self) -> None:
        for source in self.sources:
            offline = self._status(source, "offline", self.t0)
            self.sink.open_node(
                source.key, offline.topic if offline else None, offline.payload if offline else None
            )
        for source in self.sources:
            online = self._status(source, "online", self.t0)
            if online:
                self.sink.publish(online)

    def finish(self, t_end: float) -> None:
        for source in self.sources:
            offline = self._status(source, "offline", t_end)
            if offline:
                self.sink.publish(offline)

    def run(self, until: float) -> int:
        """Publish everything with ``t_meas <= until``; return the number of records sent."""
        sent = 0
        self.start()
        while self.sources:
            source = min(self.sources, key=lambda s: s.next_t)
            if source.next_t > until:
                break
            self.clock.sleep_until(source.next_t)
            for record in source.pop():
                self.sink.publish(record)
                sent += 1
        self.finish(until)
        return sent
