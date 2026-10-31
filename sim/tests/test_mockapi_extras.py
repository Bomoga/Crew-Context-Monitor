"""Earth queue, settings and check-in on the mock API."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ccm_sim import contracts
from ccm_sim.mockapi.app import create_app
from ccm_sim.mockapi.state import LEARNING_S, MockState

T0 = 1_793_491_200.0


def make(scenario: str = "scrubber_failure") -> tuple[MockState, TestClient]:
    state = MockState(scenario, "max", t0=T0)
    return state, TestClient(create_app(state))


def queue(client: TestClient) -> dict[str, Any]:
    body: dict[str, Any] = client.get("/api/earth-queue").json()
    contracts.validate("earth_queue", body)
    return body


def test_queue_is_seeded_with_one_item_per_tier_and_validates() -> None:
    _, client = make()
    body = queue(client)
    assert [i["tier"] for i in body["items"]] == ["crew_only", "flight_surgeon", "urgent"]
    assert body["next_window_t"] == T0 + 1800
    assert [i["approved"] for i in body["items"]] == [True, False, False]  # crew_only auto-approves
    for item in body["items"]:
        assert item["bytes"] == len(json.dumps(item["payload"], separators=(",", ":")).encode())


def test_approving_twice_is_idempotent_and_sends_at_the_next_window() -> None:
    state, client = make()
    first = client.post("/api/earth-queue/q-2/approve")
    assert first.status_code == 200
    contracts.validate("earth_queue_item", first.json())
    assert first.json()["approved"] and not first.json()["sent"]
    again = client.post("/api/earth-queue/q-2/approve")
    assert again.json() == first.json()
    assert [i["approved"] for i in queue(client)["items"]] == [True, True, False]
    state.advance_to(T0 + 1801)
    sent = {i["id"]: i["sent"] for i in queue(client)["items"]}
    assert sent == {"q-1": True, "q-2": True, "q-3": False}
    assert client.post("/api/earth-queue/q-99/approve").status_code == 404


def test_a_summary_is_queued_each_time_a_card_turns_red() -> None:
    state, client = make()
    state.advance_to(T0 + 4 * 3600)
    items = queue(client)["items"]
    generated = items[3:]
    assert len(generated) == 1  # only the Air card turns red in this scenario
    red = generated[0]
    assert red["tier"] == "flight_surgeon" and red["payload"]["domain"] == "air"
    assert "CO2" in red["summary"] and red["payload"]["level"] == "red"
    assert not red["approved"] and red["bytes"] < 400
    assert queue(client)["items"] == items  # asking again adds nothing
    state2, client2 = make("solar_particle_event")
    state2.advance_to(T0 + 3 * 3600)
    assert queue(client2)["items"][3]["tier"] == "urgent"


def test_auto_approve_applies_to_new_items_of_that_tier() -> None:
    state, client = make()
    r = client.put(
        "/api/settings", json={"crew_only": True, "flight_surgeon": True, "urgent": False}
    )
    assert r.status_code == 200 and r.json()["auto_approve"]["flight_surgeon"] is True
    contracts.validate("settings", r.json())
    state.advance_to(T0 + 4 * 3600)
    items = queue(client)["items"]
    assert items[1]["approved"] is False  # the seeded flight_surgeon item was already waiting
    assert items[3]["approved"] is True  # the new Air summary is auto-approved
    assert items[2]["approved"] is False  # urgent stays manual


def test_settings_enroll_rename_and_reset_baseline() -> None:
    state, client = make("quiet_day")
    body = client.get("/api/settings").json()
    contracts.validate("settings", body)
    assert [c["id"] for c in body["crew"]] == ["W1", "W2", "W3"]
    out = client.post("/api/settings/enroll", json={"id": "W4", "name": "Alex"})
    contracts.validate("settings", out.json())
    assert [c["name"] for c in out.json()["crew"]][-1] == "Alex"
    client.post("/api/settings/enroll", json={"id": "W1", "name": "Rowan"})
    status = client.get("/api/status").json()
    assert [c["name"] for c in status["crew"]][0] == "Rowan"
    state.advance_to(T0 + 3 * 3600)
    assert client.get("/api/status").json()["crew"][1]["baseline"] == "ready"
    r = client.post("/api/settings/reset-baseline", json={"crew": "W2", "metric": None})
    assert r.status_code == 200
    after = client.get("/api/status").json()
    assert after["crew"][1]["baseline"] == "learning"
    assert after["crew"][1]["learning_ends_t"] == pytest.approx(state.t_now + LEARNING_S)
    assert (
        after["crew_status"]["level"] == "green"
        and "alerts start in 2 h 0 min" in (after["crew_status"]["sentence"])
    )
    assert (
        client.post("/api/settings/reset-baseline", json={"crew": "W9", "metric": None}).status_code
        == 404
    )
    bad_id = {"id": "bad", "name": "x"}
    assert client.post("/api/settings/enroll", json=bad_id).status_code == 422


def test_checkin_adds_an_event_and_never_changes_a_level() -> None:
    state, client = make("scrubber_failure")
    state.advance_to(T0 + 3 * 3600)
    before = client.get("/api/status").json()
    assert before["checkin_due"] is True
    body = {"crew": "W2", "mood": 4, "sleep": 2, "note": "Slept badly."}
    r = client.post("/api/checkin", json=body)
    assert r.status_code == 200
    contracts.validate("checkin_response", r.json())
    contracts.validate("checkin_request", body)
    after = client.get("/api/status").json()
    assert [c["level"] for c in after["cards"]] == [c["level"] for c in before["cards"]]
    assert after["crew_status"] == before["crew_status"]
    assert [c["level"] for c in after["crew"]] == [c["level"] for c in before["crew"]]
    assert after["checkin_due"] is False
    events = client.get("/api/events").json()["events"]
    contracts.validate("events", {"events": events})
    mine = [e for e in events if e["id"] == r.json()["event_id"]]
    assert mine and mine[0]["kind"] == "checkin" and mine[0]["crew"] == "W2"
    assert "mood 4 of 5, sleep 2 of 5" in mine[0]["sentence"]


@pytest.mark.parametrize(
    "bad",
    [
        {"crew": "W1", "mood": 0, "sleep": 3, "note": None},
        {"crew": "W1", "mood": 3, "sleep": 6, "note": None},
        {"crew": "alice", "mood": 3, "sleep": 3, "note": None},
        {"crew": "W1", "mood": "high", "sleep": 3, "note": None},
    ],
)
def test_bad_checkins_are_rejected(bad: dict[str, Any]) -> None:
    _, client = make("quiet_day")
    assert client.post("/api/checkin", json=bad).status_code == 422
    assert (
        client.post("/api/checkin", json={"crew": "W7", "mood": 3, "sleep": 3}).status_code == 404
    )
