from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ccm_sim import contracts
from ccm_sim.mockapi.app import create_app
from ccm_sim.mockapi.state import MockState

INDEX = "<!doctype html><title>fake dashboard</title><div id=root></div>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside the dist folder", encoding="utf-8")
    return root


def client_for(dist: Path | None) -> TestClient:
    state = MockState("quiet_day", "max", t0=1_793_491_200.0)
    return TestClient(create_app(state, dist=dist))


def test_spa_routes_return_index_html(dist: Path) -> None:
    client = client_for(dist)
    for path in ("/", "/history", "/domain/air", "/events", "/settings", "/anything/else"):
        r = client.get(path)
        assert r.status_code == 200 and r.text == INDEX, path
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-cache"


def test_real_files_are_served_as_they_are(dist: Path) -> None:
    client = client_for(dist)
    js = client.get("/assets/app.js")
    assert js.status_code == 200 and js.text == "console.log('app')"
    assert "javascript" in js.headers["content-type"]
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/assets/missing.js").text == INDEX  # unknown paths fall back to the app


def test_api_routes_win_and_unknown_api_paths_are_json_404(dist: Path) -> None:
    client = client_for(dist)
    r = client.get("/api/status")
    assert r.status_code == 200
    contracts.validate("status", r.json())
    nope = client.get("/api/nope")
    assert nope.status_code == 404
    assert nope.headers["content-type"].startswith("application/json")
    assert nope.json() == {"detail": "Not Found"}
    assert client.get("/api").status_code == 404
    assert client.post("/api/nope", json={}).status_code in (404, 405)


def test_paths_cannot_escape_the_dist_folder(dist: Path) -> None:
    client = client_for(dist)
    for path in ("/..%2fsecret.txt", "/%2e%2e/secret.txt", "/assets/..%2f..%2fsecret.txt"):
        r = client.get(path)
        assert "outside the dist folder" not in r.text, path


def test_no_dist_means_no_static_routes(tmp_path: Path) -> None:
    client = client_for(tmp_path / "does-not-exist")
    assert client.get("/history").status_code == 404
    assert client.get("/history").headers["content-type"].startswith("application/json")
    assert client.get("/api/status").status_code == 200
