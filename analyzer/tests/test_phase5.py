"""Focused tests for Veritas Gate Phase 5.

Covers:
- SHA-256 evidence manifests with hash chaining and chain integrity verification.
- Review queue terminal state enforcement and MISMATCH protection.
- Contract adapter read operations and fail-closed disconnection handling.
- API endpoints: manifest retrieval/registration, review details, on-chain status, and demo labeling.
"""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from analyzer.contract_adapter import ContractAdapter
from analyzer.provenance import (
    GENESIS_MANIFEST_HASH,
    EvidenceProvenance,
    TamperedContentError,
)
from analyzer.review_queue import (
    InvalidStateTransitionError,
    ReviewDecision,
    ReviewQueue,
    ReviewState,
)
from analyzer.schemas import SCHEMA_VERSION, SimulationResult
from analyzer.server import create_app


# =============================================================================
# 1. EVIDENCE PROVENANCE & SHA-256 HASH CHAINING TESTS
# =============================================================================

def test_evidence_manifest_hash_chaining_integrity():
    with tempfile.TemporaryDirectory() as tmpdir:
        prov = EvidenceProvenance(str(Path(tmpdir) / "provenance.json"))

        proposal_id = "PROP-CHAIN-01"
        version = 1

        # Item 1: Proposal Specification Text
        content1 = b"Grant specification text version 1.0"
        item1 = prov.register_evidence(
            proposal_id=proposal_id,
            version=version,
            item_id="spec_text",
            media_type="text/markdown",
            source_uri="ipfs://QmSpec1",
            content=content1,
        )

        assert item1.previous_manifest_hash == GENESIS_MANIFEST_HASH
        assert item1.manifest_hash.startswith("0x")
        assert item1.integrity_verified is True

        # Item 2: Budget Breakdown Spreadsheet
        content2 = b"Budget line items: research $3M, infrastructure $2M"
        item2 = prov.register_evidence(
            proposal_id=proposal_id,
            version=version,
            item_id="budget_sheet",
            media_type="text/csv",
            source_uri="ipfs://QmBudget2",
            content=content2,
        )

        # Chained to item 1
        assert item2.previous_manifest_hash == item1.manifest_hash
        assert item2.manifest_hash != item1.manifest_hash

        # Item 3: Simulation Results Evidence
        content3 = b'{"success": true, "trace_complete": true}'
        item3 = prov.register_evidence(
            proposal_id=proposal_id,
            version=version,
            item_id="sim_evidence",
            media_type="application/json",
            source_uri="analyzer://sim/1",
            content=content3,
        )

        # Chained to item 2
        assert item3.previous_manifest_hash == item2.manifest_hash

        # Verify chain integrity
        valid, err = prov.verify_chain(proposal_id, version)
        assert valid is True
        assert err is None
        assert prov.get_manifest_root(proposal_id, version) == item3.manifest_hash

        # Summary check
        summary = prov.get_manifest_summary(proposal_id, version)
        assert summary["item_count"] == 3
        assert summary["chain_verified"] is True
        assert summary["root_hash"] == item3.manifest_hash
        assert "disclaimer" in summary


def test_evidence_manifest_detects_tampered_chain():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "provenance.json"
        prov = EvidenceProvenance(str(storage_file))

        proposal_id = "PROP-TAMPER-CHAIN"
        version = 1

        prov.register_evidence(
            proposal_id=proposal_id,
            version=version,
            item_id="doc1",
            media_type="text/plain",
            source_uri="local://1",
            content=b"Genesis document",
        )
        prov.register_evidence(
            proposal_id=proposal_id,
            version=version,
            item_id="doc2",
            media_type="text/plain",
            source_uri="local://2",
            content=b"Second document",
        )

        # Corrupt the chain link directly in the stored item
        items = prov._manifests[f"{proposal_id}:{version}"]
        items[1].previous_manifest_hash = "0x" + "f" * 64

        valid, err = prov.verify_chain(proposal_id, version)
        assert valid is False
        assert "Broken chain link" in err


def test_evidence_manifest_detects_tampered_content_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "provenance.json"
        prov = EvidenceProvenance(str(storage_file))

        proposal_id = "PROP-TAMPER-HASH"
        version = 1

        prov.register_evidence(
            proposal_id=proposal_id,
            version=version,
            item_id="doc1",
            media_type="text/plain",
            source_uri="local://1",
            content=b"Real content",
        )

        # Tamper with the content hash of the recorded item
        items = prov._manifests[f"{proposal_id}:{version}"]
        items[0].content_hash = "0x" + "e" * 64

        valid, err = prov.verify_chain(proposal_id, version)
        assert valid is False
        assert "Invalid manifest hash" in err


# =============================================================================
# 2. REVIEW QUEUE PHASE 5 ENHANCEMENTS
# =============================================================================

def test_review_queue_rejects_approve_on_mismatch():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = ReviewQueue(
            storage_path=str(Path(tmpdir) / "queue.json"),
            authorized_reviewers={"0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"},
        )

        # Enqueue with MISMATCH automated verdict
        queue.enqueue(
            proposal_id="PROP-MISMATCH-BLOCK",
            version=1,
            automated_verdict={
                "status": "MISMATCH",
                "reason": "Ownership hijacked",
            },
        )

        # Attempting APPROVE on proven MISMATCH must fail
        with pytest.raises(InvalidStateTransitionError, match="cannot be APPROVED"):
            queue.post_review(
                proposal_id="PROP-MISMATCH-BLOCK",
                version=1,
                reviewer="0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
                decision_str="APPROVE",
                reason="Attempting to overlook mismatch",
            )

        # REJECT or ESCALATE is valid
        item = queue.post_review(
            proposal_id="PROP-MISMATCH-BLOCK",
            version=1,
            reviewer="0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            decision_str="REJECT",
            reason="Confirmed malicious storage takeover",
        )
        assert item.state == ReviewState.REJECTED.value


def test_review_queue_summary_and_confirmation_update():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = ReviewQueue(
            storage_path=str(Path(tmpdir) / "queue.json"),
            authorized_reviewers={"0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"},
        )

        queue.enqueue("P1", 1, {"status": "NEEDS_REVIEW"})
        queue.enqueue("P2", 1, {"status": "NEEDS_REVIEW"})
        queue.enqueue("P3", 1, {"status": "NEEDS_REVIEW"})

        queue.post_review("P1", 1, "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266", "APPROVE", "Approved cleanly")
        queue.post_review("P2", 1, "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266", "REJECT", "Rejected: unsafe")

        summary = queue.get_summary()
        assert summary["total"] == 3
        assert summary["pending"] == 1
        assert summary["approved"] == 1
        assert summary["rejected"] == 1
        assert summary["escalated"] == 0

        # Update on-chain confirmation
        tx_hash = "0x" + "a" * 64
        ok = queue.update_on_chain_confirmation("P1", 1, tx_hash, True)
        assert ok is True
        item = queue.get("P1", 1)
        assert item.reviews[-1].tx_hash == tx_hash
        assert item.reviews[-1].on_chain_confirmed is True


# =============================================================================
# 3. CONTRACT ADAPTER PHASE 5 READ OPERATIONS
# =============================================================================

def test_contract_adapter_read_methods_disconnected():
    adapter = ContractAdapter(rpc_url="http://127.0.0.1:59999")
    assert adapter.is_connected() is False

    # Fail closed on missing connection
    prop = adapter.get_on_chain_proposal(b"P" * 32, 1)
    assert prop is None

    verdict = adapter.get_on_chain_verdict(b"P" * 32, 1)
    assert verdict is None

    review = adapter.get_on_chain_review(b"P" * 32, 1)
    assert review is None

    eligible, reason = adapter.is_on_chain_eligible(b"P" * 32, 1)
    assert eligible is False
    assert "not connected" in reason.lower()

    challenges = adapter.get_on_chain_challenge_status(b"P" * 32, 1)
    assert challenges["connected"] is False

    treasury = adapter.get_treasury_status(b"P" * 32, 1)
    assert treasury["connected"] is False


# =============================================================================
# 4. REST API PHASE 5 ENDPOINTS & INTEGRATION TESTS
# =============================================================================

@pytest.fixture
def api_client():
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_adapter = MagicMock(spec=ContractAdapter)
        mock_adapter.is_connected.return_value = True
        mock_adapter.get_on_chain_proposal.return_value = {
            "version": 1,
            "text_hash": "0x1111",
            "calldata_hash": "0x2222",
            "disclosed_wallets": ["0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"],
            "timestamp": 1000,
            "author": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        }
        mock_adapter.get_on_chain_verdict.return_value = {
            "status": "VERIFIED",
            "text_hash": "0x1111",
            "calldata_hash": "0x2222",
            "evidence_hash": "0x3333",
            "timestamp": 1000,
            "finalized": True,
        }
        mock_adapter.is_on_chain_eligible.return_value = (True, "Automated verdict is VERIFIED")
        mock_adapter.get_on_chain_review.return_value = None
        mock_adapter.get_on_chain_challenge_status.return_value = {
            "active_challenge": False,
            "disqualified": False,
            "connected": True,
        }
        mock_adapter.get_treasury_status.return_value = {
            "is_paused": False,
            "pause_reason_hash": "0x0",
            "challenge_window": 172800,
            "connected": True,
            "executed": False,
            "authorized": True,
        }

        app = create_app(
            storage_dir=tmpdir,
            contract_adapter=mock_adapter,
            authorized_reviewers={"0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"},
            demo_mode=True,
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


def test_api_evidence_manifest_endpoints(api_client):
    proposal_id = "PROP-API-EVID"

    # Register proposal
    api_client.post(
        "/proposals",
        json={
            "proposal_id": proposal_id,
            "text": "Grant text",
            "calldata": "0x1234",
            "disclosed_wallets": ["0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"],
        },
    )

    # Register evidence artifact via /manifest/<proposal_id>/<version>
    res_post = api_client.post(
        f"/manifest/{proposal_id}/1",
        json={
            "item_id": "audit_report_pdf",
            "media_type": "application/pdf",
            "source_uri": "ipfs://QmAuditReport",
            "content": "Formal security verification report content",
        },
    )
    assert res_post.status_code == 201
    post_data = res_post.get_json()
    assert post_data["item"]["item_id"] == "audit_report_pdf"
    assert post_data["item"]["manifest_hash"].startswith("0x")
    assert post_data["manifest"]["chain_verified"] is True

    # Retrieve manifest summary via GET /manifest/<proposal_id>
    res_get = api_client.get(f"/manifest/{proposal_id}")
    assert res_get.status_code == 200
    manifest = res_get.get_json()
    assert manifest["proposal_id"] == proposal_id
    assert manifest["version"] == 1
    assert manifest["item_count"] == 1
    assert manifest["chain_verified"] is True
    assert manifest["root_hash"].startswith("0x")

    # Tampered content registration fails closed
    fake_hash = "0x" + "9" * 64
    res_tamper = api_client.post(
        f"/manifest/{proposal_id}/1",
        json={
            "item_id": "tampered_item",
            "content": "Real content",
            "expected_hash": fake_hash,
        },
    )
    assert res_tamper.status_code == 400
    assert "Tampered content detected" in res_tamper.get_json()["error"]


def test_api_analyze_registers_provenance_and_labels_fixtures(api_client):
    scenario = {
        "scenario_id": "SCEN-PHASE5-ANALYZE",
        "chain_id": 31337,
        "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    }
    mock_clean = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="SCEN-PHASE5-ANALYZE",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=True,
        findings=[],
        errors=[],
    )

    with patch("analyzer.server.Simulator.run", return_value=mock_clean):
        res = api_client.post("/analyze", json=scenario)
        assert res.status_code == 200
        data = res.get_json()

        assert data["verdict"]["status"] == "VERIFIED"
        assert "manifest_root_hash" in data["verdict"]
        assert "evidence_manifest" in data
        assert data["evidence_manifest"]["chain_verified"] is True

        # Check evidence item was registered in provenance
        items = data["evidence_manifest"]["items"]
        assert any(it["item_id"] == "simulation_evidence" for it in items)


def test_api_onchain_status_endpoint(api_client):
    res = api_client.get("/onchain/PROP-1/1")
    assert res.status_code == 200
    data = res.get_json()
    assert data["rpc_connected"] is True
    assert data["proposal"]["version"] == 1
    assert data["verdict"]["status"] == "VERIFIED"
    assert data["eligible_for_execution"] is True
    assert data["treasury"]["connected"] is True
    assert data["treasury"]["challenge_window"] == 172800


def test_api_reviews_details_and_summary(api_client):
    # Enqueue a proposal
    mock_risky = SimulationResult(
        schema_version=SCHEMA_VERSION,
        scenario_id="PROP-REV-DETAIL",
        chain_id=31337,
        simulation_mode="read_only",
        success=True,
        state_diffs=[],
        logs=[],
        trace_complete=True,
        findings=[{"rule_id": "R001_DELEGATECALL", "severity": "HIGH", "title": "Risk", "explanation": "risk", "evidence": {}}],
        errors=[],
    )
    with patch("analyzer.server.Simulator.run", return_value=mock_risky):
        api_client.post("/analyze", json={
            "scenario_id": "PROP-REV-DETAIL",
            "chain_id": 31337,
            "sender": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "target": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
        })

    # Retrieve specific item details via GET /reviews/<proposal_id>/<version>
    res_item = api_client.get("/reviews/PROP-REV-DETAIL/1")
    assert res_item.status_code == 200
    item = res_item.get_json()
    assert item["proposal_id"] == "PROP-REV-DETAIL"
    assert item["state"] == "PENDING"
    assert item["automated_verdict"]["status"] == "NEEDS_REVIEW"

    # Verify summary in GET /reviews
    res_list = api_client.get("/reviews")
    assert res_list.status_code == 200
    list_data = res_list.get_json()
    assert "summary" in list_data
    assert list_data["summary"]["pending"] >= 1
