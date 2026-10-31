"""Scenario files: load, validate against the JSON Schema, and parse durations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ccm_sim.timeutil import parse_duration

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"
ALIASES = {"quiet": "quiet_day"}
DURATION_KEYS = ("for", "over", "recovery_tau")


class ScenarioError(ValueError):
    """Raised when a scenario file is invalid."""


@dataclass(frozen=True)
class EffectSpec:
    """One effect as written in the file (targets may still contain a crew wildcard)."""

    op: str
    target: str | None
    args: dict[str, Any]


@dataclass(frozen=True)
class EventSpec:
    at: float
    name: str
    label: str
    end_label: str | None
    effects: list[EffectSpec]


@dataclass(frozen=True)
class MarkSpec:
    when: str
    name: str
    label: str


@dataclass
class Scenario:
    name: str
    title: str
    duration: float
    crew: list[str]
    events: list[EventSpec]
    marks: list[MarkSpec]
    expect: list[dict[str, Any]]
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def schema_validator() -> Draft202012Validator:
    schema = json.loads((SCENARIOS_DIR / "scenario.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _effect(raw: dict[str, Any]) -> EffectSpec:
    args = {k: v for k, v in raw.items() if k not in ("op", "target")}
    for key in DURATION_KEYS:
        if key in args:
            args[key] = parse_duration(args[key])
    if "start" in args and "lag" in args["start"]:
        args["start"] = {**args["start"], "lag": parse_duration(args["start"]["lag"])}
    op = raw["op"]
    if op != "silence" and not raw.get("target"):
        raise ScenarioError(f"effect {op!r} needs a target")
    needs = {
        "set": ("value",),
        "step": ("delta", "for"),
        "ramp": ("to", "over"),
        "drift_per_day": ("delta",),
        "coupled": ("driver", "start", "gain_at_peak"),
        "exercise": ("act", "for"),
        "rate": ("cpm", "for"),
        "silence": ("node", "for"),
    }[op]
    missing = [k for k in needs if k not in args]
    if missing:
        raise ScenarioError(f"effect {op!r} is missing {missing}")
    return EffectSpec(op, raw.get("target"), args)


def scenario_from_dict(raw: dict[str, Any]) -> Scenario:
    errors = sorted(schema_validator().iter_errors(raw), key=lambda e: list(e.absolute_path))
    if errors:
        where = "/".join(str(p) for p in errors[0].absolute_path) or "<root>"
        raise ScenarioError(f"scenario invalid at {where}: {errors[0].message}")
    events = [
        EventSpec(
            at=parse_duration(e["at"]),
            name=e["name"],
            label=e["label"],
            end_label=e.get("end_label"),
            effects=[_effect(x) for x in e["effects"]],
        )
        for e in raw.get("events", [])
    ]
    marks = [MarkSpec(m["when"], m["name"], m["label"]) for m in raw.get("marks", [])]
    return Scenario(
        name=raw["name"],
        title=raw["title"],
        duration=parse_duration(raw["duration"]),
        crew=list(raw["crew"]),
        events=events,
        marks=marks,
        expect=list(raw["expect"]),
        description=raw.get("description", ""),
        raw=raw,
    )


def scenario_path(name: str) -> Path:
    if name.endswith((".yaml", ".yml")) or "/" in name or "\\" in name:
        return Path(name)
    return SCENARIOS_DIR / f"{ALIASES.get(name, name)}.yaml"


def load_scenario(name: str) -> Scenario:
    path = scenario_path(name)
    if not path.exists():
        raise ScenarioError(f"unknown scenario {name!r} (looked for {path})")
    return scenario_from_dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_scenarios() -> list[str]:
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml") if p.stem != "demo")
