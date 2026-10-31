"""Scenario ``expect:`` blocks: what a correct pipeline should show, and a consistency check.

The expectations are the oracle for the Backend lane's evaluation and the source of card levels
for the mock API. This module parses them, resolves their times against the truth channels, and
checks that each one agrees with an independent oracle derived from the truth and the thresholds
(for example, an Air red window must lie where CO2 is at or above the red threshold).

Entry forms (PLAN Appendix B.3), with ``from`` and ``until`` optional:

- ``{card: air, level: red, from: <time>, until: <time>, attribution: cabin, crew: "*"}``
- ``{quiet: [cardio, air], from:, until:}``
- ``{correlation: {x: co2_mmhg, y: prv, lag_min: [15, 25]}}`` and ``{no_correlation: true}``
- ``{no_events: [spike]}``
- ``{node: C1, state: offline, from:, until:}`` and ``{coverage: {node: C1, step: 1m}}``

A time is a duration from the scenario start (``3h``), a mark reference with an optional offset
(``mark:co2_passes_yellow + 55m``), or a truth condition (``cabin.co2 >= air.co2.yellow``) that
is true from that moment on.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ccm_sim.timeutil import parse_duration

if TYPE_CHECKING:
    from ccm_sim.engine import World

DOMAINS = ("cardio", "air", "thermal", "radiation")
RANK = {"green": 0, "yellow": 1, "red": 2}
# Provisional detectability of a cardiovascular change (D24). Slow resting-HR drift of 6 bpm is
# deliberately below the HR line so that coincident_trends stays quiet.
CARDIO_RMSSD_MS = 8.0
CARDIO_HR_BPM = 10.0
SPIKE_STEP = 2.0  # largest allowed change of a crew HR or RMSSD offset over 5 minutes
GRID = 60.0
_DURATION = re.compile(r"^\s*\d+(?:\.\d+)?\s*[smhd]\s*$")
_MARK = re.compile(r"^\s*mark:([a-z0-9_]+)\s*(?:([+-])\s*(\S+))?\s*$")


class ExpectError(ValueError):
    """Raised when an expectation cannot be parsed or resolved."""


@dataclass(frozen=True)
class CardExpect:
    domain: str
    level: str
    t_from: float
    t_until: float
    attribution: str | None
    crew: tuple[str, ...]
    crew_explicit: bool
    reason: str | None


def resolve_time(expr: Any, world: World, default: float) -> float:
    """Resolve a ``from``/``until`` value to an absolute time."""
    if expr is None:
        return default
    if isinstance(expr, int | float):
        return world.t0 + float(expr)
    text = str(expr)
    if _DURATION.match(text):
        return world.t0 + parse_duration(text)
    mark = _MARK.match(text)
    if mark:
        name, sign, offset = mark.groups()
        events = {e.name: e.t for e in world.events}
        if name not in events:
            raise ExpectError(f"mark {name!r} is not in the scenario timeline")
        shift = parse_duration(offset) if offset else 0.0
        return events[name] + (shift if sign != "-" else -shift)
    found = world.truth.first_time(text)
    if found is None:
        raise ExpectError(f"condition {text!r} is never true in the scenario")
    return found


def _crew(entry: dict[str, Any], world: World) -> tuple[tuple[str, ...], bool]:
    spec = entry.get("crew", "*")
    if spec == "*":
        return tuple(world.crew), False
    ids = [spec] if isinstance(spec, str) else list(spec)
    return tuple(c for c in ids if c in world.crew), True


def parse_cards(world: World) -> list[CardExpect]:
    out: list[CardExpect] = []
    end = world.t0 + world.duration
    for entry in world.scenario.expect:
        if "card" not in entry:
            continue
        domain, level = entry["card"], entry.get("level")
        if domain not in DOMAINS or level not in RANK:
            raise ExpectError(f"bad card expectation {entry!r}")
        crew, explicit = _crew(entry, world)
        out.append(
            CardExpect(
                domain,
                level,
                resolve_time(entry.get("from"), world, world.t0),
                resolve_time(entry.get("until"), world, end),
                entry.get("attribution"),
                crew,
                explicit,
                entry.get("reason"),
            )
        )
    return out


# -- state at a time (used by the mock API) --------------------------------------------------


@dataclass(frozen=True)
class DomainState:
    level: str
    attribution: str | None
    crew: tuple[str, ...]
    reason: str | None
    since: float | None = None


def states_at(world: World, t: float) -> dict[str, DomainState]:
    """Per-domain expected state at time ``t``: the highest active card expectation, else green."""
    states = {d: DomainState("green", None, (), None) for d in DOMAINS}
    for c in parse_cards(world):
        if c.t_from <= t < c.t_until and RANK[c.level] >= RANK[states[c.domain].level]:
            states[c.domain] = DomainState(c.level, c.attribution, c.crew, c.reason, c.t_from)
    return states


def correlation_at(world: World, t: float) -> dict[str, Any] | None:
    """The expected correlation entry, active once a cabin-attributed cardio window has begun."""
    wanted = next((e["correlation"] for e in world.scenario.expect if "correlation" in e), None)
    if wanted is None:
        return None
    starts = [
        c.t_from
        for c in parse_cards(world)
        if c.domain == "cardio" and c.attribution == "cabin" and c.level != "green"
    ]
    return dict(wanted) if starts and t >= min(starts) else None


# -- oracle levels from the truth channels ---------------------------------------------------


def air_level(world: World, t: float) -> str:
    if world.truth.condition_holds("cabin.co2 >= air.co2.red", t):
        return "red"
    if world.truth.condition_holds("cabin.co2 >= air.co2.yellow", t):
        return "yellow"
    return "green"


def thermal_level(world: World, t: float) -> str:
    truth, thr = world.truth, world.truth.thresholds
    temp = truth.level("cabin.temp", t)
    if temp >= thr.value("thermal.cabin_temp_c.hi") or temp < thr.value("thermal.cabin_temp_c.lo"):
        return "red"
    # a steady skin residual of the yellow size needs this much cabin change (skin gain 0.25)
    skin_gain = 0.25
    swing = abs(temp - truth.baselines.base("cabin.temp"))
    return "yellow" if swing >= thr.value("thermal.skin_residual_c.yellow") / skin_gain else "green"


def _radiation_limit_cpm(world: World) -> tuple[float, float]:
    thr = world.truth.thresholds
    window = thr.value("radiation.poisson.window_s")
    lam = world.truth.baselines.base("cabin.cpm") * window / 60.0
    return (lam + thr.value("radiation.poisson.k_sigma") * math.sqrt(lam)) / (window / 60.0), window


def radiation_level(world: World, t: float) -> str:
    """Windowed Poisson oracle: yellow after one complete exceeding window, red after two."""
    limit, window = _radiation_limit_cpm(world)
    thr = world.truth.thresholds
    k = math.floor((t - world.t0) / window) - 1  # last complete tumbling window

    def exceeds(idx: int) -> bool:
        if idx < 0:
            return False
        start = world.t0 + idx * window
        samples = [world.truth.level("cabin.cpm", start + s) for s in range(0, int(window), 60)]
        return sum(samples) / len(samples) > limit

    streak = 0
    for idx in range(k, k - int(thr.value("radiation.poisson.red_windows")), -1):
        if not exceeds(idx):
            break
        streak += 1
    if streak >= thr.value("radiation.poisson.red_windows"):
        return "red"
    return "yellow" if streak >= thr.value("radiation.poisson.yellow_windows") else "green"


def cardio_level(world: World, crew: str, t: float) -> str:
    d_hr = world.truth.offset(f"crew.{crew}.hr", t)
    d_rm = world.truth.offset(f"crew.{crew}.rmssd", t)
    if abs(d_rm) >= CARDIO_RMSSD_MS or abs(d_hr) >= CARDIO_HR_BPM:
        return "yellow"
    return "green"


def _grid(world: World, t_from: float, t_until: float) -> list[float]:
    n = int((t_until - t_from) // GRID)
    return [t_from + k * GRID for k in range(max(n, 0))]


def _cardio_attribution(world: World, crew: tuple[str, ...]) -> str | None:
    coupled = {e.target for e in world.truth.effects if e.op == "coupled"}
    direct = {
        e.target
        for e in world.truth.effects
        if e.op != "coupled"
        and e.target.split(".")[-1] in ("hr", "rmssd")
        and e.target.startswith("crew.")
    }
    names = [f"crew.{c}.{f}" for c in crew for f in ("hr", "rmssd")]
    if any(n in coupled for n in names) and not any(n in direct for n in names):
        return "cabin"
    if any(n in direct for n in names) and not any(n in coupled for n in names):
        return "individual"
    return None


# -- checkpoints for the end-to-end tests ------------------------------------------------------

SIX_HOURS = 6 * 3600.0


def checkpoints(world: World, max_points: int = 6) -> list[dict[str, Any]]:
    """Times at which a dashboard should show particular states, with the expected states.

    Each entry has the offset in seconds from the scenario start, the expected level, attribution
    and crew of each card, whether a correlation is expected, the labels of the simulated events
    published so far, and the nodes that are offline.
    """
    end = world.t0 + world.duration
    candidates = {180.0}
    for c in parse_cards(world):
        for edge in (c.t_from, c.t_until):
            if world.t0 < edge < end:
                candidates.add(edge - world.t0 + 180.0)
    for s in world.truth.silences:
        candidates.add((s.t_start + s.t_end) / 2.0 - world.t0)
        candidates.add(s.t_end - world.t0 + 120.0)
    candidates.add(world.duration - 120.0)
    usable = sorted(t for t in candidates if 120.0 <= t <= world.duration - 60.0)
    picked: list[float] = []
    for t in usable:  # drop points within five minutes of the one before
        if not picked or t - picked[-1] >= 300.0:
            picked.append(t)
    while len(picked) > max_points:  # thin evenly but keep the first and the last
        del picked[len(picked) // 2]
    out: list[dict[str, Any]] = []
    for offset in picked:
        t = world.t0 + offset
        states = states_at(world, t)
        out.append(
            {
                "offset": offset,
                "cards": {
                    d: {
                        "level": states[d].level,
                        "attribution": states[d].attribution,
                        "crew": list(states[d].crew),
                    }
                    for d in DOMAINS
                },
                "correlation": correlation_at(world, t) is not None,
                "sim_events": [e.label for e in world.events if e.t <= t and e.t >= t - SIX_HOURS],
                "offline": sorted(s.node for s in world.truth.silences if s.t_start <= t < s.t_end),
            }
        )
    return out


# -- the consistency check ---------------------------------------------------------------------


def _check_card(world: World, c: CardExpect, problems: list[str]) -> None:
    label = f"card {c.domain} {c.level}"
    if not c.t_from < c.t_until:
        problems.append(f"{label}: from is not before until")
        return
    times = _grid(world, c.t_from, c.t_until)
    for t in times:
        if c.domain == "cardio":
            wrong = [
                crew
                for crew in world.crew
                if cardio_level(world, crew, t) != (c.level if crew in c.crew else "green")
            ]
            if wrong:
                problems.append(
                    f"{label}: at +{(t - world.t0) / 60:.0f} min the truth gives {wrong} a "
                    "different cardio level"
                )
                return
        else:
            oracle = {"air": air_level, "thermal": thermal_level, "radiation": radiation_level}[
                c.domain
            ](world, t)
            if oracle != c.level:
                problems.append(
                    f"{label}: at +{(t - world.t0) / 60:.0f} min the truth gives {oracle}"
                )
                return
    if c.domain == "cardio" and c.attribution and c.level != "green":
        derived = _cardio_attribution(world, c.crew)
        if derived != c.attribution:
            problems.append(f"{label}: attribution {c.attribution!r}, effects imply {derived!r}")


def _check_quiet(world: World, entry: dict[str, Any], problems: list[str]) -> None:
    end = world.t0 + world.duration
    t_from = resolve_time(entry.get("from"), world, world.t0)
    t_until = resolve_time(entry.get("until"), world, end)
    for domain in entry["quiet"]:
        for t in _grid(world, t_from, t_until):
            if domain == "cardio":
                levels = {cardio_level(world, c, t) for c in world.crew}
            else:
                levels = {
                    {"air": air_level, "thermal": thermal_level, "radiation": radiation_level}[
                        domain
                    ](world, t)
                }
            if levels != {"green"}:
                problems.append(
                    f"quiet {domain}: truth is not green at +{(t - world.t0) / 60:.0f} min"
                )
                break


def _check_node(world: World, entry: dict[str, Any], problems: list[str]) -> None:
    silences = [s for s in world.truth.silences if s.node == entry["node"]]
    end = world.t0 + world.duration
    if not silences:
        problems.append(f"node {entry['node']}: expected a silence, the scenario has none")
        return
    s = silences[0]
    if entry["state"] == "offline":
        ok = (
            resolve_time(entry.get("from"), world, world.t0) == s.t_start
            and resolve_time(entry.get("until"), world, end) == s.t_end
        )
    else:
        ok = resolve_time(entry.get("from"), world, world.t0) == s.t_end
    if not ok:
        problems.append(f"node {entry['node']} {entry['state']}: window does not match the silence")


def check_expectations(world: World) -> list[str]:
    """Return a list of problems (empty when every expectation is consistent)."""
    problems: list[str] = []
    expect = world.scenario.expect
    if not expect:
        return ["scenario has no expect block"]
    try:
        for c in parse_cards(world):
            _check_card(world, c, problems)
        for entry in expect:
            if "quiet" in entry:
                _check_quiet(world, entry, problems)
            elif "correlation" in entry:
                lo, hi = entry["correlation"]["lag_min"]
                lags = [
                    float(e.args["start"].get("lag", 0.0)) / 60.0
                    for e in world.truth.effects
                    if e.op == "coupled" and e.args["driver"] == "cabin.co2"
                ]
                if not any(lo <= lag <= hi for lag in lags):
                    problems.append(f"correlation: no coupled effect has a lag in [{lo}, {hi}] min")
            elif entry.get("no_correlation"):
                if any(e.op == "coupled" for e in world.truth.effects):
                    problems.append("no_correlation: the scenario has a coupled effect")
            elif "no_events" in entry:
                for target in {
                    e.target for e in world.truth.effects if e.target.startswith("crew.")
                }:
                    series = world.truth.offset_series(target, step=300.0)
                    if len(series) > 1 and abs(series[1:] - series[:-1]).max() > SPIKE_STEP:
                        problems.append(
                            f"no_events: {target} jumps by more than {SPIKE_STEP} in 5 min"
                        )
            elif "node" in entry:
                _check_node(world, entry, problems)
            elif "coverage" in entry:
                silences = [s for s in world.truth.silences if s.node == entry["coverage"]["node"]]
                if not silences or not all(s.buffer for s in silences):
                    problems.append("coverage: needs a buffered silence on that node")
            elif not ({"card", "no_correlation"} & set(entry)):
                problems.append(f"unknown expectation {entry!r}")
    except (ExpectError, KeyError) as exc:
        problems.append(str(exc))
    return problems
