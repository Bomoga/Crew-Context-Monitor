"""Mock API state: a scenario running in this process, rolled up per minute.

The mock does not detect anything. Card levels, attribution and the correlation come from the
scenario's ``expect:`` entries (``ccm_sim.expectations``); the numbers come from the generated
data and the parameter baselines; the sentences come from ``templates``.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from ccm_sim.cabin import load_cabin_params
from ccm_sim.clock import SimClock
from ccm_sim.engine import World, build_world
from ccm_sim.expectations import (
    DOMAINS,
    RANK,
    DomainState,
    correlation_at,
    parse_cards,
    states_at,
)
from ccm_sim.mockapi import templates as tpl
from ccm_sim.mockapi.earth import EarthQueue
from ccm_sim.physiology import circadian_hr, load_physiology
from ccm_sim.playlist import Playlist, is_playlist, load_playlist
from ccm_sim.publisher import Publisher
from ccm_sim.scenario import load_scenario
from ccm_sim.sinks import Record
from ccm_sim.thresholds import Thresholds, load_thresholds
from ccm_sim.units import ppm_to_mmhg

LEARNING_S = 7200.0
MINUTE = 60.0
CARD_METRIC = {"cardio": "prv", "air": "co2_mmhg", "thermal": "temp_c", "radiation": "cpm"}
WORST_ORDER = ("radiation", "air", "thermal", "cardio")  # tie-break for the status bar

METRICS: dict[str, tuple[str, bool]] = {
    # metric: (unit, is_crew_metric)
    "hr": ("bpm", True),
    "hr_resid": ("bpm", True),
    "prv": ("ms", True),
    "spo2": ("%", True),
    "skin_c": ("C", True),
    "act": ("g", True),
    "co2_mmhg": ("mmHg", False),
    "temp_c": ("C", False),
    "rh": ("%", False),
    "voc": ("index", False),
    "pm25": ("ug/m3", False),
    "cpm": ("counts/min", False),
}
# half-width of the baseline band drawn in History (illustrative, not learned)
BAND = {
    "hr": 5.0,
    "hr_resid": 3.0,
    "prv": 8.0,
    "spo2": 1.5,
    "skin_c": 0.4,
    "act": 0.1,
    "co2_mmhg": 0.1,
    "temp_c": 0.5,
    "rh": 3.0,
    "voc": 15.0,
    "pm25": 3.0,
    "cpm": 7.0,
}


class StopRun(Exception):
    """Raised inside the sink to abort a background run."""


class Rollups:
    """Per-minute sum, count, min and max for each ``(metric, key)``."""

    def __init__(self, t0: float, duration: float) -> None:
        self.t0 = t0
        self.n = int(duration // MINUTE) + 3
        self._d: dict[tuple[str, str], np.ndarray] = {}

    def minute(self, t: float) -> int:
        return int((t - self.t0 - 1e-6) // MINUTE) if t > self.t0 else 0

    def add(self, metric: str, key: str, t: float, value: float) -> None:
        arr = self._d.get((metric, key))
        if arr is None:
            arr = np.zeros((4, self.n))
            arr[2, :] = np.inf
            arr[3, :] = -np.inf
            self._d[(metric, key)] = arr
        k = min(self.minute(t), self.n - 1)
        arr[0, k] += value
        arr[1, k] += 1
        arr[2, k] = min(arr[2, k], value)
        arr[3, k] = max(arr[3, k], value)

    def window(self, metric: str, key: str, t_lo: float, t_hi: float) -> tuple[float, int]:
        """``(sum, count)`` over the minutes covering ``(t_lo, t_hi]``."""
        arr = self._d.get((metric, key))
        if arr is None:
            return 0.0, 0
        lo, hi = self.minute(t_lo), self.minute(t_hi)
        lo = max(lo, 0)
        sl = slice(lo + (1 if t_lo > self.t0 else 0), hi + 1)
        return float(arr[0, sl].sum()), int(arr[1, sl].sum())

    def mean(self, metric: str, key: str, t_lo: float, t_hi: float) -> float | None:
        total, count = self.window(metric, key, t_lo, t_hi)
        return total / count if count else None

    def buckets(
        self, metric: str, key: str, t_lo: float, t_hi: float, step: float
    ) -> list[tuple[float, float, float, float]]:
        """``(t, mean, min, max)`` per ``step``-second bucket aligned to the start."""
        arr = self._d.get((metric, key))
        if arr is None:
            return []
        per = max(int(step // MINUTE), 1)
        first = max(self.minute(t_lo) // per * per, 0)
        out: list[tuple[float, float, float, float]] = []
        for start in range(first, min(self.minute(t_hi) + 1, self.n), per):
            cnt = arr[1, start : start + per].sum()
            if cnt:
                out.append(
                    (
                        self.t0 + start * MINUTE,
                        float(arr[0, start : start + per].sum() / cnt),
                        float(arr[2, start : start + per].min()),
                        float(arr[3, start : start + per].max()),
                    )
                )
        return out


@dataclass
class NodeInfo:
    node: str
    id: str
    state: str = "online"
    last_seen_t: float | None = None
    offline_since: float | None = None


class StoreSink:
    """A sink that feeds the mock state instead of a broker."""

    def __init__(self, state: MockState) -> None:
        self._state = state

    def open_node(
        self, key: str, will_topic: str | None, will_payload: dict[str, Any] | None
    ) -> None:
        return None

    def publish(self, record: Record) -> None:
        self._state.ingest(record)

    def drop_node(self, key: str, offline: Record) -> None:
        self._state.ingest(offline)

    def restore_node(self, key: str) -> None:
        return None

    def close(self) -> None:
        return None


class MockState:
    """A running scenario plus everything the endpoints read from it."""

    def __init__(
        self,
        scenario: str = "scrubber_failure",
        speed: float | str | None = 60.0,
        seed: int = 1,
        t0: float | None = None,
        crew: list[str] | None = None,
        learning: bool = False,
        fast_forward: float = 0.0,
        start_thread: bool = False,
    ) -> None:
        self.lock = threading.RLock()
        self.thresholds: Thresholds = load_thresholds()
        self._cabin_params = load_cabin_params()
        self._crew_params = load_physiology()
        self.checkins: list[dict[str, Any]] = []
        self._thread: threading.Thread | None = None
        self._stopping = False
        self.configure(scenario, speed, seed, t0, crew, learning, fast_forward)
        if start_thread:
            self.start()

    # -- lifecycle ----------------------------------------------------------------------------
    def configure(
        self,
        scenario: str,
        speed: float | str | None,
        seed: int = 1,
        t0: float | None = None,
        crew: list[str] | None = None,
        learning: bool = False,
        fast_forward: float = 0.0,
    ) -> None:
        """Start over on a scenario, or on a playlist such as ``demo`` whose steps run in turn."""
        self.stop()
        start = float(int(t0 if t0 is not None else time.time()))
        playlist = load_playlist(scenario) if is_playlist(scenario) else None
        first = playlist.steps[0].scenario if playlist else scenario
        world = build_world(load_scenario(first), seed, start, crew)  # may raise: build first
        total = (
            sum(load_scenario(s.scenario).duration for s in playlist.steps)
            if playlist
            else world.duration
        )
        with self.lock:
            self.scenario_name = scenario
            self.playlist: Playlist | None = playlist
            self._step = 0
            self._crew_arg = crew
            self.speed = speed if speed is not None else (60.0 if playlist is None else None)
            self.seed = seed
            self.learning = learning
            self.world: World = world
            self.worlds: list[World] = [world]
            self.t0 = world.t0
            self.t_end = self.t0 + total
            self._world_end = self.t0 + world.duration
            self.t_now = self.t0
            self.rollups = Rollups(self.t0, total)
            self.nodes: dict[str, NodeInfo] = {}
            self.sim_events: list[dict[str, Any]] = []
            self.node_events: list[dict[str, Any]] = []
            self.checkins = []
            self.baseline_start = {
                c: (self.t0 if learning else self.t0 - 86400.0) for c in self.world.crew
            }
            self._last_ibi: dict[str, int] = {}
            self.auto_approve = {"crew_only": True, "flight_surgeon": False, "urgent": False}
            self.settings_crew = [
                {"id": c, "name": c, "enrolled_t": self.t0 - 7 * 86400.0} for c in self.world.crew
            ]
            mean_hr = sum(self._crew_param(c, "hr0") for c in self.world.crew) / len(
                self.world.crew
            )
            self.queue = EarthQueue(
                self.t0,
                self.auto_approve,
                (
                    "Daily crew summary: all four domains normal; "
                    f"resting HR {mean_hr:.0f}, baseline {mean_hr:.0f}."
                ),
            )
            self._cabin_temp = self._cabin_params["temp_base"]
            self._publisher = Publisher(
                self.world.sources, StoreSink(self), SimClock(self.t0, "max"), self.t0
            )
            self._started = False
            self.finished = False
        if fast_forward > 0:
            self.advance_to(self.t0 + fast_forward)

    def _world_at(self, t: float) -> World:
        """The step's world that covers simulated time ``t`` (the first one before any step)."""
        current = self.worlds[0]
        for w in self.worlds:
            if w.t0 <= t:
                current = w
        return current

    def _next_world(self) -> bool:
        """Build and switch to the playlist's next step; False when there is none."""
        if self.playlist is None or self._step + 1 >= len(self.playlist.steps):
            return False
        self._step += 1
        step = self.playlist.steps[self._step]
        world = build_world(
            load_scenario(step.scenario),
            self.seed + self._step,
            self._world_end,
            self._crew_arg,
            seq_start=self.world.seq_state(),
        )
        self.sim_events.append(
            {
                "scenario": self.playlist.name,
                "name": f"demo_step_{self._step + 1}",
                "label": step.label,
                "phase": "mark",
                "t_meas": self._world_end,
                "crew": None,
            }
        )
        self.world = world
        self.worlds.append(world)
        self._world_end = world.t0 + world.duration
        self._publisher = Publisher(
            world.sources, StoreSink(self), SimClock(world.t0, "max"), world.t0
        )
        return True

    def _step_speed(self) -> float | str:
        if self.speed is not None:
            return self.speed
        assert self.playlist is not None
        return self.playlist.steps[self._step].speed

    def advance_to(self, t_sim: float) -> None:
        """Run the scenario synchronously, at once, up to simulated time ``t_sim``."""
        with self.lock:
            target = min(t_sim, self.t_end)
            while True:
                self._publisher.run(
                    min(target, self._world_end), finish=False, start=not self._started
                )
                self._started = True
                if target > self._world_end and self._next_world():
                    continue
                break
            self.t_now = max(self.t_now, target)
            self.finished = target >= self.t_end

    def start(self) -> None:
        """Run the rest of the scenario in a background thread at the configured speed."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopping = False

        def loop() -> None:
            try:
                while True:
                    self._publisher.clock = SimClock(self.t_now, self._step_speed())
                    self._publisher.run(self._world_end, finish=False, start=not self._started)
                    self._started = True
                    with self.lock:
                        self.t_now = max(self.t_now, self._world_end)
                        if not self._next_world():
                            self.finished = True
                            return
            except StopRun:
                return

        self._thread = threading.Thread(target=loop, name="mock-run", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        thread = getattr(self, "_thread", None)
        if thread is not None and thread.is_alive():
            self._stopping = True
            thread.join(timeout=5)
        self._thread = None
        self._stopping = False

    # -- ingest -------------------------------------------------------------------------------
    def ingest(self, record: Record) -> None:
        if self._stopping:
            raise StopRun
        with self.lock:
            topic, p = record.topic, record.payload
            if topic.endswith("wearable/telemetry"):
                self._ingest_wearable(p)
            elif topic.endswith("cabin/telemetry"):
                self._ingest_cabin(p)
            elif "/status/" in topic:
                self._ingest_status(p)
            elif topic.endswith("sim/event"):
                self.sim_events.append(dict(p))
                self.t_now = max(self.t_now, float(p["t_meas"]))

    def _ingest_wearable(self, p: dict[str, Any]) -> None:
        crew, t = p["crew"], float(p["t_meas"])
        r = self.rollups
        if p["hr"] is not None:
            r.add("hr", crew, t, p["hr"])
            params = self._crew_params.get(crew) or self._crew_params["W1"]
            predicted = (
                params["hr0"]
                + circadian_hr(params["hr_circ_amp"], t)
                + params["beta1"] * (p["act"] - params["act_ref"])
                + params["beta2"] * (self._cabin_temp - 22.0)
            )
            r.add("hr_resid", crew, t, p["hr"] - predicted)
        if p["spo2"] is not None:
            r.add("spo2", crew, t, p["spo2"])
        r.add("skin_c", crew, t, p["skin_c"])
        r.add("act", crew, t, p["act"])
        previous = self._last_ibi.get(crew)
        for rr in p["ibi"]:
            if previous is not None:
                d = rr - previous
                r.add("ssd", crew, t, d * d)
                r.add("nd", crew, t, 1.0)
            previous = rr
        if previous is not None:
            self._last_ibi[crew] = previous
        node = self.nodes.setdefault(p["id"], NodeInfo("wearable", p["id"]))
        node.last_seen_t = max(node.last_seen_t or t, t)
        self.t_now = max(self.t_now, t)

    def _ingest_cabin(self, p: dict[str, Any]) -> None:
        t, r = float(p["t_meas"]), self.rollups
        r.add("co2_mmhg", "cabin", t, ppm_to_mmhg(p["co2"], self.thresholds.cabin_pressure_mmhg))
        r.add("temp_c", "cabin", t, p["temp_c"])
        r.add("rh", "cabin", t, p["rh"])
        r.add("voc", "cabin", t, p["voc"])
        r.add("pm25", "cabin", t, p["pm25"])
        if "cpm" in p:
            r.add("cpm", "cabin", t, p["cpm"])
        self._cabin_temp = p["temp_c"]
        node = self.nodes.setdefault(p["id"], NodeInfo("cabin", p["id"]))
        node.last_seen_t = max(node.last_seen_t or t, t)
        self.t_now = max(self.t_now, t)

    def _ingest_status(self, p: dict[str, Any]) -> None:
        node = self.nodes.setdefault(p["id"], NodeInfo(p["node"], p["id"]))
        t = float(p["t"])
        if p["state"] == "offline" and node.state != "offline":
            node.offline_since = t
            self.node_events.append(
                {"t": t, "node": node.id, "sentence": tpl.node_event_sentence(node.id, "offline")}
            )
        elif p["state"] == "online" and node.state == "offline" and node.offline_since is not None:
            minutes = (t - node.offline_since) / 60.0
            self.node_events.append(
                {
                    "t": t,
                    "node": node.id,
                    "sentence": tpl.node_event_sentence(node.id, "online", minutes),
                }
            )
            node.offline_since = None
        node.state = p["state"]
        self.t_now = max(self.t_now, t)

    # -- measurements -------------------------------------------------------------------------
    def _crew_param(self, crew: str, name: str) -> float:
        return (self._crew_params.get(crew) or self._crew_params["W1"])[name]

    def _prv(self, crew: str, t: float) -> float | None:
        """Pulse-rate variability: RMSSD of the last five minutes of intervals."""
        ssd, _ = self.rollups.window("ssd", crew, t - 300.0, t)
        diffs, _ = self.rollups.window("nd", crew, t - 300.0, t)
        return math.sqrt(ssd / diffs) if diffs >= 30 else None

    def _crew_mean(
        self, metric: str, crews: tuple[str, ...], t: float, seconds: float
    ) -> float | None:
        vals = [self.rollups.mean(metric, c, t - seconds, t) for c in crews]
        got = [v for v in vals if v is not None]
        return sum(got) / len(got) if got else None

    def _facts(self, domain: str, st: DomainState, t: float) -> tpl.Facts:
        crews = tuple(self.world.crew)
        named = st.crew if st.level != "green" and st.crew else crews
        hr0 = sum(self._crew_param(c, "hr0") for c in named) / len(named)
        prv0 = sum(self._crew_param(c, "rmssd0") for c in named) / len(named)
        skin0 = sum(self._crew_param(c, "skin0") for c in crews) / len(crews)
        prvs = [v for v in (self._prv(c, t) for c in named) if v is not None]
        co2_0 = ppm_to_mmhg(self._cabin_params["co2_base"], self.thresholds.cabin_pressure_mmhg)
        co2 = self.rollups.mean("co2_mmhg", "cabin", t - 60.0, t)
        skin = self._crew_mean("skin_c", crews, t, 300.0)
        temp = self.rollups.mean("temp_c", "cabin", t - 60.0, t)
        cpm = self.rollups.mean("cpm", "cabin", t - 600.0, t)
        thr = self.thresholds
        hr = self._crew_mean("hr", named, t, 300.0)
        return tpl.Facts(
            domain=domain,
            level=st.level,
            attribution=st.attribution,
            crew=st.crew if st.level != "green" else (),
            all_crew=crews,
            reason_kind=st.reason,
            since_t=st.since,
            hr=hr if hr is not None else hr0,
            hr0=hr0,
            prv=sum(prvs) / len(prvs) if prvs else prv0,
            prv0=prv0,
            co2=co2 if co2 is not None else co2_0,
            co2_0=co2_0,
            temp=temp if temp is not None else self._cabin_params["temp_base"],
            skin_resid=(skin - skin0) if skin is not None else 0.0,
            cpm=cpm if cpm is not None else self._cabin_params["cpm_base"],
            cpm0=self._cabin_params["cpm_base"],
            co2_yellow=thr.co2_mmhg("yellow"),
            co2_red=thr.co2_mmhg("red"),
            temp_lo=thr.value("thermal.cabin_temp_c.lo"),
            temp_hi=thr.value("thermal.cabin_temp_c.hi"),
            radiation_windows=2 if st.level == "red" else (1 if st.level == "yellow" else 0),
        )

    def _numbers(self, f: tpl.Facts, t: float) -> list[dict[str, Any]]:
        def n(label: str, value: float | None, unit: str, base: float | None) -> dict[str, Any]:
            return {
                "label": label,
                "value": None if value is None else round(value, 1),
                "unit": unit,
                "baseline": None if base is None else round(base, 1),
            }

        crews = tuple(self.world.crew)
        if f.domain == "cardio":
            spo2 = self._crew_mean("spo2", f.crew or crews, t, 300.0)
            return [
                n("Resting HR", f.hr, "bpm", f.hr0),
                n("Pulse-rate variability", f.prv, "ms", f.prv0),
                n(
                    "SpO2",
                    spo2 if spo2 is not None else self._crew_param("W1", "spo2_0"),
                    "%",
                    self._crew_param("W1", "spo2_0"),
                ),
            ]
        if f.domain == "air":
            voc = self.rollups.mean("voc", "cabin", t - 300.0, t)
            return [
                n("CO2", f.co2, "mmHg", f.co2_0),
                n(
                    "VOC index",
                    voc if voc is not None else self._cabin_params["voc_base"],
                    "index",
                    self._cabin_params["voc_base"],
                ),
            ]
        if f.domain == "thermal":
            return [
                n("Cabin temperature", f.temp, "C", self._cabin_params["temp_base"]),
                n("Skin residual", f.skin_resid, "C", 0.0),
            ]
        return [n("Counts per minute", f.cpm, "counts/min", f.cpm0)]

    # -- status -------------------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        with self.lock:
            return self.status_at(self.t_now)

    def status_at(self, t: float) -> dict[str, Any]:
        crews = list(self.world.crew)
        learning = any(t < self.baseline_start[c] + LEARNING_S for c in crews)
        states = states_at(self._world_at(t), t)
        if learning:
            states = {d: DomainState("green", None, (), None) for d in DOMAINS}
        facts = {d: self._facts(d, states[d], t) for d in DOMAINS}
        cards = []
        for d in DOMAINS:
            f = facts[d]
            since = states[d].since
            name, det_state, detail = tpl.detector(f, (t - since) / 60.0 if since else 0.0)
            card: dict[str, Any] = {
                "domain": d,
                "level": f.level,
                "reason": tpl.card_reason(f),
                "action": tpl.card_action(f),
                "attribution": f.attribution,
                "crew": list(f.crew) if f.level != "green" else [],
                "numbers": self._numbers(f, t),
                "detector": {"name": name, "state": det_state, "detail": detail},
                "model": None,
            }
            if d == "cardio":
                p = self._crew_params["W1"]
                card["model"] = {
                    "beta0": round(f.hr0, 2),
                    "beta1": p["beta1"],
                    "beta2": p["beta2"],
                    "fitted_t": self.t0 - 3600.0,
                }
            if learning:
                for number in card["numbers"]:
                    number["baseline"] = None
            cards.append(card)
        worst_domain = max(DOMAINS, key=lambda d: (RANK[facts[d].level], -WORST_ORDER.index(d)))
        worst = facts[worst_domain]
        if learning:
            ends = max(
                self.baseline_start[c] + LEARNING_S
                for c in crews
                if t < self.baseline_start[c] + LEARNING_S
            )
            crew_status = {
                "level": "green",
                "domain": None,
                "sentence": tpl.learning_sentence(ends - t),
                "attribution": None,
                "action": None,
            }
        else:
            crew_status = {
                "level": worst.level,
                "domain": worst_domain if worst.level != "green" else None,
                "sentence": tpl.crew_status_sentence(worst, facts["cardio"], facts["cardio"]),
                "attribution": worst.attribution,
                "action": tpl.card_action(worst),
            }
        cardio = facts["cardio"]
        names = {e["id"]: e["name"] for e in self.settings_crew}
        crew_rows = []
        for c in crews:
            node = self.nodes.get(c)
            ends = self.baseline_start[c] + LEARNING_S
            crew_rows.append(
                {
                    "id": c,
                    "name": names.get(c, c),
                    "src": "sim",
                    "online": node.state == "online" if node else True,
                    "level": cardio.level if c in cardio.crew else "green",
                    "baseline": "learning" if t < ends else "ready",
                    "learning_ends_t": ends if t < ends else None,
                    "last_seen_t": node.last_seen_t if node else None,
                }
            )
        nodes = [
            {"node": n.node, "id": n.id, "state": n.state, "last_seen_t": n.last_seen_t}
            for n in sorted(self.nodes.values(), key=lambda n: (n.node != "wearable", n.id))
        ]
        return {
            "t": t,
            "source_mode": "mock",
            "thresholds_status": self.thresholds.status,
            "crew_status": crew_status,
            "crew": crew_rows,
            "cards": cards,
            "nodes": nodes,
            "correlation": None if learning else self._correlation(t, cardio),
            "checkin_due": not any(c["t"] > t - 86400.0 for c in self.checkins),
        }

    def _correlation(self, t: float, cardio: tpl.Facts) -> dict[str, Any] | None:
        world = self._world_at(t)
        wanted = correlation_at(world, t)
        if wanted is None:
            return None
        lags = [
            float(e.args["start"].get("lag", 0.0)) / 60.0
            for e in world.truth.effects
            if e.op == "coupled" and e.args["driver"] == "cabin.co2"
        ]
        lo, hi = wanted["lag_min"]
        lag = lags[0] if lags else (lo + hi) / 2.0
        crew = cardio.crew[0] if cardio.crew else self.world.crew[0]
        return {
            "x": wanted["x"],
            "y": wanted["y"],
            "crew": crew,
            "lag_min": lag,
            "r": self._pearson(crew, t, lag),
            "sentence": tpl.correlation_sentence(lag, self.thresholds.co2_mmhg("yellow")),
        }

    def _pearson(self, crew: str, t: float, lag_min: float) -> float:
        """Illustrative correlation of CO2 against pulse-rate variability, from the rollups."""
        lag, r = int(lag_min), self.rollups
        xs: list[float] = []
        ys: list[float] = []
        for k in range(max(0, r.minute(t) - 120), r.minute(t) - lag):
            x = r.mean("co2_mmhg", "cabin", self.t0 + k * MINUTE, self.t0 + (k + 1) * MINUTE)
            lo, hi = self.t0 + (k + lag - 4) * MINUTE, self.t0 + (k + lag + 1) * MINUTE
            ssd, _ = r.window("ssd", crew, lo, hi)
            diffs, _ = r.window("nd", crew, lo, hi)
            if x is not None and diffs >= 30:
                xs.append(x)
                ys.append(math.sqrt(ssd / diffs))
        if len(xs) < 10 or np.std(xs) == 0 or np.std(ys) == 0:
            return -0.5
        return round(float(max(-1.0, min(1.0, np.corrcoef(xs, ys)[0, 1]))), 2)

    # -- history ------------------------------------------------------------------------------
    def baseline_value(self, metric: str, crew: str | None) -> float:
        c = crew or "W1"
        table = {
            "hr": self._crew_param(c, "hr0"),
            "hr_resid": 0.0,
            "prv": self._crew_param(c, "rmssd0"),
            "spo2": self._crew_param(c, "spo2_0"),
            "skin_c": self._crew_param(c, "skin0"),
            "act": self._crew_param(c, "act_rest"),
            "co2_mmhg": ppm_to_mmhg(
                self._cabin_params["co2_base"], self.thresholds.cabin_pressure_mmhg
            ),
            "temp_c": self._cabin_params["temp_base"],
            "rh": self._cabin_params["rh_base"],
            "voc": self._cabin_params["voc_base"],
            "pm25": self._cabin_params["pm25_base"],
            "cpm": self._cabin_params["cpm_base"],
        }
        return table[metric]

    def _co2_baseline(self) -> float:
        co2_ppm = self._cabin_params["co2_base"]
        return ppm_to_mmhg(co2_ppm, self.thresholds.cabin_pressure_mmhg)

    def limits(self, metric: str) -> dict[str, float | None]:
        thr = self.thresholds
        if metric == "co2_mmhg":
            return {"yellow": thr.co2_mmhg("yellow"), "red": thr.co2_mmhg("red")}
        if metric == "temp_c":
            return {"yellow": None, "red": thr.value("thermal.cabin_temp_c.hi")}
        if metric == "cpm":
            window = thr.value("radiation.poisson.window_s")
            lam = self._cabin_params["cpm_base"] * window / 60.0
            line = (lam + thr.value("radiation.poisson.k_sigma") * math.sqrt(lam)) / (window / 60.0)
            return {"yellow": round(line, 1), "red": round(line, 1)}
        return {"yellow": None, "red": None}

    def history(self, metric: str, crew: str | None, hours: float, step: float) -> dict[str, Any]:
        unit, is_crew = METRICS[metric]
        with self.lock:
            key = (crew or self.world.crew[0]) if is_crew else "cabin"
            t_hi, t_lo = self.t_now, self.t_now - hours * 3600.0
            if metric == "prv":
                points = self._prv_buckets(key, t_lo, t_hi, step)
            else:
                points = self.rollups.buckets(metric, key, t_lo, t_hi, step)
            base = self.baseline_value(metric, key if is_crew else None)
            band = BAND[metric]
            baseline = [
                {
                    "t": t,
                    "mean": round(base, 3),
                    "lo": round(base - band, 3),
                    "hi": round(base + band, 3),
                }
                for t, *_ in points
            ]
            cusum = (
                self._cusum(metric, key, [p[0] for p in points])
                if metric in ("prv", "hr_resid")
                else None
            )
            return {
                "metric": metric,
                "unit": unit,
                "crew": key if is_crew else None,
                "points": [
                    {"t": t, "mean": round(m, 3), "min": round(lo, 3), "max": round(hi, 3)}
                    for t, m, lo, hi in points
                ],
                "baseline": baseline,
                "cusum": cusum,
                "limits": self.limits(metric),
            }

    def _prv_buckets(
        self, crew: str, t_lo: float, t_hi: float, step: float
    ) -> list[tuple[float, float, float, float]]:
        out = []
        t = self.t0 + max(0, int((t_lo - self.t0) // step)) * step
        while t <= t_hi:
            v = self._prv(crew, t + step)
            if v is not None and t >= self.t0:
                out.append((t, v, v, v))
            t += step
        return out

    def _cusum(self, metric: str, crew: str, times: list[float]) -> list[dict[str, float]]:
        """Illustrative CUSUM curve from the scenario's truth offsets (the mock detects nothing)."""
        sigma = 8.0 if metric == "prv" else 3.0
        target = f"crew.{crew}.rmssd" if metric == "prv" else f"crew.{crew}.hr"
        pos = neg = 0.0
        out: list[dict[str, float]] = []
        last = times[0] if times else 0.0
        for t in times:
            z = self._world_at(t).truth.offset(target, t) / sigma
            for _ in range(max(int((t - last) // 60.0), 1)):
                pos = max(0.0, pos + z - 0.25)
                neg = max(0.0, neg - z - 0.25)
            last = t
            out.append({"t": t, "pos": round(pos, 3), "neg": round(neg, 3), "h": 5.0})
        return out

    # -- events -------------------------------------------------------------------------------
    def events(self, since: float | None = None, limit: int = 200) -> dict[str, Any]:
        with self.lock:
            items: list[dict[str, Any]] = []
            for e in self.sim_events:
                domain, metric = _event_domain(e["name"])
                items.append(
                    _event(
                        e["t_meas"],
                        "sim_event",
                        domain,
                        metric,
                        e["crew"],
                        tpl.sim_event_sentence(e["label"]),
                        True,
                    )
                )
            for e in self.node_events:
                items.append(_event(e["t"], "node", None, None, None, e["sentence"], False))
            for c in self.checkins:
                items.append(
                    _event(
                        c["t"],
                        "checkin",
                        None,
                        None,
                        c["crew"],
                        tpl.checkin_sentence(c["crew"], c["mood"], c["sleep"]),
                        False,
                    )
                )
            cards = [c for w in self.worlds for c in parse_cards(w)]
            for card in cards:
                if card.level == "green" or card.t_from > self.t_now:
                    continue
                f = self._facts(
                    card.domain,
                    DomainState(card.level, card.attribution, card.crew, card.reason, card.t_from),
                    card.t_from,
                )
                metric = {
                    "cardio": "prv",
                    "air": "co2_mmhg",
                    "thermal": "temp_c",
                    "radiation": "cpm",
                }[card.domain]
                crew = card.crew[0] if card.domain == "cardio" and len(card.crew) == 1 else None
                kind = "drift" if card.domain == "cardio" else "spike"
                items.append(
                    _event(
                        card.t_from,
                        kind,
                        card.domain,
                        metric,
                        crew,
                        tpl.card_event_sentence(f),
                        False,
                    )
                )
            for w in self.worlds:
                if not any("correlation" in e for e in w.scenario.expect):
                    continue
                starts = [
                    c.t_from
                    for c in parse_cards(w)
                    if c.domain == "cardio" and c.attribution == "cabin" and c.level != "green"
                ]
                if not starts or min(starts) > self.t_now:
                    continue
                cardio = self.status_at(min(starts))["correlation"]
                if cardio is not None:
                    items.append(
                        _event(
                            min(starts),
                            "correlation",
                            "cardio",
                            "prv",
                            cardio["crew"],
                            cardio["sentence"],
                            False,
                        )
                    )
            items.sort(key=lambda e: e["t"])
            for i, e in enumerate(items, start=1):
                e["id"] = f"e-{i}"
            if since is not None:
                items = [e for e in items if e["t"] > since]
            return {"events": items[-limit:]}

    # -- Earth queue and settings -------------------------------------------------------------
    def sync_queue(self) -> None:
        """Queue a summary for every card that has turned red so far (once each)."""
        with self.lock:
            reds = [
                c
                for w in self.worlds
                for c in parse_cards(w)
                if c.level == "red" and c.t_from <= self.t_now
            ]
            for card in sorted(reds, key=lambda c: c.t_from):
                state = DomainState(
                    card.level, card.attribution, card.crew, card.reason, card.t_from
                )
                summary = tpl.card_reason(self._facts(card.domain, state, card.t_from))
                self.queue.queue_red(card.domain, card.t_from, summary, self.auto_approve)

    def earth_queue(self) -> dict[str, Any]:
        with self.lock:
            self.sync_queue()
            return self.queue.view(self.t_now)

    def approve_item(self, item_id: str) -> dict[str, Any] | None:
        with self.lock:
            self.sync_queue()
            return self.queue.approve(item_id, self.t_now)

    def settings(self) -> dict[str, Any]:
        with self.lock:
            return {
                "crew": [dict(c) for c in self.settings_crew],
                "auto_approve": dict(self.auto_approve),
            }

    def set_auto_approve(self, tiers: dict[str, bool]) -> dict[str, Any]:
        with self.lock:
            self.sync_queue()  # items already waiting keep the settings they arrived under
            self.auto_approve.update(tiers)
            return self.settings()

    def enroll(self, crew_id: str, name: str) -> dict[str, Any]:
        with self.lock:
            for entry in self.settings_crew:
                if entry["id"] == crew_id:
                    entry["name"] = name
                    return self.settings()
            self.settings_crew.append({"id": crew_id, "name": name, "enrolled_t": self.t_now})
            return self.settings()

    def reset_baseline(self, crew_id: str, metric: str | None) -> dict[str, Any]:
        """Restart the mock's learning timer for a crew member (any metric)."""
        with self.lock:
            if crew_id not in self.world.crew:
                raise KeyError(crew_id)
            self.baseline_start[crew_id] = self.t_now
            return self.settings()

    def add_checkin(self, body: dict[str, Any]) -> dict[str, Any]:
        """Record a check-in as context; it never changes a card level."""
        with self.lock:
            entry = {**body, "t": self.t_now}
            self.checkins.append(entry)
            events = self.events(limit=1_000_000)["events"]
            mine = [e for e in events if e["kind"] == "checkin" and e["t"] == entry["t"]]
            return {"ok": True, "event_id": mine[-1]["id"]}


def _event(
    t: float,
    kind: str,
    domain: str | None,
    metric: str | None,
    crew: str | None,
    sentence: str,
    simulated: bool,
) -> dict[str, Any]:
    return {
        "id": "",
        "t": t,
        "kind": kind,
        "domain": domain,
        "metric": metric,
        "crew": crew,
        "score": None,
        "sentence": sentence,
        "simulated": simulated,
    }


def _event_domain(name: str) -> tuple[str | None, str | None]:
    if name.startswith("co2") or "scrubber" in name:
        return "air", "co2_mmhg"
    if "temp" in name or "thermal" in name or "cooling" in name:
        return "thermal", "temp_c"
    if "solar" in name or "radiation" in name:
        return "radiation", "cpm"
    if any(w in name for w in ("illness", "exercise", "drift", "hr_trend")):
        return "cardio", "hr"
    return None, None
