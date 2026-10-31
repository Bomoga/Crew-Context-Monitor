"""Plain-language sentences for the mock API.

Copy rules (PLAN P6), enforced by tests: one plain sentence per reason with a number and a
baseline comparison; no raw z-scores; heart-rate variability is always written "pulse-rate
variability"; radiation is always a "proxy"; "consistent with", never "caused by".
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime

DOMAIN_NAMES = {
    "cardio": "Cardiovascular",
    "air": "Air quality",
    "thermal": "Thermal",
    "radiation": "Radiation (proxy)",
}


@dataclass(frozen=True)
class Facts:
    """Everything a sentence may mention about one domain at one moment."""

    domain: str
    level: str  # green | yellow | red
    attribution: str | None = None  # cabin | individual | unclear | None
    crew: tuple[str, ...] = ()  # crew the card names
    all_crew: tuple[str, ...] = ("W1", "W2", "W3")
    reason_kind: str | None = None  # "drift" for slow cardio drift
    since_t: float | None = None  # when the current state began (unix seconds)
    hr: float = 62.0
    hr0: float = 62.0
    prv: float = 45.0
    prv0: float = 45.0
    co2: float = 0.6  # mmHg
    co2_0: float = 0.6
    temp: float = 22.0  # C
    skin_resid: float = 0.0  # C from baseline
    cpm: float = 18.0
    cpm0: float = 18.0
    co2_yellow: float = 2.5
    co2_red: float = 3.0
    temp_lo: float = 18.0
    temp_hi: float = 27.0
    radiation_windows: int = 0  # complete exceeding windows in a row


def clock(t: float) -> str:
    """Time of day, UTC, as HH:MM."""
    return datetime.fromtimestamp(t, UTC).strftime("%H:%M")


def names(crew: tuple[str, ...]) -> str:
    if len(crew) <= 1:
        return crew[0] if crew else "no one"
    return ", ".join(crew[:-1]) + " and " + crew[-1]


def _up(text: str) -> str:
    """Upper-case the first letter only (``str.capitalize`` would lower-case ``HR``)."""
    return text[:1].upper() + text[1:]


def _cardio_numbers(f: Facts) -> str:
    return (
        f"resting HR {f.hr:.0f}, baseline {f.hr0:.0f}; "
        f"pulse-rate variability {f.prv:.0f} ms, baseline {f.prv0:.0f} ms"
    )


def card_reason(f: Facts) -> str:
    """The one sentence a card shows."""
    if f.domain == "cardio":
        if f.level == "green":
            return f"Resting HR {f.hr:.0f}, baseline {f.hr0:.0f}; " + (
                f"pulse-rate variability {f.prv:.0f} ms, baseline {f.prv0:.0f} ms."
            )
        since = f" since {clock(f.since_t)}" if f.since_t else ""
        if f.attribution == "cabin":
            up = max(f.co2 - f.co2_0, 0.0)
            return (
                f"{len(f.crew)} of {len(f.all_crew)} crew show lower pulse-rate variability"
                f"{since}; cabin CO2 up {up:.1f} mmHg."
            )
        if f.attribution == "individual":
            if f.reason_kind == "drift":
                return (
                    f"Only {names(f.crew)} changed{since}, a slow drift; cabin within normal. "
                    + _up(_cardio_numbers(f))
                    + "."
                )
            return (
                f"Only {names(f.crew)} changed; cabin within normal. "
                + _up(_cardio_numbers(f))
                + "."
            )
        return "Not enough data to attribute. " + _up(_cardio_numbers(f)) + "."
    if f.domain == "air":
        base = f"Cabin CO2 {f.co2:.1f} mmHg, baseline {f.co2_0:.1f} mmHg"
        if f.level == "yellow":
            return f"{base}; above the {f.co2_yellow:.1f} mmHg yellow line."
        if f.level == "red":
            return f"{base}; above the {f.co2_red:.1f} mmHg red line."
        return base + "."
    if f.domain == "thermal":
        band = f"normal band {f.temp_lo:.0f} to {f.temp_hi:.0f} C"
        base = f"Cabin {f.temp:.1f} C, {band}; skin {f.skin_resid:+.1f} C from baseline"
        return base + "."
    base = f"Radiation proxy {f.cpm:.0f} counts per minute, baseline {f.cpm0:.0f}"
    if f.level == "yellow":
        return f"{base}; above the expected range for 1 window."
    if f.level == "red":
        return (
            f"{base}; above the expected range for {max(f.radiation_windows, 2)} windows in a row."
        )
    return base + "."


def card_action(f: Facts) -> str | None:
    if f.level == "green":
        return None
    if f.domain == "air":
        if f.level == "red":
            return "Check scrubber, increase ventilation, retest in 30 min"
        return "Check scrubber and increase ventilation"
    if f.domain == "thermal":
        return (
            "Check cooling loop and reduce workload" if f.level == "red" else "Check cooling loop"
        )
    if f.domain == "radiation":
        if f.level == "red":
            return "Move to the shielded area and log exposure time"
        return "Note exposure time and watch for updates"
    if f.attribution == "cabin":
        return "Check the cabin air first, then recheck in 30 min"
    if f.attribution == "individual":
        return f"Check in with {names(f.crew)}; recheck sleep and hydration"
    return "Retest in 30 min"


def detector(f: Facts, minutes_active: float) -> tuple[str, str, str]:
    """``(name, state, detail)`` for the card's detector line."""
    minutes = max(int(minutes_active), 0)
    if f.domain == "cardio":
        detail = "no drift" if f.level == "green" else f"alarm {minutes} min ago"
        return ("residual cusum", f.level, detail)
    if f.domain == "air":
        if f.level == "green":
            return ("threshold", "green", "within normal")
        line = f.co2_red if f.level == "red" else f.co2_yellow
        return ("threshold", f.level, f"above {line:.1f} mmHg for {minutes} min")
    if f.domain == "thermal":
        if f.level == "green":
            return ("threshold", "green", "within normal")
        return ("threshold", f.level, f"outside the comfortable range for {minutes} min")
    windows = (
        0 if f.level == "green" else (1 if f.level == "yellow" else max(f.radiation_windows, 2))
    )
    return ("poisson window", f.level, f"{windows} of 2 windows above threshold")


def learning_sentence(seconds_left: float) -> str:
    minutes = max(int(round(seconds_left / 60.0)), 0)
    hours, rest = divmod(minutes, 60)
    return f"Learning each crew member's baseline; alerts start in {hours} h {rest} min."


def crew_status_sentence(worst: Facts, cardio: Facts, normal: Facts) -> str:
    """The status bar sentence for the worst card."""
    if worst.level == "green":
        return (
            f"All four domains are normal; resting HR {normal.hr:.0f}, baseline {normal.hr0:.0f}."
        )
    if worst.domain == "cardio":
        return card_reason(worst)
    head = card_reason(worst).rstrip(".").split(";")[0]
    if cardio.level != "green" and cardio.attribution == "cabin":
        return (
            f"{head}; {len(cardio.crew)} of {len(cardio.all_crew)} crew show lower "
            "pulse-rate variability; consistent with a cabin cause."
        )
    return card_reason(worst)


def correlation_sentence(lag_min: float, yellow_mmhg: float) -> str:
    return (
        f"Pulse-rate variability began dropping {lag_min:.0f} min after CO2 passed "
        f"{yellow_mmhg:.1f} mmHg."
    )


def sim_event_sentence(label: str) -> str:
    return f"Simulated: {label}"


def node_event_sentence(node_id: str, state: str, minutes: float | None = None) -> str:
    if state == "offline":
        return f"{node_id} went offline."
    after = f" after {max(int(round(minutes)), 1)} min" if minutes is not None else ""
    return f"{node_id} back online{after}."


def checkin_sentence(crew: str, mood: int, sleep: int) -> str:
    return f"Check-in from {crew}: mood {mood} of 5, sleep {sleep} of 5."


def card_event_sentence(f: Facts) -> str:
    return card_reason(f)


def template_cases() -> Iterator[Facts]:
    """Every domain x level x attribution combination, for the copy-rule tests."""
    base = Facts(domain="cardio", level="green")
    for domain in DOMAIN_NAMES:
        yield replace(base, domain=domain, level="green")
        for level in ("yellow", "red"):
            if domain == "cardio":
                for attribution in ("cabin", "individual", "unclear"):
                    for kind in (None, "drift"):
                        yield replace(
                            base,
                            domain=domain,
                            level=level,
                            attribution=attribution,
                            crew=("W2",) if attribution == "individual" else ("W1", "W2", "W3"),
                            reason_kind=kind,
                            since_t=1_793_500_000.0,
                            hr=71,
                            prv=31,
                            co2=3.1,
                        )
            else:
                yield replace(
                    base,
                    domain=domain,
                    level=level,
                    attribution="cabin",
                    crew=("W1", "W2", "W3"),
                    co2=3.1,
                    temp=28.4,
                    skin_resid=1.2,
                    cpm=238,
                    radiation_windows=2,
                )
