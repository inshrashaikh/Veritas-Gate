"""Flask REST API for Veritas Gate Phase 5.

Connects simulation evidence, deterministic verdicts, proposal records,
human review queues, and audit provenance logs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from flask import Flask, jsonify, request

from analyzer.contract_adapter import ContractAdapter
from analyzer.provenance import EvidenceProvenance, TamperedContentError
from analyzer.review_queue import (
    InvalidStateTransitionError,
    ItemNotFoundError,
    ReviewQueue,
    ReviewQueueError,
    UnauthorizedReviewerError,
)
from analyzer.schemas import ScenarioConfig, SimulationResult
from analyzer.simulate import Simulator

logger = logging.getLogger("veritas.server")

# Maximum permitted payload size: 2 MB
MAX_CONTENT_LENGTH = 2 * 1024 * 1024


def create_app(
    storage_dir: Optional[str] = None,
    contract_adapter: Optional[ContractAdapter] = None,
    authorized_reviewers: Optional[set[str]] = None,
) -> Flask:
    """Factory creating and configuring the Flask API application."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    # Setup local storage paths
    base_dir = Path(storage_dir) if storage_dir else Path(__file__).resolve().parent / "data"
    base_dir.mkdir(parents=True, exist_ok=True)

    review_storage = base_dir / "review_queue.json"
    provenance_storage = base_dir / "provenance.json"
    proposals_storage = base_dir / "proposals.json"

    # Initialize submodules
    queue = ReviewQueue(
        storage_path=str(review_storage),
        authorized_reviewers=authorized_reviewers,
    )
    provenance = EvidenceProvenance(storage_path=str(provenance_storage))
    adapter = contract_adapter or ContractAdapter()

    # In-memory / persisted proposal index
    proposals_db: Dict[str, Dict[str, Any]] = {}

    def load_proposals():
        if proposals_storage.is_file():
            try:
                with open(proposals_storage, "r", encoding="utf-8") as f:
                    proposals_db.update(json.load(f))
            except Exception as e:
                logger.error("Failed to load proposals db: %s", e)

    def persist_proposals():
        try:
            with open(proposals_storage, "w", encoding="utf-8") as f:
                json.dump(proposals_db, f, indent=2)
        except Exception as e:
            logger.error("Failed to persist proposals db: %s", e)

    load_proposals()

    # Error Handlers
    @app.errorhandler(400)
    def handle_bad_request(e):
        return jsonify({"error": "Bad request", "detail": str(e)}), 400

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({"error": "Resource not found", "detail": str(e)}), 404

    @app.errorhandler(413)
    def handle_payload_too_large(e):
        return jsonify({"error": "Payload too large", "detail": "Maximum permitted size is 2MB"}), 413

    @app.errorhandler(500)
    def handle_server_error(e):
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500

    # =========================================================================
    # ENDPOINTS
    # =========================================================================

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service": "veritas-analyzer-api",
            "version": "1.0.0",
            "timestamp": time.time(),
            "rpc_connected": adapter.is_connected(),
        }), 200

    @app.route("/proposals", methods=["POST"])
    def register_proposal():
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        data = request.get_json()
        proposal_id = data.get("proposal_id")
        if not proposal_id or not isinstance(proposal_id, str):
            return jsonify({"error": "'proposal_id' is required and must be a non-empty string"}), 400

        text = data.get("text", "")
        calldata = data.get("calldata", "0x")
        disclosed_wallets = data.get("disclosed_wallets", [])

        # Validate addresses
        clean_wallets = []
        for w in disclosed_wallets:
            if not isinstance(w, str) or not re.match(r"^0x[0-9a-fA-F]{40}$", w):
                return jsonify({"error": f"Invalid address in disclosed_wallets: {w}"}), 400
            clean_wallets.append(w.lower())

        # Compute cryptographic hashes
        text_hash = "0x" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        calldata_bytes = bytes.fromhex(calldata[2:]) if calldata.startswith("0x") else calldata.encode("utf-8")
        calldata_hash = "0x" + hashlib.sha256(calldata_bytes).hexdigest()

        if proposal_id not in proposals_db:
            proposals_db[proposal_id] = {
                "proposal_id": proposal_id,
                "latest_version": 0,
                "versions": {},
            }

        prop_record = proposals_db[proposal_id]
        new_version = prop_record["latest_version"] + 1
        prop_record["latest_version"] = new_version

        version_data = {
            "version": new_version,
            "text": text,
            "text_hash": text_hash,
            "calldata": calldata,
            "calldata_hash": calldata_hash,
            "disclosed_wallets": clean_wallets,
            "created_at": time.time(),
        }
        prop_record["versions"][str(new_version)] = version_data

        # Register evidence artifacts in provenance manifest
        evidence_items = data.get("evidence", [])
        for ev in evidence_items:
            provenance.register_evidence(
                proposal_id=proposal_id,
                version=new_version,
                item_id=ev.get("item_id", "doc"),
                media_type=ev.get("media_type", "application/octet-stream"),
                source_uri=ev.get("source_uri", "local://proposals"),
                content=ev.get("content", "").encode("utf-8") if "content" in ev else None,
                expected_hash=ev.get("expected_hash"),
            )

        persist_proposals()

        return jsonify({
            "message": "Proposal registered successfully",
            "proposal_id": proposal_id,
            "version": new_version,
            "text_hash": text_hash,
            "calldata_hash": calldata_hash,
        }), 201

    @app.route("/proposals/<proposal_id>", methods=["GET"])
    def get_proposal(proposal_id: str):
        if proposal_id not in proposals_db:
            return jsonify({"error": f"Proposal '{proposal_id}' not found"}), 404

        prop = proposals_db[proposal_id]
        return jsonify({
            "proposal_id": prop["proposal_id"],
            "latest_version": prop["latest_version"],
            "versions": prop["versions"],
        }), 200

    @app.route("/analyze", methods=["POST"])
    def analyze_scenario():
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        data = request.get_json()
        try:
            scenario_cfg = ScenarioConfig.from_dict(data)
        except ValueError as ve:
            return jsonify({"error": "Scenario validation failed", "detail": str(ve)}), 400

        # Execute deterministic EVM simulation
        try:
            simulator = Simulator(scenario_cfg)
            sim_result: SimulationResult = simulator.run()
        except Exception as e:
            logger.error("Simulation execution error: %s", e)
            return jsonify({"error": "Simulation execution failed", "detail": str(e)}), 500

        # Compute deterministic governance verdict based on observable evidence
        verdict_status = "VERIFIED"
        reason = "All state diffs and trace invariants verified clean."

        if not sim_result.success:
            verdict_status = "MISMATCH"
            reason = f"Execution failed or reverted: {sim_result.errors}"
        else:
            # Check for high-risk findings (DELEGATECALL, SELFDESTRUCT, Proxy Upgrades, Unlimited Approvals)
            has_delegatecall = any(f["rule_id"] == "R001_DELEGATECALL" for f in sim_result.findings)
            has_selfdestruct = any(f["rule_id"] == "R002_SELFDESTRUCT" for f in sim_result.findings)
            has_proxy = any(f["rule_id"] == "R003_PROXY_UPGRADE" for f in sim_result.findings)
            has_unlimited = any(f["rule_id"] == "R004_UNLIMITED_APPROVAL" for f in sim_result.findings)

            if has_delegatecall or has_selfdestruct or has_proxy or has_unlimited:
                verdict_status = "NEEDS_REVIEW"
                reasons = []
                if has_delegatecall:
                    reasons.append("DELEGATECALL execution detected")
                if has_selfdestruct:
                    reasons.append("SELFDESTRUCT instruction detected")
                if has_proxy:
                    reasons.append("Proxy implementation modified")
                if has_unlimited:
                    reasons.append("Unlimited token approval granted")
                reason = "; ".join(reasons)

        evidence_hash = "0x" + hashlib.sha256(json.dumps(sim_result.to_dict(), sort_keys=True).encode("utf-8")).hexdigest()

        # If verdict is NEEDS_REVIEW, automatically queue it for human review
        if verdict_status == "NEEDS_REVIEW":
            queue.enqueue(
                proposal_id=scenario_cfg.scenario_id,
                version=1,
                automated_verdict={
                    "status": verdict_status,
                    "reason": reason,
                    "evidence_hash": evidence_hash,
                    "trace_complete": sim_result.trace_complete,
                    "timestamp": time.time(),
                },
            )

        return jsonify({
            "simulation": sim_result.to_dict(),
            "verdict": {
                "status": verdict_status,
                "reason": reason,
                "evidence_hash": evidence_hash,
                "trace_complete": sim_result.trace_complete,
            },
        }), 200

    @app.route("/reviews", methods=["GET"])
    def list_reviews():
        status_filter = request.args.get("status")
        items = queue.list_items(status_filter)
        return jsonify({"count": len(items), "items": [it.to_dict() for it in items]}), 200

    @app.route("/reviews/<proposal_id>/<int:version>", methods=["POST"])
    def post_review(proposal_id: str, version: int):
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        data = request.get_json()
        reviewer = data.get("reviewer")
        decision = data.get("decision")
        reason = data.get("reason")
        evidence_refs = data.get("evidence_refs", [])
        sync_on_chain = data.get("sync_on_chain", False)

        if not reviewer or not decision or not reason:
            return jsonify({"error": "Missing required fields: 'reviewer', 'decision', and 'reason' are mandatory"}), 400

        try:
            # 1. Update off-chain review queue
            tx_hash = None
            on_chain_confirmed = False

            # 2. If sync_on_chain requested, submit to local Anvil
            if sync_on_chain and adapter.is_connected():
                proposal_bytes32 = proposal_id.encode("utf-8").ljust(32, b"\x00")[:32]
                reason_hash_bytes = hashlib.sha256(reason.encode("utf-8")).digest()
                tx_h, confirmed, err = adapter.post_review_on_chain(
                    proposal_id_bytes32=proposal_bytes32,
                    version=version,
                    reviewer_address=reviewer,
                    decision_str=decision,
                    reason_hash_bytes32=reason_hash_bytes,
                )
                tx_hash = tx_h
                on_chain_confirmed = confirmed
                if err:
                    logger.warning("On-chain sync warning: %s", err)

            updated_item = queue.post_review(
                proposal_id=proposal_id,
                version=version,
                reviewer=reviewer,
                decision_str=decision,
                reason=reason,
                evidence_refs=evidence_refs,
                tx_hash=tx_hash,
                on_chain_confirmed=on_chain_confirmed,
            )

            return jsonify({
                "message": "Review submitted successfully",
                "item": updated_item.to_dict(),
            }), 200

        except UnauthorizedReviewerError as ure:
            return jsonify({"error": "Unauthorized reviewer", "detail": str(ure)}), 403
        except ItemNotFoundError as infe:
            return jsonify({"error": "Item not found in review queue", "detail": str(infe)}), 404
        except InvalidStateTransitionError as iste:
            return jsonify({"error": "Invalid state transition", "detail": str(iste)}), 409
        except ValueError as ve:
            return jsonify({"error": "Validation error", "detail": str(ve)}), 400
        except Exception as e:
            return jsonify({"error": "Failed to process review", "detail": str(e)}), 500

    @app.route("/audit/<proposal_id>", methods=["GET"])
    def get_audit(proposal_id: str):
        events = []

        # 1. Proposal history
        if proposal_id in proposals_db:
            prop = proposals_db[proposal_id]
            for v_num, v_data in sorted(prop["versions"].items(), key=lambda x: int(x[0])):
                events.append({
                    "event_type": "PROPOSAL_VERSION_REGISTERED",
                    "version": int(v_num),
                    "text_hash": v_data["text_hash"],
                    "calldata_hash": v_data["calldata_hash"],
                    "timestamp": v_data["created_at"],
                })

        # 2. Review Queue entries
        queued_items = [it for it in queue.list_items() if it.proposal_id == proposal_id]
        for it in queued_items:
            # Automated verdict event
            if it.automated_verdict:
                events.append({
                    "event_type": "AUTOMATED_VERDICT_POSTED",
                    "version": it.version,
                    "status": it.automated_verdict.get("status"),
                    "reason": it.automated_verdict.get("reason"),
                    "evidence_hash": it.automated_verdict.get("evidence_hash"),
                    "timestamp": it.automated_verdict.get("timestamp", it.created_at),
                })
            # Human reviews
            for rev in it.reviews:
                events.append({
                    "event_type": "HUMAN_REVIEW_RECORDED",
                    "version": it.version,
                    "reviewer": rev.reviewer,
                    "decision": rev.decision,
                    "reason": rev.reason,
                    "reason_hash": rev.reason_hash,
                    "tx_hash": rev.tx_hash,
                    "on_chain_confirmed": rev.on_chain_confirmed,
                    "timestamp": rev.timestamp,
                })

        events.sort(key=lambda x: x.get("timestamp", 0))

        return jsonify({
            "proposal_id": proposal_id,
            "event_count": len(events),
            "timeline": events,
        }), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
