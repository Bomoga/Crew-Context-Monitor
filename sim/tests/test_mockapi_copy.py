"""Copy rules: every sentence the mock can produce, for every state, obeys PLAN P6."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ccm_sim import contracts
from ccm_sim.mockapi import templates as tpl
from ccm_sim.mockapi.app import create_app
from ccm_sim.mockapi.copyrules import event_strings, queue_strings, status_strings, violations
from ccm_sim.mockapi.state import MockState
from ccm_sim.scenario import list_scenarios, load_scenario

T0 = 1_793_491_200.0


def test_the_checker_catches_each_kind_of_violation() -> None:
    assert violations("This was caused by the scrubber.")
    assert violations("Cabin CO2 is high, z-score 3.2.")
    assert violations("Heart rate z = -2.1 today.")
    assert violations("HRV is down 12 ms.")
    assert violations("Radiation 238 counts per minute.")
    assert violations("Pulse-rate variability is lower.", reason=True)  # no number
    assert not violations(
        "Consistent with a cabin cause: pulse-rate variability 31 ms, baseline 45."
    )
    assert not violations("Radiation proxy 238 counts per minute, baseline 18.", reason=True)


def test_every_template_obeys_the_rules() -> None:
    texts: list[tuple[str, bool]] = []
    for f in tpl.template_cases():
        texts.append((tpl.card_reason(f), True))
        action = tpl.card_action(f)
        if action:
            texts.append((action, False))
        texts.append((tpl.detector(f, 12.0)[2], False))
        texts.append((tpl.card_event_sentence(f), True))
        for worst in (f, replace(f, domain="air", level=f.level)):
            texts.append((tpl.crew_status_sentence(worst, f, f), True))
    texts += [
        (tpl.correlation_sentence(20, 2.5), True),
        (tpl.learning_sentence(3 * 3600 + 20 * 60), True),
        (tpl.sim_event_sentence("CO2 passes 2.5 mmHg"), False),
        (tpl.node_event_sentence("C1", "offline"), False),
        (tpl.node_event_sentence("C1", "online", 8), False),
        (tpl.checkin_sentence("W2", 4, 3), False),
    ]
    assert len(texts) > 50
    for text, is_reason in texts:
        assert violations(text, reason=is_reason) == [], text


def test_attribution_phrases_match_the_plan() -> None:
    base = tpl.Facts(domain="cardio", level="yellow", attribution="cabin", crew=("W1", "W2", "W3"))
    since = replace(base, since_t=1_793_500_200.0, co2=2.7, co2_0=0.6)
    assert "3 of 3 crew show lower pulse-rate variability since 02:30; cabin CO2 up 2.1 mmHg" in (
        tpl.card_reason(since)
    )
    solo = replace(base, attribution="individual", crew=("W2",), hr=71, hr0=65)
    assert tpl.card_reason(solo).startswith("Only W2 changed; cabin within normal.")
    assert "Resting HR 71, baseline 65" in tpl.card_reason(solo)
    assert tpl.card_reason(replace(base, attribution="unclear")).startswith(
        "Not enough data to attribute."
    )
    assert tpl.correlation_sentence(20, 2.5) == (
        "Pulse-rate variability began dropping 20 min after CO2 passed 2.5 mmHg."
    )


def test_radiation_is_always_a_proxy() -> None:
    for level in ("green", "yellow", "red"):
        f = tpl.Facts(domain="radiation", level=level, cpm=238, radiation_windows=2)
        assert "proxy" in tpl.card_reason(f)
    assert "(proxy)" in tpl.DOMAIN_NAMES["radiation"]


def _params() -> list[Any]:
    return [
        pytest.param(n, marks=pytest.mark.slow) if load_scenario(n).duration > 86400 else n
        for n in list_scenarios()
    ]


@pytest.mark.parametrize("name", _params())
def test_every_mock_response_for_every_scenario_state_obeys_the_rules(name: str) -> None:
    state = MockState(name, "max", t0=T0)
    client = TestClient(create_app(state))
    span = state.t_end - state.t0
    seen = 0
    for k in range(5):
        state.advance_to(state.t0 + 120.0 + (span - 120.0) * k / 4)
        for where, text, is_reason in [
            *status_strings(client.get("/api/status").json()),
            *event_strings(client.get("/api/events").json()),
            *queue_strings(client.get("/api/earth-queue").json()),
        ]:
            assert violations(text, reason=is_reason) == [], (name, where, text)
            seen += 1
    assert seen >= 80


def test_contract_fixtures_obey_the_rules() -> None:
    folder = contracts.contracts_dir() / "examples" / "api" / "valid"
    checked = 0
    for path in sorted(folder.glob("*.json")):
        kind = path.name.split(".", 1)[0]
        body = json.loads(path.read_text(encoding="utf-8"))
        if kind == "status":
            strings = list(status_strings(body))
        elif kind == "events":
            strings = list(event_strings(body))
        elif kind == "earth_queue":
            strings = list(queue_strings(body))
        else:
            continue
        for where, text, is_reason in strings:
            assert violations(text, reason=is_reason) == [], (path.name, where, text)
            checked += 1
    assert checked > 80
