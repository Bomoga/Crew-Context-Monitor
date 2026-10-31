import pytest

from ccm_sim.clock import SimClock
from ccm_sim.rng import stream


class FakeReal:
    """Fake real-time source: ``sleep`` advances ``t`` and counts calls."""

    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


def make(speed: float | str) -> tuple[SimClock, FakeReal]:
    fake = FakeReal()
    return SimClock(5000.0, speed, real_now=fake.now, sleep=fake.sleep), fake


def test_speed_60_one_real_second_is_sixty_sim_seconds() -> None:
    clock, fake = make(60)
    fake.t += 1.0
    assert clock.now() == pytest.approx(5060.0)


def test_sleep_until_waits_the_scaled_real_time() -> None:
    clock, fake = make(60)
    clock.sleep_until(5120.0)
    assert fake.sleeps == [pytest.approx(2.0)]
    assert clock.now() == pytest.approx(5120.0)


def test_sleep_until_past_time_does_not_sleep() -> None:
    clock, fake = make(10)
    fake.t += 100.0
    clock.sleep_until(5001.0)
    assert fake.sleeps == []


def test_max_never_sleeps_and_jumps_forward() -> None:
    clock, fake = make("max")
    clock.sleep_until(9000.0)
    clock.sleep_until(8000.0)
    assert fake.sleeps == []
    assert clock.now() == 9000.0


@pytest.mark.parametrize("bad", [0, -1, "fast"])
def test_bad_speed_rejected(bad: float | str) -> None:
    with pytest.raises(ValueError):
        SimClock(0.0, bad)


def test_same_seed_is_byte_identical() -> None:
    a = stream(42, "crew.W1.hr").normal(size=1000)
    b = stream(42, "crew.W1.hr").normal(size=1000)
    assert a.tobytes() == b.tobytes()


def test_different_seed_or_name_differs() -> None:
    base = stream(42, "crew.W1.hr").normal(size=10).tobytes()
    assert base != stream(43, "crew.W1.hr").normal(size=10).tobytes()
    assert base != stream(42, "crew.W2.hr").normal(size=10).tobytes()


def test_adding_w3_leaves_w1_identical() -> None:
    only_w1 = stream(7, "crew.W1.ibi").normal(size=500)
    stream(7, "crew.W3.ibi").normal(size=500)  # a third crew member draws numbers too
    with_w3 = stream(7, "crew.W1.ibi").normal(size=500)
    assert only_w1.tobytes() == with_w3.tobytes()
