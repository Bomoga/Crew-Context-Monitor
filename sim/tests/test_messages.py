from typing import Any

import pytest

from ccm_sim import contracts
from ccm_sim.cabin import CabinModel, load_cabin_params
from ccm_sim.messages import CabinNode, WearableNode, status_message
from ccm_sim.physiology import CrewPhysiology, load_physiology

T0 = 1_760_000_000.0
SEED = 11


def build() -> tuple[CabinNode, dict[str, WearableNode]]:
    cabin = CabinModel(load_cabin_params(), SEED, T0)
    params = load_physiology()
    wearables = {
        crew: WearableNode(CrewPhysiology(crew, params[crew], SEED, T0, cabin.temp_fn), SEED, T0)
        for crew in ("W1", "W2", "W3")
    }
    return CabinNode(cabin, SEED, T0), wearables


def test_ten_thousand_messages_validate_with_clean_seq_and_spacing() -> None:
    cabin, wearables = build()
    last_t: dict[str, float] = {}
    last_seq: dict[str, int] = {}
    count = 0

    def check(msg: dict[str, Any], kind: str, period: float) -> None:
        nonlocal count
        contracts.validate(kind, msg)
        key = msg["id"]
        if key in last_seq:
            assert msg["seq"] == last_seq[key] + 1
            assert msg["t_meas"] - last_t[key] == pytest.approx(period, abs=1e-9)
        else:
            assert msg["seq"] == 1
        last_seq[key], last_t[key] = msg["seq"], msg["t_meas"]
        count += 1

    for _ in range(3000):
        for node in wearables.values():
            check(node.next_message(), "wearable_telemetry", 5.0)
    for _ in range(1000):
        check(cabin.next_message(), "cabin_telemetry", 10.0)
    assert count == 10000


def test_hr_is_derived_from_the_ibi_in_the_window() -> None:
    _, wearables = build()
    node = wearables["W1"]
    for _ in range(50):
        msg = node.next_message()
        mean_ibi = sum(msg["ibi"]) / len(msg["ibi"])
        assert msg["hr"] == round(60000 / mean_ibi)
        assert 2 <= len(msg["ibi"]) <= 12


def test_no_finger_message_follows_d15() -> None:
    cabin = CabinModel(load_cabin_params(), SEED, T0)
    phys = CrewPhysiology("W2", load_physiology()["W2"], SEED, T0, cabin.temp_fn)
    node = WearableNode(phys, SEED, T0, finger_fn=lambda t: t < T0 + 100)
    msgs = [node.next_message() for _ in range(30)]
    late = msgs[-1]
    assert late["hr"] is None and late["spo2"] is None
    assert late["finger"] is False and late["ibi"] == []
    contracts.validate("wearable_telemetry", late)
    assert "finger" not in msgs[0]


def test_t_node_offset_within_two_seconds_plus_drift() -> None:
    _, wearables = build()
    node = wearables["W3"]
    first = node.next_message()
    assert abs(first["t_node"] - first["t_meas"]) < 2.0
    for _ in range(10000):
        last = node.next_message()
    drift = (last["t_node"] - last["t_meas"]) - (first["t_node"] - first["t_meas"])
    assert drift == pytest.approx(30e-6 * (last["t_meas"] - first["t_meas"]), abs=0.01)


def test_status_message_validates() -> None:
    contracts.validate("node_status", status_message("cabin", "C1", "online", T0))


def test_cabin_without_geiger_omits_counts() -> None:
    cabin = CabinNode(CabinModel(load_cabin_params(), SEED, T0), SEED, T0, geiger=False)
    msg = cabin.next_message()
    contracts.validate("cabin_telemetry", msg)
    assert "cpm" not in msg and "c10s" not in msg
