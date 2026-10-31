"""Build schema-valid wearable, cabin, status and simulator-event messages.

A node produces one message per period of simulated time: wearable every 5 s, cabin every 10 s.
``t_meas`` is the window end on the simulated clock; ``t_node`` adds a per-node offset (within 2 s)
and 30 ppm of drift, as a real node clock would.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ccm_sim.beats import BeatGenerator
from ccm_sim.cabin import CABIN_DT, CabinModel
from ccm_sim.physiology import CrewPhysiology
from ccm_sim.rng import stream

WEARABLE_PERIOD = 5.0
CABIN_PERIOD = CABIN_DT
DRIFT_PPM = 30.0
MAX_IBI = 20

WEARABLE_TOPIC = "ccm/wearable/telemetry"
CABIN_TOPIC = "ccm/cabin/telemetry"
SIM_EVENT_TOPIC = "ccm/sim/event"


def status_topic(node: str, node_id: str) -> str:
    return f"ccm/{node}/status/{node_id}"


def status_message(node: str, node_id: str, state: str, t: float) -> dict[str, Any]:
    return {"node": node, "id": node_id, "state": state, "t": round(t, 3)}


def sim_event_message(
    scenario: str, name: str, label: str, phase: str, t_meas: float, crew: str | None
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "name": name,
        "label": label,
        "phase": phase,
        "t_meas": round(t_meas, 3),
        "crew": crew,
    }


class _NodeClock:
    """Per-node t_node: fixed offset within 2 s plus 30 ppm drift from ``t0``."""

    def __init__(self, seed: int, name: str, t0: float) -> None:
        self._t0 = t0
        self._offset = float(stream(seed, f"clock.{name}").uniform(-1.9, 1.9))

    def t_node(self, t_meas: float) -> float:
        return round(t_meas + self._offset + DRIFT_PPM * 1e-6 * (t_meas - self._t0), 3)


class WearableNode:
    """One wearable: a crew member's physiology turned into 5 s telemetry messages."""

    def __init__(
        self,
        physiology: CrewPhysiology,
        seed: int,
        t0: float,
        src: str = "sim",
        node_id: str | None = None,
        finger_fn: Callable[[float], bool] | None = None,
    ) -> None:
        self.physiology = physiology
        self.crew = physiology.crew
        self.id = node_id or physiology.crew
        self.src = src
        self.t0 = t0
        self.seq = 0
        self._k = 0
        self._finger_fn = finger_fn or (lambda t: True)
        self._beats = BeatGenerator(
            stream(seed, f"crew.{self.crew}.ibi"), physiology.hr_fn, physiology.rmssd_fn, t0
        )
        self._clock = _NodeClock(seed, f"wearable.{self.id}", t0)
        self._last_hr = int(round(physiology.p["hr0"]))

    @property
    def next_t(self) -> float:
        """``t_meas`` of the next message."""
        return self.t0 + WEARABLE_PERIOD * (self._k + 1)

    def next_message(self) -> dict[str, Any]:
        t_meas = self.next_t
        self._k += 1
        self.seq += 1
        beats = self._beats.advance_to(t_meas)
        snap = self.physiology.advance_to(t_meas)
        msg: dict[str, Any] = {
            "node": "wearable",
            "id": self.id,
            "crew": self.crew,
            "src": self.src,
            "seq": self.seq,
            "t_node": self._clock.t_node(t_meas),
            "t_meas": round(t_meas, 3),
        }
        if self._finger_fn(t_meas):
            ibi = [rr for _, rr in beats][-MAX_IBI:]
            if ibi:
                self._last_hr = int(round(60000.0 / (sum(ibi) / len(ibi))))
            msg["hr"] = min(250, max(25, self._last_hr))
            msg["spo2"] = snap.spo2
            msg["ibi"] = ibi
        else:
            msg["hr"] = None
            msg["spo2"] = None
            msg["ibi"] = []
            msg["finger"] = False
        msg.update(
            skin_c=round(snap.skin_c, 2),
            act=round(snap.act, 3),
            motion=snap.motion,
            batt=round(snap.batt, 2),
        )
        return msg


class CabinNode:
    """The cabin sensor node: environment snapshots turned into 10 s telemetry messages."""

    def __init__(
        self,
        model: CabinModel,
        seed: int,
        t0: float,
        src: str = "sim",
        node_id: str = "C1",
        geiger: bool = True,
    ) -> None:
        self.model = model
        self.id = node_id
        self.src = src
        self.t0 = t0
        self.geiger = geiger
        self.seq = 0
        self._k = 0
        self._clock = _NodeClock(seed, f"cabin.{node_id}", t0)

    @property
    def next_t(self) -> float:
        return self.t0 + CABIN_PERIOD * (self._k + 1)

    def next_message(self) -> dict[str, Any]:
        t_meas = self.next_t
        self._k += 1
        self.seq += 1
        s = self.model.advance_to(t_meas)
        msg: dict[str, Any] = {
            "node": "cabin",
            "id": self.id,
            "src": self.src,
            "seq": self.seq,
            "t_node": self._clock.t_node(t_meas),
            "t_meas": round(t_meas, 3),
            "co2": s.co2,
            "temp_c": s.temp_c,
            "rh": s.rh,
            "voc": s.voc,
            "pm1": s.pm1,
            "pm25": s.pm25,
            "pm10": s.pm10,
        }
        if self.geiger:
            msg["cpm"] = s.cpm
            msg["c10s"] = s.c10s
        return msg
