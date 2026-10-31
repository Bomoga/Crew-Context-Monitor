"""Build a simulated world (nodes plus models) and run it into a sink."""

from __future__ import annotations

from dataclasses import dataclass

from ccm_sim.cabin import CabinModel, load_cabin_params
from ccm_sim.clock import SimClock
from ccm_sim.messages import CabinNode, WearableNode
from ccm_sim.physiology import CrewPhysiology, load_physiology
from ccm_sim.publisher import NodeSource, Publisher, Source
from ccm_sim.sinks import Sink


@dataclass
class World:
    """Everything a run needs: sources in publish order, start time and default duration."""

    sources: list[Source]
    t0: float
    duration: float
    name: str


def build_quiet(crew: list[str], seed: int, t0: float, duration: float) -> World:
    """The built-in ``quiet`` scenario: nothing happens (replaced by YAML scenarios in P3)."""
    cabin = CabinModel(load_cabin_params(), seed, t0)
    params = load_physiology()
    sources: list[Source] = []
    for crew_id in crew:
        phys = CrewPhysiology(crew_id, params.get(crew_id, params["W1"]), seed, t0, cabin.temp_fn)
        sources.append(NodeSource(WearableNode(phys, seed, t0)))
    sources.append(NodeSource(CabinNode(cabin, seed, t0)))
    return World(sources, t0, duration, "quiet")


def run_world(world: World, sink: Sink, speed: float | str = "max") -> int:
    """Publish the world's messages to ``sink``; return the number of telemetry records."""
    clock = SimClock(world.t0, speed)
    return Publisher(world.sources, sink, clock, world.t0).run(world.t0 + world.duration)
