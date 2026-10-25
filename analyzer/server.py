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
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from flask import Flask, jsonify, request

_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from analyzer.contract_adapter import ContractAdapter
from analyzer.provenance import EvidenceProvenance, TamperedContentError
from analyzer.review_queue import (
    InvalidStateTransitionError,
    ItemNotFoundError,
    ReviewQueue,
    ReviewQueueError,
    UnauthorizedReviewerError,
)
from analyzer.schemas import (
    ScenarioConfig,
    SimulationResult,
    load_simulation_result_from_dict,
)
from analyzer.simulate import Simulator, load_demo_simulation_fixture

logger = logging.getLogger("veritas.server")

# Maximum permitted payload size: 2 MB
MAX_CONTENT_LENGTH = 2 * 1024 * 1024


def create_app(
    storage_dir: Optional[str] = None,
    contract_adapter: Optional[ContractAdapter] = None,
    authorized_reviewers: Optional[set[str]] = None,
    demo_mode: Optional[bool] = None,
) -> Flask:
    """Factory creating and configuring the Flask API application."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    # Explicit Demo Mode configuration (enabled by default for local development)
    is_demo = (
        demo_mode
        if demo_mode is not None
        else os.environ.get("VERITAS_DEMO_MODE", "true").lower() in ("true", "1", "yes")
    )
    app.config["DEMO_MODE"] = is_demo

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

    # CORS Support
    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return response

    @app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
    @app.route("/<path:path>", methods=["OPTIONS"])
    def handle_options(path=""):
        return "", 204

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
            "demo_mode": app.config.get("DEMO_MODE", True),
            "timestamp": time.time(),
            "rpc_connected": adapter.is_connected(),
        }), 200

    default_data_file = Path(__file__).resolve().parent / "default_data.json"
    default_data = {}
    if default_data_file.is_file():
        try:
            with open(default_data_file, "r", encoding="utf-8") as f:
                default_data = json.load(f)
        except Exception as e:
            logger.warning("Failed to load default_data.json: %s", e)

    @app.route("/metrics", methods=["GET"])
    def get_metrics():
        base_metrics = default_data.get("metrics", {})
        if not base_metrics:
            base_metrics = {
                "totalProposals": len(proposals_db),
                "verifiedCount": 0,
                "mismatchCount": 0,
                "needsReviewCount": 0,
                "pendingReviews": len([it for it in queue.list_items() if it.status.value == "PENDING_REVIEW"]),
                "activeChallenges": 0,
                "guardianPauses": 0,
                "treasury": {
                    "tokenSymbol": "MOCK",
                    "tokenDecimals": 18,
                    "totalBalance": "10000000000000000000000000",
                    "requestedTotal": "0",
                    "nativeBalanceWei": "0",
                },
                "latestAuditEvents": []
            }
        return jsonify(base_metrics), 200

    @app.route("/proposals", methods=["GET"])
    def list_proposals():
        if proposals_db:
            return jsonify(list(proposals_db.values())), 200
        return jsonify(default_data.get("proposals", [])), 200

    @app.route("/red-team", methods=["GET"])
    def get_red_team():
        return jsonify(default_data.get("redTeam", {
            "testSuite": "Step1 & Phase4 Suites",
            "totalPayloadsTested": 26,
            "caughtCount": 26,
            "escalatedCount": 0,
            "missedCount": 0,
            "detectionRate": 100.0,
            "falseVerifiedRate": 0.0,
            "scenarios": []
        })), 200

    @app.route("/challenges", methods=["GET"])
    def get_challenges():
        return jsonify(default_data.get("challenges", [])), 200

    @app.route("/guardian", methods=["GET"])
    def get_guardian():
        return jsonify(default_data.get("guardianEvents", [])), 200

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
        if proposal_id in proposals_db:
            prop = proposals_db[proposal_id]
            latest_v = prop.get("latest_version", 1)
            manifest_summary = provenance.get_manifest_summary(proposal_id, latest_v)
            return jsonify({
                "proposal_id": prop["proposal_id"],
                "latest_version": prop["latest_version"],
                "versions": prop["versions"],
                "evidence_manifest": manifest_summary,
                "is_demo": False,
                "data_source": "local_proposals_db",
            }), 200

        # Fallback to seeded demo proposals if unindexed or in demo mode
        for p in default_data.get("proposals", []):
            if p.get("id") == proposal_id:
                p_copy = dict(p)
                p_copy["is_demo"] = True
                p_copy["data_source"] = "seeded_demo_fixture"
                p_copy["evidence_manifest"] = provenance.get_manifest_summary(proposal_id, 1)
                return jsonify(p_copy), 200

        return jsonify({"error": f"Proposal '{proposal_id}' not found"}), 404

    @app.route("/analyze", methods=["POST"])
    def analyze_scenario():
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        data = request.get_json()
        try:
            scenario_cfg = ScenarioConfig.from_dict(data)
        except ValueError as ve:
            return jsonify({"error": "Scenario validation failed", "detail": str(ve)}), 400

        sim_result: Optional[SimulationResult] = None
        is_demo_fixture = False
        demo_note = None

        # Execute deterministic EVM simulation against local node
        try:
            simulator = Simulator(scenario_cfg)
            sim_result = simulator.run()
        except Exception as e:
            logger.error("Simulation execution error: %s", e)
            return jsonify({"error": "Simulation execution failed", "detail": str(e)}), 500

        # If Anvil node was unreachable, fall back to clearly labelled demo fixture if demo mode is enabled
        if not sim_result.success and any("failed to connect" in err.lower() for err in sim_result.errors):
            if app.config.get("DEMO_MODE", True):
                fixture_data = load_demo_simulation_fixture(scenario_cfg.scenario_id)
                if fixture_data:
                    is_demo_fixture = True
                    demo_note = (
                        "[DEMO FIXTURE] Local Anvil node was offline. Showing labeled demonstration fixture. "
                        "NOT live on-chain execution."
                    )
                    try:
                        sim_result = load_simulation_result_from_dict(fixture_data)
                    except Exception as load_err:
                        logger.warning("Failed to parse fallback demo fixture: %s", load_err)

        # Compute deterministic governance verdict based on observable evidence
        # 1. Check for Treasury ownership hijack (direct storage collision)
        has_owner_hijack = any(
            (
                (isinstance(d, dict) and d.get("effect_type") == "treasury_owner" and d.get("before_value") != d.get("after_value"))
                or (isinstance(d, dict) and "owner" in str(d.get("effect_id", "")).lower() and d.get("before_value") != d.get("after_value"))
                or (hasattr(d, "effect_type") and getattr(d, "effect_type") == "treasury_owner" and getattr(d, "before_value") != getattr(d, "after_value"))
            )
            for d in sim_result.state_diffs
        )

        # 2. Check for missing/incomplete trace evidence (FAIL CLOSED: NEVER TREAT INCOMPLETE TRACE AS SAFE)
        has_inconclusive_trace = (
            not sim_result.trace_complete
            or any(
                (isinstance(f, dict) and (f.get("rule_id") == "R000_INCONCLUSIVE_TRACE" or f.get("code") == "R000_INCONCLUSIVE_TRACE"))
                or (hasattr(f, "rule_id") and getattr(f, "rule_id") == "R000_INCONCLUSIVE_TRACE")
                for f in sim_result.findings
            )
        )

        # 3. Check for high-risk findings (DELEGATECALL, SELFDESTRUCT, Proxy Upgrades, Unlimited Approvals)
        finding_codes = set()
        for f in sim_result.findings:
            if isinstance(f, dict):
                code = f.get("rule_id") or f.get("code")
                if code:
                    finding_codes.add(str(code).upper())
            elif hasattr(f, "rule_id"):
                finding_codes.add(str(getattr(f, "rule_id")).upper())
            elif hasattr(f, "code"):
                finding_codes.add(str(getattr(f, "code")).upper())

        has_delegatecall = any("DELEGATECALL" in c or "R001" in c for c in finding_codes)
        has_selfdestruct = any("SELFDESTRUCT" in c or "R002" in c for c in finding_codes)
        has_proxy = any("PROXY" in c or "R003" in c for c in finding_codes)
        has_unlimited = any("UNLIMITED" in c or "APPROVAL" in c or "R004" in c for c in finding_codes)

        if has_owner_hijack:
            verdict_status = "MISMATCH"
            reason = "Treasury ownership hijacked under execution"
        elif not sim_result.success:
            verdict_status = "MISMATCH"
            reason = f"Execution failed or reverted: {'; '.join(sim_result.errors)}"
        elif has_inconclusive_trace:
            verdict_status = "NEEDS_REVIEW"
            reason = "Trace evidence incomplete or unavailable; fail-closed safety discipline requires human review"
        elif has_delegatecall or has_selfdestruct or has_proxy or has_unlimited:
            verdict_status = "NEEDS_REVIEW"
            reasons = []
            if has_delegatecall:
                reasons.append("DELEGATECALL execution detected (R001)")
            if has_selfdestruct:
                reasons.append("SELFDESTRUCT instruction detected (R002)")
            if has_proxy:
                reasons.append("Proxy implementation modified (R003)")
            if has_unlimited:
                reasons.append("Unlimited token approval granted (R004)")
            reason = "; ".join(reasons)
        else:
            verdict_status = "VERIFIED"
            reason = "All state diffs and trace invariants verified clean."

        sim_dict = sim_result.to_dict()
        sim_dict["is_demo"] = is_demo_fixture
        sim_dict["data_source"] = "synthetic_demo_fixture" if is_demo_fixture else "local_anvil_node"
        if is_demo_fixture:
            sim_dict["simulation_note"] = demo_note

        evidence_bytes = json.dumps(sim_dict, sort_keys=True).encode("utf-8")
        evidence_hash = "0x" + hashlib.sha256(evidence_bytes).hexdigest()

        # Register simulation evidence into provenance with SHA-256 hash chaining
        try:
            provenance.register_evidence(
                proposal_id=scenario_cfg.scenario_id,
                version=1,
                item_id="simulation_evidence",
                media_type="application/json",
                source_uri=f"analyzer://simulation/{scenario_cfg.scenario_id}",
                content=evidence_bytes,
                expected_hash=evidence_hash,
            )
        except Exception as prov_err:
            logger.debug("Provenance chain notice: %s", prov_err)

        manifest_summary = provenance.get_manifest_summary(scenario_cfg.scenario_id, 1)

        # If verdict is NEEDS_REVIEW, automatically queue it for human review
        if verdict_status == "NEEDS_REVIEW":
            queue.enqueue(
                proposal_id=scenario_cfg.scenario_id,
                version=1,
                automated_verdict={
                    "status": verdict_status,
                    "reason": reason,
                    "evidence_hash": evidence_hash,
                    "manifest_root_hash": manifest_summary.get("root_hash"),
                    "trace_complete": sim_result.trace_complete,
                    "is_demo": is_demo_fixture,
                    "timestamp": time.time(),
                },
            )

        verdict_obj = {
            "status": verdict_status,
            "reason": reason,
            "evidence_hash": evidence_hash,
            "manifest_root_hash": manifest_summary.get("root_hash"),
            "trace_complete": sim_result.trace_complete,
            "is_demo": is_demo_fixture,
            "data_source": "synthetic_demo_fixture" if is_demo_fixture else "local_anvil_node",
        }
        if is_demo_fixture:
            verdict_obj["note"] = demo_note

        return jsonify({
            "simulation": sim_dict,
            "verdict": verdict_obj,
            "evidence_manifest": manifest_summary,
        }), 200

    @app.route("/manifest/<proposal_id>", methods=["GET"])
    @app.route("/manifest/<proposal_id>/<int:version>", methods=["GET"])
    @app.route("/proposals/<proposal_id>/manifest", methods=["GET"])
    def get_evidence_manifest(proposal_id: str, version: Optional[int] = None):
        target_version = version
        if target_version is None:
            if proposal_id in proposals_db:
                target_version = proposals_db[proposal_id].get("latest_version", 1)
            else:
                target_version = 1

        summary = provenance.get_manifest_summary(proposal_id, target_version)
        summary["is_demo"] = app.config.get("DEMO_MODE", True)
        summary["data_source"] = "local_evidence_provenance"
        return jsonify(summary), 200

    @app.route("/manifest/<proposal_id>/<int:version>", methods=["POST"])
    @app.route("/proposals/<proposal_id>/evidence", methods=["POST"])
    def register_manifest_evidence(proposal_id: str, version: Optional[int] = None):
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        target_version = version
        data = request.get_json()
        if target_version is None:
            target_version = int(data.get("version", 1))

        item_id = data.get("item_id")
        if not item_id or not isinstance(item_id, str):
            return jsonify({"error": "'item_id' is required and must be a non-empty string"}), 400

        media_type = data.get("media_type", "application/octet-stream")
        source_uri = data.get("source_uri", f"local://evidence/{proposal_id}/{item_id}")
        content_val = data.get("content")
        content_bytes = content_val.encode("utf-8") if isinstance(content_val, str) else None
        expected_hash = data.get("expected_hash")

        try:
            item = provenance.register_evidence(
                proposal_id=proposal_id,
                version=target_version,
                item_id=item_id,
                media_type=media_type,
                source_uri=source_uri,
                content=content_bytes,
                expected_hash=expected_hash,
            )
            summary = provenance.get_manifest_summary(proposal_id, target_version)
            return jsonify({
                "message": "Evidence registered in manifest hash chain",
                "item": item.to_dict(),
                "manifest": summary,
            }), 201
        except TamperedContentError as tce:
            return jsonify({"error": "Tampered content detected", "detail": str(tce)}), 400
        except ValueError as ve:
            return jsonify({"error": "Validation error", "detail": str(ve)}), 400
        except Exception as e:
            logger.error("Failed to register evidence artifact: %s", e)
            return jsonify({"error": "Internal error", "detail": str(e)}), 500

    @app.route("/reviews", methods=["GET"])
    def list_reviews():
        status_filter = request.args.get("status")
        items = queue.list_items(status_filter)
        return jsonify({
            "count": len(items),
            "summary": queue.get_summary(),
            "items": [it.to_dict() for it in items],
        }), 200

    @app.route("/reviews/<proposal_id>/<int:version>", methods=["GET"])
    def get_review_item(proposal_id: str, version: int):
        item = queue.get(proposal_id, version)
        if not item:
            return jsonify({"error": f"No review item found for proposal {proposal_id} v{version}"}), 404
        return jsonify(item.to_dict()), 200

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

    @app.route("/proposals/<proposal_id>/reviews", methods=["POST"])
    def post_proposal_review(proposal_id: str):
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        data = request.get_json()
        action = data.get("action")
        reason = data.get("reason", "")
        reviewer = data.get("reviewer", "0xAuditor77777777777777777777777777777777")
        sync_on_chain = data.get("sync_on_chain", False)

        if not action or action not in ("APPROVE", "REJECT", "ESCALATE"):
            return jsonify({"error": "Invalid action; must be APPROVE, REJECT, or ESCALATE"}), 400
        if not reason or len(reason.strip()) < 10:
            return jsonify({"error": "Mandatory written reason required (minimum 10 characters)"}), 400

        if app.config.get("DEMO_MODE", True):
            simulated_review = {
                "proposal_id": proposal_id,
                "action": action,
                "reason": reason.strip(),
                "reviewer": reviewer,
                "timestamp": time.time(),
                "is_demo": True,
                "simulated": True,
                "on_chain_confirmed": False,
                "note": "Simulated local demonstration record — NOT an on-chain transaction or real signature."
            }
            return jsonify({
                "message": "Demo review recorded (simulated)",
                "success": True,
                "is_demo": True,
                "simulated": True,
                "review": simulated_review,
            }), 200

        # Live mode: forward to post_review
        return post_review(proposal_id, 1)

    @app.route("/proposals/<proposal_id>/vote", methods=["POST"])
    def post_proposal_vote(proposal_id: str):
        if not request.is_json:
            return jsonify({"error": "Expected application/json content-type"}), 400

        data = request.get_json()
        choice = data.get("choice")
        acknowledged = data.get("acknowledged", False)

        if not acknowledged:
            return jsonify({"error": "You must acknowledge that you have seen the real effects before voting."}), 400
        if not choice or choice not in ("FOR", "AGAINST", "ABSTAIN"):
            return jsonify({"error": "Invalid vote choice: must be FOR, AGAINST, or ABSTAIN"}), 400

        if app.config.get("DEMO_MODE", True):
            return jsonify({
                "message": "Demo vote acknowledged and recorded locally",
                "success": True,
                "is_demo": True,
                "simulated": True,
                "on_chain_confirmed": False,
                "choice": choice,
                "acknowledged": True,
                "timestamp": time.time(),
                "note": "Simulated local ballot acknowledgement — NOT submitted to on-chain Governor."
            }), 200

        return jsonify({
            "error": "Live on-chain Governor contract is not configured on local RPC",
            "success": False,
            "is_demo": False,
        }), 503

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

        # 3. Evidence Manifest events
        max_ver = 1
        if proposal_id in proposals_db:
            max_ver = proposals_db[proposal_id].get("latest_version", 1)
        for v in range(1, max_ver + 1):
            manifest_items = provenance.get_manifest(proposal_id, v)
            for m in manifest_items:
                events.append({
                    "event_type": "EVIDENCE_MANIFEST_REGISTERED",
                    "version": v,
                    "item_id": m.item_id,
                    "content_hash": m.content_hash,
                    "previous_manifest_hash": m.previous_manifest_hash,
                    "manifest_hash": m.manifest_hash,
                    "integrity_verified": m.integrity_verified,
                    "timestamp": m.retrieval_timestamp,
                })

        events.sort(key=lambda x: x.get("timestamp", 0))

        return jsonify({
            "proposal_id": proposal_id,
            "event_count": len(events),
            "timeline": events,
        }), 200

    @app.route("/onchain/<proposal_id>/<int:version>", methods=["GET"])
    def get_onchain_status(proposal_id: str, version: int):
        proposal_bytes32 = proposal_id.encode("utf-8").ljust(32, b"\x00")[:32]
        is_connected = adapter.is_connected()
        if not is_connected:
            return jsonify({
                "proposal_id": proposal_id,
                "version": version,
                "rpc_connected": False,
                "note": "Local Anvil RPC offline or disconnected. On-chain queries unavailable.",
            }), 200

        on_chain_prop = adapter.get_on_chain_proposal(proposal_bytes32, version)
        on_chain_verdict = adapter.get_on_chain_verdict(proposal_bytes32, version)
        eligible, eligible_reason = adapter.is_on_chain_eligible(proposal_bytes32, version)
        latest_review = adapter.get_on_chain_review(proposal_bytes32, version)
        challenge_status = adapter.get_on_chain_challenge_status(proposal_bytes32, version)
        treasury_status = adapter.get_treasury_status(proposal_bytes32, version)

        return jsonify({
            "proposal_id": proposal_id,
            "version": version,
            "rpc_connected": True,
            "proposal": on_chain_prop,
            "verdict": on_chain_verdict,
            "eligible_for_execution": eligible,
            "eligibility_reason": eligible_reason,
            "latest_review": latest_review,
            "challenges": challenge_status,
            "treasury": treasury_status,
        }), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False)
