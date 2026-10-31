"""Build a simulated world from a scenario and run it into a sink."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ccm_sim.cabin import CabinModel, load_cabin_params
from ccm_sim.clock import SimClock
from ccm_sim.effects import Baselines
from ccm_sim.messages import (
    SIM_EVENT_TOPIC,
    CabinNode,
    WearableNode,
    sim_event_message,
)
from ccm_sim.physiology import CrewPhysiology, load_physiology
from ccm_sim.publisher import NodeSource, Publisher, SilencedSource, Source
from ccm_sim.scenario import EffectSpec, EventSpec, Scenario, load_scenario
from ccm_sim.sinks import Record, Sink
from ccm_sim.thresholds import Thresholds, load_thresholds
from ccm_sim.truth import Truth

_PLACEHOLDER = re.compile(r"\{([a-z0-9_.]+)\}")


@dataclass(frozen=True)
class SimEvent:
    """A scenario event, end or mark placed on the timeline."""

    t: float
    scenario: str
    name: str
    label: str
    phase: str  # start | end | mark
    crew: str | None


class EventSource:
    """Publishes the timeline on ``ccm/sim/event``."""

    key = "sim"
    node_type = None
    node_id = None

    def __init__(self, events: list[SimEvent]) -> None:
        self._events = sorted(events, key=lambda e: e.t)
        self._i = 0

    @property
    def next_t(self) -> float:
        return self._events[self._i].t if self._i < len(self._events) else float("inf")

    def pop(self) -> list[Record]:
        e = self._events[self._i]
        self._i += 1
        return [
            Record(
                SIM_EVENT_TOPIC,
                sim_event_message(e.scenario, e.name, e.label, e.phase, e.t, e.crew),
                qos=1,
                node=self.key,
            )
        ]


@dataclass
class World:
    """Everything a run needs: sources in publish order, timing, truth and the event timeline."""

    sources: list[Source]
    t0: float
    duration: float
    name: str
    scenario: Scenario
    truth: Truth
    crew: list[str]
    seed: int
    events: list[SimEvent] = field(default_factory=list)
    missing_marks: list[str] = field(default_factory=list)


def _fmt(value: float) -> str:
    return f"{value:.1f}" if abs(value - round(value, 1)) < 1e-9 else f"{value:g}"


def _fill(label: str, thresholds: Thresholds) -> str:
    return _PLACEHOLDER.sub(lambda m: _fmt(thresholds.value(m.group(1))), label)


def _effect_target(spec: EffectSpec) -> str:
    """The target of an effect; a silence on a wearable counts as a crew target."""
    if spec.target:
        return spec.target
    node = str(spec.args.get("node", ""))
    return f"crew.{node}.link" if node.startswith("W") else ""


def _event_crew(event: EventSpec) -> str | None:
    targets = [_effect_target(s) for s in event.effects]
    crews = {t.split(".")[1] for t in targets if t.startswith("crew.")}
    others = any(not t.startswith("crew.") for t in targets)
    if len(crews) == 1 and not others and "*" not in crews:
        return next(iter(crews))
    return None


def _end_label(event: EventSpec) -> str:
    if event.end_label:
        return event.end_label
    return (
        re.sub(r"\bbegins\b", "ends", event.label)
        if "begins" in event.label
        else f"{event.label} ends"
    )


def build_timeline(
    scenario: Scenario, truth: Truth, thresholds: Thresholds, t_end: float
) -> tuple[list[SimEvent], list[str]]:
    events: list[SimEvent] = []
    missing: list[str] = []
    for ev in scenario.events:
        t_start = truth.t0 + ev.at
        crew = _event_crew(ev)
        events.append(
            SimEvent(t_start, scenario.name, ev.name, _fill(ev.label, thresholds), "start", crew)
        )
        bounded = all("for" in s.args for s in ev.effects)
        if bounded or ev.end_label:
            lengths = [s.args["for"] for s in ev.effects if "for" in s.args]
            t_stop = t_start + max(lengths) if lengths else t_end
            events.append(
                SimEvent(
                    t_stop,
                    scenario.name,
                    f"{ev.name}_end",
                    _fill(_end_label(ev), thresholds),
                    "end",
                    crew,
                )
            )
    for mark in scenario.marks:
        t_mark = truth.first_time(mark.when)
        if t_mark is None:
            missing.append(mark.name)
            continue
        events.append(
            SimEvent(t_mark, scenario.name, mark.name, _fill(mark.label, thresholds), "mark", None)
        )
    return [e for e in events if e.t <= t_end], missing


def _silenced(source: NodeSource, truth: Truth) -> Source:
    silences = [s for s in truth.silences if s.node == source.key]
    return SilencedSource(source, silences) if silences else source


def build_world(
    scenario: Scenario,
    seed: int,
    t0: float,
    crew: list[str] | None = None,
    duration: float | None = None,
    thresholds: Thresholds | None = None,
) -> World:
    thresholds = thresholds or load_thresholds()
    crew = crew or list(scenario.crew)
    duration = scenario.duration if duration is None else duration
    cabin_params = load_cabin_params()
    crew_params = load_physiology()
    for cid in crew:
        crew_params.setdefault(cid, dict(crew_params["W1"]))
    truth = Truth(scenario, crew, t0, duration, thresholds, Baselines(cabin_params, crew_params))
    for effect in truth.effects:
        if effect.op == "exercise" and "recovery_tau" in effect.args:
            crew_params[effect.target.split(".")[1]]["tau_act_recover_s"] = float(
                effect.args["recovery_tau"]
            )

    def cabin_offsets(target: str, t: float) -> float:
        return truth.offset(f"cabin.{target}", t)

    cabin = CabinModel(cabin_params, seed, t0, cabin_offsets)
    sources: list[Source] = []
    events, missing = build_timeline(scenario, truth, thresholds, t0 + duration)
    sources.append(EventSource(events))
    for cid in crew:

        def crew_offsets(target: str, t: float, _prefix: str = f"crew.{cid}.") -> float:
            return truth.offset(_prefix + target, t)

        phys = CrewPhysiology(cid, crew_params[cid], seed, t0, cabin.temp_fn, crew_offsets)
        sources.append(_silenced(NodeSource(WearableNode(phys, seed, t0)), truth))
    sources.append(_silenced(NodeSource(CabinNode(cabin, seed, t0)), truth))
    return World(sources, t0, duration, scenario.name, scenario, truth, crew, seed, events, missing)


def build_quiet(crew: list[str], seed: int, t0: float, duration: float) -> World:
    """The ``quiet`` scenario (an alias of ``quiet_day``) with an explicit duration."""
    return build_world(load_scenario("quiet"), seed, t0, crew, duration)


def run_world(world: World, sink: Sink, speed: float | str = "max") -> int:
    """Publish the world's messages to ``sink``; return the number of records sent."""
    clock = SimClock(world.t0, speed)
    return Publisher(world.sources, sink, clock, world.t0).run(world.t0 + world.duration)
