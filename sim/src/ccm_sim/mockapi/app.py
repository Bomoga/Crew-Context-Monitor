"""The mock API: the dashboard's ``/api`` routes served from a scenario running in-process.

Every response carries the exact shapes of ``contracts/api`` and ``source_mode: "mock"``. The real
API is meant to replace this app on the same port and paths. Routes under ``/api/_mock`` are for
development only.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from ccm_sim.mockapi.state import METRICS, MockState
from ccm_sim.scenario import ScenarioError

MetricName = Literal[
    "hr", "hr_resid", "prv", "spo2", "skin_c", "act",
    "co2_mmhg", "temp_c", "rh", "voc", "pm25", "cpm",
]  # fmt: skip


class ScenarioSwitch(BaseModel):
    name: str
    speed: float | Literal["max"] = 60.0


def create_app(state: MockState | None = None) -> FastAPI:
    """Build the app around ``state`` (default: scrubber_failure in manual, max-speed mode)."""
    app = FastAPI(title="Crew Context Monitor mock API", version="1.0.0")
    app.state.mock = state or MockState(speed="max")

    def mock() -> MockState:
        current: MockState = app.state.mock
        return current

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        return mock().status()

    @app.get("/api/history")
    def get_history(
        metric: MetricName,
        crew: str | None = None,
        hours: float = Query(6.0, gt=0, le=168),
        step: float = Query(60.0, ge=60, le=86400),
    ) -> dict[str, Any]:
        state_ = mock()
        _, is_crew = METRICS[metric]
        if is_crew and crew is not None and crew not in state_.world.crew:
            raise HTTPException(status_code=404, detail=f"unknown crew member {crew!r}")
        return state_.history(metric, crew, hours, step)

    @app.get("/api/events")
    def get_events(
        since: float | None = None, limit: int = Query(200, ge=1, le=1000)
    ) -> dict[str, Any]:
        return mock().events(since, limit)

    @app.post("/api/_mock/scenario")
    def switch_scenario(body: ScenarioSwitch) -> dict[str, Any]:
        """Development only: restart the mock on another scenario and speed."""
        state_ = mock()
        try:
            state_.configure(body.name, body.speed, learning=state_.learning)
        except ScenarioError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if body.speed != "max":
            state_.start()
        return {"scenario": body.name, "speed": body.speed, "t0": state_.t0}

    @app.get("/api/_mock/info")
    def mock_info() -> dict[str, Any]:
        """Development only: which scenario is running and where its clock is."""
        s = mock()
        return {
            "scenario": s.scenario_name,
            "speed": s.speed,
            "t0": s.t0,
            "t_now": s.t_now,
            "t_end": s.t_end,
            "finished": s.finished,
        }

    return app
