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
from ccm_sim.truth import Silence


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

    def run(self, until: float, finish: bool = True, start: bool = True) -> int:
        """Publish everything with ``t_meas <= until``; return the number of records sent.

        With ``finish=False`` the offline statuses are left unsent (tests kill nodes instead);
        with ``start=False`` the nodes are assumed to be open already (later playlist steps).
        """
        sent = 0
        if start:
            self.start()
        while self.sources:
            source = min(self.sources, key=lambda s: s.next_t)
            if source.next_t > until:
                break
            self.clock.sleep_until(source.next_t)
            for record in source.pop():
                if record.action == "drop" and record.node:
                    self.sink.drop_node(record.node, record)
                    continue
                if record.action == "restore" and record.node:
                    self.sink.restore_node(record.node)
                self.sink.publish(record)
                sent += 1
        if finish:
            self.finish(until)
        return sent


class SilencedSource:
    """Wraps a node source with silences: the node drops off, buffers, then flushes in order.

    At a silence start the node's connection is dropped (the broker fires the last will; sinks
    without a broker get an ``offline`` status record). At its end the node reconnects, publishes
    ``online`` and flushes the messages it measured meanwhile with their original ``seq`` and
    ``t_meas`` (``buffer: false`` discards them instead, leaving a ``seq`` gap).
    """

    def __init__(self, base: NodeSource, silences: Sequence[Silence]) -> None:
        self._base = base
        self._silences = sorted(silences, key=lambda s: s.t_start)
        self._i = 0
        self._silent = False

    @property
    def key(self) -> str:
        return self._base.key

    @property
    def node_type(self) -> str | None:
        return self._base.node_type

    @property
    def node_id(self) -> str | None:
        return self._base.node_id

    @property
    def next_t(self) -> float:
        if self._silent:
            return self._silences[self._i].t_end
        if self._i < len(self._silences):
            return min(self._base.next_t, self._silences[self._i].t_start)
        return self._base.next_t

    def _status(self, state: str, t: float, action: str | None) -> Record:
        assert self._base.node_type is not None and self._base.node_id is not None
        return Record(
            status_topic(self._base.node_type, self._base.node_id),
            status_message(self._base.node_type, self._base.node_id, state, t),
            retain=True,
            qos=1,
            node=self._base.key,
            action=action,
        )

    def pop(self) -> list[Record]:
        if self._silent:
            silence = self._silences[self._i]
            out = [self._status("online", silence.t_end, "restore")]
            while self._base.next_t < silence.t_end:
                messages = self._base.pop()
                if silence.buffer:
                    out.extend(messages)
            self._silent = False
            self._i += 1
            return out
        if self._i < len(self._silences) and self._base.next_t >= self._silences[self._i].t_start:
            self._silent = True
            return [self._status("offline", self._silences[self._i].t_start, "drop")]
        return self._base.pop()
