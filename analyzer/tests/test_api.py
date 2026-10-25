"""Comprehensive integration and unit tests for the Flask REST API."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from analyzer.contract_adapter import ContractAdapter
from analyzer.schemas import SCHEMA_VERSION, SimulationResult
from analyzer.server import create_app


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_adapter = MagicMock(spec=ContractAdapter)
        mock_adapter.is_connected.return_value = True

        authorized = {"0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"}
        app = create_app(
            storage_dir=tmpdir,
            contract_adapter=mock_adapter,
            authorized_reviewers=authorized,
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "veritas-analyzer-api"
    assert data["rpc_connected"] is True


def test_proposals_registration_and_history(client):
    # 1. Register proposal version 1
    payload_v1 = {
        "proposal_id": "PROP-API-1",
        "text": "Grant proposal v1",
        "calldata": "0x12345678",
        "disclosed_wallets": ["0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"],
        "evidence": [
            {
                "item_id": "budget_pdf",
                "media_type": "application/pdf",
                "source_uri": "ipfs://Qm123",
                "content": "budget content",
            }
        ],
    }
    res1 = client.post("/proposals", json=payload_v1)
    assert res1.status_code == 201
    data1 = res1.get_json()
    assert data1["proposal_id"] == "PROP-API-1"
    assert data1["version"] == 1
    assert data1["text_hash"].startswith("0x")
    assert data1["calldata_hash"].startswith("0x")

    # 2. Update to version 2
    payload_v2 = {
        "proposal_id": "PROP-API-1",
        "text": "Revised grant proposal v2",
        "calldata": "0xabcdef01",
        "disclosed_wallets": ["0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"],
    }
    res2 = client.post("/proposals", json=payload_v2)
    assert res2.status_code == 201
    data2 = res2.get_json()
    assert data2["version"] == 2

    # 3. Retrieve proposal history
    res_get = client.get("/proposals/PROP-API-1")
    assert res_get.status_code == 200
    get_data = res_get.get_json()
    assert get_data["latest_version"] == 2
    assert "1" in get_data["versions"]
    assert "2" in get_data["versions"]
    assert get_data["versions"]["1"]["text"] == "Grant proposal v1"
    assert get_data["versions"]["2"]["text"] == "Revised grant proposal v2"

    # 4. Unknown proposal returns 404
    res_404 = client.get("/proposals/NON-EXISTENT")
    assert res_404.status_code == 404


def test_proposals_validation_errors(client):
    # Missing proposal_id
    res1 = client.post("/proposals", json={"text": "hello"})
    assert res1.status_code == 400

    # Malformed wallet address
    res2 = client.post(
        "/proposals",
        json={
            "proposal_id": "P-BAD-WALLET",
            "disclosed_wallets": ["not-a-valid-eth-address"],
        },
    )
    assert res2.status_code == 400

    # Non-json request
    res3 = client.post("/proposals", data="raw text", content_type="text/plain")
    assert res3.status_code == 400


def test_analyze_endpoint_clean_and_risky(client):
    # Scenario data
    clean_scenario = {
        "scenario_id": "SCEN-CLEAN-01",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
        "calldata": "0x12345678",
        "simulation_mode": "read_only",
    }

    # Mock simulator returning clean success
    mock_clean_result = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="SCEN-CLEAN-01",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=True,
        findings=[],
        errors=[],
    )

    with patch("analyzer.server.Simulator.run", return_value=mock_clean_result):
        res = client.post("/analyze", json=clean_scenario)
        assert res.status_code == 200
        data = res.get_json()
        assert data["verdict"]["status"] == "VERIFIED"

    # Risky scenario with DELEGATECALL finding
    mock_risky_result = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="SCEN-RISKY-01",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=True,
        findings=[
            {
                "rule_id": "R001_DELEGATECALL",
                "severity": "HIGH",
                "title": "DELEGATECALL detected",
                "explanation": "Target executed in caller storage",
                "evidence": {},
            }
        ],
        errors=[],
    )

    risky_scenario = dict(clean_scenario, scenario_id="SCEN-RISKY-01")
    with patch("analyzer.server.Simulator.run", return_value=mock_risky_result):
        res2 = client.post("/analyze", json=risky_scenario)
        assert res2.status_code == 200
        data2 = res2.get_json()
        assert data2["verdict"]["status"] == "NEEDS_REVIEW"
        assert "DELEGATECALL" in data2["verdict"]["reason"]

        # Verify it was automatically enqueued in review queue
        res_reviews = client.get("/reviews?status=PENDING")
        assert res_reviews.status_code == 200
        review_items = res_reviews.get_json()["items"]
        assert any(it["proposal_id"] == "SCEN-RISKY-01" for it in review_items)


def test_reviews_endpoints_workflow(client):
    # Enqueue an item via analyze endpoint
    mock_result = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="PROP-REV-01",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=True,
        findings=[{"rule_id": "R001_DELEGATECALL", "severity": "HIGH", "title": "DELEGATECALL", "explanation": "risk", "evidence": {}}],
        errors=[],
    )
    scenario = {
        "scenario_id": "PROP-REV-01",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    }
    with patch("analyzer.server.Simulator.run", return_value=mock_result):
        client.post("/analyze", json=scenario)

    # 1. List pending reviews
    res_list = client.get("/reviews")
    assert res_list.status_code == 200
    assert any(it["proposal_id"] == "PROP-REV-01" for it in res_list.get_json()["items"])

    # 2. Reject empty reason
    res_no_reason = client.post(
        "/reviews/PROP-REV-01/1",
        json={
            "reviewer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "decision": "APPROVE",
            "reason": "",
        },
    )
    assert res_no_reason.status_code == 400

    # 3. Reject unauthorized reviewer
    res_unauth = client.post(
        "/reviews/PROP-REV-01/1",
        json={
            "reviewer": "0x1111111111111111111111111111111111111111",
            "decision": "APPROVE",
            "reason": "Looks fine",
        },
    )
    assert res_unauth.status_code == 403

    # 4. Escalate decision
    res_esc = client.post(
        "/reviews/PROP-REV-01/1",
        json={
            "reviewer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "decision": "ESCALATE",
            "reason": "Need technical lead signoff on storage slots",
        },
    )
    assert res_esc.status_code == 200
    assert res_esc.get_json()["item"]["state"] == "ESCALATED"

    # 5. Final Approve decision
    res_app = client.post(
        "/reviews/PROP-REV-01/1",
        json={
            "reviewer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "decision": "APPROVE",
            "reason": "Storage slots reviewed and confirmed safe",
        },
    )
    assert res_app.status_code == 200
    assert res_app.get_json()["item"]["state"] == "APPROVED"

    # 6. Reject subsequent review on terminal APPROVED state (409 Conflict)
    res_dup = client.post(
        "/reviews/PROP-REV-01/1",
        json={
            "reviewer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "decision": "REJECT",
            "reason": "Changed my mind",
        },
    )
    assert res_dup.status_code == 409


def test_audit_endpoint(client):
    # Register proposal
    client.post(
        "/proposals",
        json={
            "proposal_id": "PROP-AUDIT-01",
            "text": "Initial proposal",
            "calldata": "0x1234",
            "disclosed_wallets": ["0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"],
        },
    )

    # Analyze (NEEDS_REVIEW)
    mock_result = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="PROP-AUDIT-01",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=True,
        findings=[{"rule_id": "R001_DELEGATECALL", "severity": "HIGH", "title": "DELEGATECALL", "explanation": "risk", "evidence": {}}],
        errors=[],
    )
    with patch("analyzer.server.Simulator.run", return_value=mock_result):
        client.post(
            "/analyze",
            json={
                "scenario_id": "PROP-AUDIT-01",
                "chain_id": 31337,
                "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
                "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
            },
        )

    # Submit Human Review
    client.post(
        "/reviews/PROP-AUDIT-01/1",
        json={
            "reviewer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "decision": "APPROVE",
            "reason": "Auditor verification passed",
        },
    )

    # Retrieve audit trail
    res_audit = client.get("/audit/PROP-AUDIT-01")
    assert res_audit.status_code == 200
    audit_data = res_audit.get_json()
    assert audit_data["proposal_id"] == "PROP-AUDIT-01"
    timeline = audit_data["timeline"]
    assert len(timeline) >= 3

    event_types = [e["event_type"] for e in timeline]
    assert "PROPOSAL_VERSION_REGISTERED" in event_types
    assert "AUTOMATED_VERDICT_POSTED" in event_types
    assert "HUMAN_REVIEW_RECORDED" in event_types


def test_oversized_payload_rejected(client):
    large_string = "a" * (3 * 1024 * 1024)  # 3 MB
    res = client.post(
        "/proposals",
        json={"proposal_id": "OVERSIZED", "text": large_string},
    )
    assert res.status_code == 413


def test_malformed_json_handling(client):
    # Malformed JSON syntax (syntax error)
    res = client.post(
        "/proposals",
        data="{\"broken_json\": ",
        content_type="application/json",
    )
    assert res.status_code == 400

    res2 = client.post(
        "/analyze",
        data="{\"broken_json\": ",
        content_type="application/json",
    )
    assert res2.status_code == 400

    res3 = client.post(
        "/reviews/PROP-1/1",
        data="{\"broken_json\": ",
        content_type="application/json",
    )
    assert res3.status_code == 400


def test_analyze_incomplete_evidence_and_errors(client):
    # Incomplete scenario: missing sender and target
    incomplete_payload = {
        "scenario_id": "INCOMPLETE-01",
        "chain_id": 31337,
    }
    res = client.post("/analyze", json=incomplete_payload)
    assert res.status_code == 400
    assert "validation failed" in res.get_json()["error"]

    # Analyzer execution error / exception
    valid_payload = {
        "scenario_id": "ERR-01",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    }
    with patch("analyzer.server.Simulator.run", side_effect=RuntimeError("EVM node crashed")):
        res_err = client.post("/analyze", json=valid_payload)
        assert res_err.status_code == 500
        assert "EVM node crashed" in res_err.get_json()["detail"]


def test_review_sync_on_chain_handling():
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_adapter = MagicMock(spec=ContractAdapter)
        mock_adapter.is_connected.return_value = True
        # Simulate unconfirmed transaction / warning
        mock_adapter.post_review_on_chain.return_value = (
            "0x" + "b" * 64,
            False,
            "Transaction pending confirmation or reverted",
        )

        authorized = {"0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"}
        app = create_app(
            storage_dir=tmpdir,
            contract_adapter=mock_adapter,
            authorized_reviewers=authorized,
        )
        app.config["TESTING"] = True

        with app.test_client() as c:
            # Enqueue an item
            mock_result = SimulationResult(
                schema_version=SCHEMA_VERSION,
                scenario_id="PROP-SYNC-01",
                chain_id=31337,
                simulation_mode="read_only",
                success=True,
                state_diffs=[],
                logs=[],
                trace_complete=True,
                findings=[{"rule_id": "R001_DELEGATECALL", "severity": "HIGH", "title": "Risk", "explanation": "risk", "evidence": {}}],
                errors=[],
            )
            with patch("analyzer.server.Simulator.run", return_value=mock_result):
                c.post("/analyze", json={
                    "scenario_id": "PROP-SYNC-01",
                    "chain_id": 31337,
                    "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
                    "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
                })

            # Submit review with sync_on_chain = True
            res = c.post(
                "/reviews/PROP-SYNC-01/1",
                json={
                    "reviewer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
                    "decision": "APPROVE",
                    "reason": "Approved with pending chain confirmation",
                    "sync_on_chain": True,
                },
            )
            assert res.status_code == 200
            item = res.get_json()["item"]
            assert item["state"] == "APPROVED"
            assert len(item["reviews"]) == 1
            rev = item["reviews"][0]
            assert rev["tx_hash"] == "0x" + "b" * 64
            assert rev["on_chain_confirmed"] is False


def test_proposals_persistence_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_adapter = MagicMock(spec=ContractAdapter)
        mock_adapter.is_connected.return_value = True

        app1 = create_app(storage_dir=tmpdir, contract_adapter=mock_adapter)
        app1.config["TESTING"] = True
        with app1.test_client() as c1:
            res = c1.post("/proposals", json={
                "proposal_id": "PROP-RELOAD-TEST",
                "text": "Initial reload text",
                "calldata": "0x1234",
            })
            assert res.status_code == 201

        # Reinstantiate app with same directory
        app2 = create_app(storage_dir=tmpdir, contract_adapter=mock_adapter)
        app2.config["TESTING"] = True
        with app2.test_client() as c2:
            res = c2.get("/proposals/PROP-RELOAD-TEST")
            assert res.status_code == 200
            data = res.get_json()
            assert data["proposal_id"] == "PROP-RELOAD-TEST"
            assert data["latest_version"] == 1
            assert data["versions"]["1"]["text"] == "Initial reload text"


def test_analyze_fallback_demo_fixture_when_node_offline(client):
    """When Anvil is offline and DEMO_MODE is true, /analyze returns labelled demo fixture."""
    payload = {
        "scenario_id": "scenario-honest-grant-5m",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
        "rpc_url": "http://127.0.0.1:8545",
    }
    # Mock offline node returning failure
    mock_offline_result = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="scenario-honest-grant-5m",
        chain_id=31337,
        simulation_mode="read_only",
        success=False,
        state_diffs=[],
        logs=[],
        trace_complete=False,
        findings=[],
        errors=["Failed to connect to local RPC at http://127.0.0.1:8545: Connection refused"],
    )
    with patch("analyzer.server.Simulator.run", return_value=mock_offline_result):
        res = client.post("/analyze", json=payload)
        assert res.status_code == 200
        body = res.get_json()
        assert body["simulation"]["is_demo"] is True
        assert body["simulation"]["data_source"] == "synthetic_demo_fixture"
        assert "[DEMO FIXTURE]" in body["simulation"]["simulation_note"]
        assert body["verdict"]["is_demo"] is True
        assert body["verdict"]["data_source"] == "synthetic_demo_fixture"


def test_analyze_fail_closed_on_incomplete_trace(client):
    """Missing or incomplete trace data must NEVER be treated as safe (VERIFIED)."""
    payload = {
        "scenario_id": "TEST-INCOMPLETE-TRACE",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    }
    mock_incomplete = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="TEST-INCOMPLETE-TRACE",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=False,
        findings=[{"rule_id": "R000_INCONCLUSIVE_TRACE", "severity": "WARNING", "title": "Inconclusive Trace", "explanation": "no trace", "evidence": {}}],
        errors=["Incomplete trace: buffer exceeded limit"],
    )
    with patch("analyzer.server.Simulator.run", return_value=mock_incomplete):
        res = client.post("/analyze", json=payload)
        assert res.status_code == 200
        verdict = res.get_json()["verdict"]
        assert verdict["status"] == "NEEDS_REVIEW"
        assert verdict["trace_complete"] is False
        assert "incomplete or unavailable" in verdict["reason"]


def test_analyze_ownership_hijack_verdict_mismatch(client):
    """Unexpected ownership change in state diffs must immediately trigger MISMATCH."""
    payload = {
        "scenario_id": "TEST-OWNER-TAKEOVER",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    }
    mock_takeover = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="TEST-OWNER-TAKEOVER",
        chain_id=31337,
        simulation_mode="stateful_execution",
        success=True,
        state_diffs=[
            {
                "effect_id": "treasury_owner:0x1111111111111111111111111111111111111111",
                "effect_type": "treasury_owner",
                "address": "0x1111111111111111111111111111111111111111",
                "before_value": "0x2222222222222222222222222222222222222222",
                "after_value": "0x9999999999999999999999999999999999999999",
            }
        ],
        logs=[],
        trace_complete=True,
        findings=[{"rule_id": "R001_DELEGATECALL", "severity": "HIGH", "title": "DELEGATECALL", "explanation": "delegatecall", "evidence": {}}],
        errors=[],
    )
    with patch("analyzer.server.Simulator.run", return_value=mock_takeover):
        res = client.post("/analyze", json=payload)
        assert res.status_code == 200
        verdict = res.get_json()["verdict"]
        assert verdict["status"] == "MISMATCH"
        assert "ownership hijacked" in verdict["reason"].lower()

