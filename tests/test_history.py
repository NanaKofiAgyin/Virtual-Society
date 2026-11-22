"""Unit tests for `simulation/history.py` and the upgraded server history/layer/fast-forward APIs."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agents import HumanAgent, random_genome
from server.app import create_app
from simulation import HistoryTracker


def test_milestones_chronicle_and_novelty_metrics() -> None:
    """HistoryTracker logs milestones grouped by era and computes novelty metrics."""
    hist = HistoryTracker(stagnation_years=3)
    hist.observe_event({"tick": 10, "kind": "discovery", "message": "Ada discovered fire"}, year=1, era="Stone Age")
    hist.observe_event({"tick": 20, "kind": "discovery", "message": "Ada discovered farming"}, year=2, era="Neolithic Era")
    hist.observe_event({"tick": 30, "kind": "speciation", "message": "New species arctic_deer evolved"}, year=2, era="Neolithic Era")
    hist.observe_environment("ice_age", tick=40, year=2, era="Neolithic Era")
    hist.observe_event({"tick": 50, "kind": "war", "message": "Border conflict erupted"}, year=3, era="Neolithic Era")

    chron = hist.chronicle()
    assert "Stone Age" in chron and "Neolithic Era" in chron
    assert chron["Stone Age"][0]["title"] == "First Fire"
    assert any(m["kind"] == "ice_age" for m in chron["Neolithic Era"])
    assert any(m["kind"] == "war" for m in chron["Neolithic Era"])
    assert hist.new_tech_per_century(current_year=10) == 20.0


def test_stagnation_detector_identifies_cause_and_suggestion() -> None:
    """Stagnation detector fires after X quiet years with likely cause and setting suggestion."""
    hist = HistoryTracker(stagnation_years=3)
    hist.last_novelty_year = 1

    # Too-small population triggers population warning
    small_humans = [HumanAgent(id="h1", name="Ada", position=(5, 5))]
    warn = hist.record_year_metrics(year=4, humans=small_humans, animals=[], society={"era": "Stone Age"})
    assert warn is not None
    assert warn["quiet_years"] == 3
    assert "small" in warn["cause"].lower()
    assert "FOUNDING_HUMANS" in warn["suggestion"]


def test_server_layers_history_and_fast_forward_endpoints(tmp_path: Path) -> None:
    """GET /api/layers, GET /api/history, and POST /api/fast_forward work via TestClient."""
    api = create_app(seed=42, width=20, height=20, db_path=tmp_path / "hist_server.db")
    with TestClient(api) as client:
        layers = client.get("/api/layers")
        assert layers.status_code == 200
        lbody = layers.json()
        assert len(lbody["temperature"]) == 400
        assert len(lbody["ocean_depth"]) == 400

        ff = client.post("/api/fast_forward", json={"days": 3})
        assert ff.status_code == 200
        assert ff.json()["tick"] == 3 * 24

        hist = client.get("/api/history")
        assert hist.status_code == 200
        hbody = hist.json()
        assert "chronicle" in hbody and "metrics" in hbody and "phylo_tree" in hbody
