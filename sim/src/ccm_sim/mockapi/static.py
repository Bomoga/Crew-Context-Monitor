"""Serve the built dashboard (``dashboard/dist``) from the same app as the API.

Real files are served as they are; every other path that is not under ``/api`` returns
``index.html`` so client-side routes such as ``/history`` and ``/domain/air`` work on reload. Paths
under ``/api`` that no route handles keep returning a JSON 404.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


def default_dist() -> Path:
    """``CCM_DASHBOARD_DIST`` if set, else ``dashboard/dist`` in the repository."""
    env = os.environ.get("CCM_DASHBOARD_DIST")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[4] / "dashboard" / "dist"


def mount_dashboard(app: FastAPI, dist: Path) -> bool:
    """Add the static routes if ``dist/index.html`` exists; return whether they were added."""
    root = dist.resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    @app.get("/{full_path:path}", include_in_schema=False)
    def dashboard(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return True
