"""
tests/test_demo_mode.py
=======================
Automated verification tests for Veritas Gate Fix 0 Demo-First Foundation.
Tests demo-mode defaults, API fallback to seeded fixtures, data labeling,
safe separation (no on-chain tx in demo mode), and startup error reporting.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from analyzer.server import create_app


@pytest.fixture
def client():
    """Create Flask test client with DEMO_MODE enabled by default."""
    app = create_app(demo_mode=True)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def live_client():
    """Create Flask test client with DEMO_MODE disabled (live mode)."""
    app = create_app(demo_mode=False)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_reports_demo_mode(client):
    """Verify /health endpoint explicitly reports demo_mode status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "veritas-analyzer-api"
    assert data["demo_mode"] is True
    assert "rpc_connected" in data


def test_proposals_list_contains_seeded_demo_data(client):
    """Verify /proposals returns seeded proposals when no on-chain records exist."""
    resp = client.get("/proposals")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 6
    ids = [p["id"] for p in data]
    assert "prop-001" in ids
    assert "prop-002" in ids
    assert "prop-003" in ids


def test_seeded_proposal_by_id_has_demo_label(client):
    """Verify /proposals/<id> falls back to seeded fixtures and labels them as demo data."""
    resp = client.get("/proposals/prop-001")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == "prop-001"
    assert data["is_demo"] is True
    assert data["data_source"] == "seeded_demo_fixture"
    assert data["verdict"]["status"] == "VERIFIED"


def test_unregistered_nonexistent_proposal_returns_404(client):
    """Verify /proposals/<nonexistent> properly returns 404."""
    resp = client.get("/proposals/prop-999-does-not-exist")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "not found" in data["error"].lower()


def test_demo_review_submission_functional_and_simulated(client):
    """Verify /proposals/<id>/reviews records simulated review without on-chain execution."""
    payload = {
        "action": "APPROVE",
        "reason": "Detailed offline auditor rationale for demo test proposal",
        "reviewer": "0xAuditor77777777777777777777777777777777",
        "sync_on_chain": False
    }
    resp = client.post("/proposals/prop-003/reviews", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["is_demo"] is True
    assert data["simulated"] is True
    assert data["review"]["on_chain_confirmed"] is False
    assert "NOT an on-chain transaction" in data["review"]["note"]


def test_demo_review_submission_rejects_short_rationale(client):
    """Verify /proposals/<id>/reviews enforces minimum 10 characters rationale even in demo."""
    payload = {
        "action": "APPROVE",
        "reason": "short",
        "reviewer": "0xAuditor77777777777777777777777777777777"
    }
    resp = client.post("/proposals/prop-003/reviews", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "minimum 10 characters" in data["error"]


def test_demo_voting_requires_acknowledgement(client):
    """Verify /proposals/<id>/vote rejects submissions without explicit acknowledgment."""
    payload = {
        "choice": "FOR",
        "acknowledged": False
    }
    resp = client.post("/proposals/prop-001/vote", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert "must acknowledge" in data["error"].lower()


def test_demo_voting_records_simulated_ballot(client):
    """Verify /proposals/<id>/vote records simulated ballot without on-chain tx."""
    payload = {
        "choice": "FOR",
        "acknowledged": True
    }
    resp = client.post("/proposals/prop-001/vote", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["is_demo"] is True
    assert data["simulated"] is True
    assert data["on_chain_confirmed"] is False
    assert data["choice"] == "FOR"
    assert "NOT submitted to on-chain Governor" in data["note"]


def test_live_voting_fails_gracefully_when_governor_unconfigured(live_client):
    """Verify live mode fails clearly when on-chain Governor infrastructure is unavailable."""
    payload = {
        "choice": "FOR",
        "acknowledged": True
    }
    resp = live_client.post("/proposals/prop-001/vote", json=payload)
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["success"] is False
    assert "not configured" in data["error"].lower()


def test_startup_dependency_check_diagnostics():
    """Verify run.py's check_dependencies function returns actionable details."""
    import run
    # Current venv should pass dependency check
    venv_py = run.find_python_interpreter()
    ok, err = run.check_dependencies(venv_py)
    assert ok is True
    assert err is None

    # An invalid python binary or dummy command returns False with diagnostic error
    ok_bad, err_bad = run.check_dependencies("true")
    assert ok_bad is False
