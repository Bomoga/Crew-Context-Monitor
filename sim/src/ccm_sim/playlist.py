"""Playlists: scenarios run back to back as one unbroken run (the simulator-driven demo)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from ccm_sim.engine import World, build_world, run_world
from ccm_sim.messages import SIM_EVENT_TOPIC, sim_event_message
from ccm_sim.scenario import SCENARIOS_DIR, ScenarioError, load_scenario
from ccm_sim.sinks import Record, Sink


@dataclass(frozen=True)
class Step:
    scenario: str
    speed: float | str
    label: str


@dataclass(frozen=True)
class Playlist:
    name: str
    title: str
    steps: list[Step]


def load_playlist(name: str) -> Playlist:
    path = SCENARIOS_DIR / f"{name}.yaml"
    if not path.exists():
        raise ScenarioError(f"unknown playlist {name!r} (looked for {path})")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "steps" not in raw or not raw["steps"]:
        raise ScenarioError(f"{path.name} is not a playlist: it needs a non-empty 'steps' list")
    steps = []
    for s in raw["steps"]:
        speed = s.get("speed", 1)
        if speed != "max" and not (isinstance(speed, int | float) and speed > 0):
            raise ScenarioError(f"playlist step {s!r} has a bad speed")
        steps.append(Step(s["scenario"], speed, s["label"]))
    return Playlist(raw["name"], raw["title"], steps)


def run_playlist(
    playlist: Playlist,
    sink: Sink,
    seed: int,
    t0: float,
    crew: list[str] | None = None,
    speed: float | str | None = None,
) -> tuple[int, list[World]]:
    """Run every step into ``sink``, one after another; nodes stay online between steps.

    Each step starts where the previous one ended and its nodes continue the previous step's
    sequence numbers. Returns the record count and the worlds that were run.
    """
    worlds: list[World] = []
    seq: dict[str, int] = {}
    sent = 0
    t = t0
    last = len(playlist.steps) - 1
    for i, step in enumerate(playlist.steps):
        world = build_world(load_scenario(step.scenario), seed + i, t, crew, seq_start=seq)
        mark = sim_event_message(playlist.name, f"demo_step_{i + 1}", step.label, "mark", t, None)
        sink.publish(Record(SIM_EVENT_TOPIC, mark, qos=1, node="sim"))
        sent += run_world(
            world, sink, speed if speed is not None else step.speed, start=i == 0, finish=i == last
        )
        seq = world.seq_state()
        t += world.duration
        worlds.append(world)
    return sent, worlds
