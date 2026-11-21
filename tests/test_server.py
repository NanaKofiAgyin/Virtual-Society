"""Unit tests for `server/app.py` using FastAPI's TestClient."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app


def _make_client(tmp_path: Path) -> TestClient:
    api = create_app(seed=42, width=15, height=15, db_path=tmp_path / "server_test.db")
    return TestClient(api)


def test_health_and_index(tmp_path: Path) -> None:
    """GET /health returns ok and GET / serves index.html."""
    with _make_client(tmp_path) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

        home = client.get("/")
        assert home.status_code == 200
        assert "Virtual Society" in home.text


def test_read_endpoints_map_state_agent_events(tmp_path: Path) -> None:
    """GET /api/map, /api/state, /api/agent/{id}, and /api/events return cached data."""
    with _make_client(tmp_path) as client:
        m = client.get("/api/map")
        assert m.status_code == 200
        assert m.json()["width"] == 15
        assert m.json()["height"] == 15

        st = client.get("/api/state")
        assert st.status_code == 200
        body = st.json()
        assert body["counts"]["humans"] == 10
        assert body["running"] is False

        first_id = body["humans"][0]["id"]
        ag = client.get(f"/api/agent/{first_id}")
        assert ag.status_code == 200
        assert ag.json()["id"] == first_id
        assert "persona" in ag.json()

        missing = client.get("/api/agent/does_not_exist")
        assert missing.status_code == 404

        ev = client.get("/api/events")
        assert ev.status_code == 200
        assert "events" in ev.json()


def test_control_step_save_load_and_reset(tmp_path: Path) -> None:
    """POST /api/control, /api/step, /api/save, /api/load, and /api/reset work end-to-end."""
    with _make_client(tmp_path) as client:
        # Load before any save returns 404
        assert client.post("/api/load").status_code == 404

        ctrl = client.post("/api/control", json={"running": False, "speed": 4.0})
        assert ctrl.status_code == 200
        assert ctrl.json() == {"running": False, "speed": 4.0}

        # Step twice and save
        assert client.post("/api/step").json()["tick"] == 1
        assert client.post("/api/step").json()["tick"] == 2
        saved = client.post("/api/save")
        assert saved.status_code == 200
        assert saved.json()["tick"] == 2

        # Advance further then load back to tick 2
        assert client.post("/api/step").json()["tick"] == 3
        loaded = client.post("/api/load")
        assert loaded.status_code == 200
        assert loaded.json()["tick"] == 2
        assert client.get("/api/state").json()["environment"]["tick"] == 2

        # Reset with a new seed
        reset = client.post("/api/reset", json={"seed": 99})
        assert reset.status_code == 200
        assert reset.json() == {"seed": 99, "tick": 0}
        assert client.get("/api/state").json()["seed"] == 99


def test_read_endpoints_do_not_block_when_sim_lock_is_held(tmp_path: Path) -> None:
    """GET endpoints serve from cache immediately even while `runner.lock` is held."""
    api = create_app(seed=7, width=15, height=15, db_path=tmp_path / "lock_test.db")
    runner = api.state.runner
    with TestClient(api) as client:
        with runner.lock:
            # Simulates a slow Ollama call inside tick() holding runner.lock
            assert client.get("/api/state").status_code == 200
            assert client.get("/api/map").status_code == 200
            assert client.get("/api/events").status_code == 200
            assert client.get("/api/agent/h_1").status_code == 200
