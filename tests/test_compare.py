"""
tests/test_compare.py
=====================
Comprehensive tests for Veritas Gate Phase 3 deterministic claims comparison engine.
"""

import json
from pathlib import Path
import pytest

from analyzer import (
    Verdict,
    compare,
    get_forbid_ownership_claims,
    get_honest_5m_grant_claims,
    load_claims_from_json,
    load_simulation_result_from_json,
    REASON_ALL_CLAIMS_VERIFIED,
    REASON_CLAIMS_AMBIGUOUS,
    REASON_CLAIMS_UNSUPPORTED_TYPE,
    REASON_FORBIDDEN_EFFECT_OBSERVED,
    REASON_OWNERSHIP_COLLISION_DETECTED,
    REASON_PROVEN_TRANSFER_AMOUNT_MISMATCH,
    REASON_PROVEN_TRANSFER_MISSING,
    REASON_PROVEN_TRANSFER_RECIPIENT_MISMATCH,
    REASON_REQUIRED_EVIDENCE_MISSING,
    REASON_RISKY_OPERATION_FLAG,
    REASON_SIMULATION_ERRORS,
    REASON_SIMULATION_FAILED,
    REASON_TRACE_INCOMPLETE,
    REASON_UNCLAIMED_MATERIAL_TRANSFER,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def read_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: Honest 5M grant with complete clean evidence => VERIFIED
# ---------------------------------------------------------------------------
def test_honest_5m_grant_verified():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_honest.json")

    result = compare(claims_json, sim_json)
    assert result.verdict == Verdict.VERIFIED
    assert result.reason_code == REASON_ALL_CLAIMS_VERIFIED
    assert "claim-001-grant-distribution" in result.matched_claims
    assert "claim-002-ownership-preserved" in result.matched_claims
    assert len(result.unclaimed_effects) == 0


# ---------------------------------------------------------------------------
# Test 2: Ownership change contradicting claims => MISMATCH
# ---------------------------------------------------------------------------
def test_ownership_change_mismatch():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_malicious.json")

    result = compare(claims_json, sim_json)
    assert result.verdict == Verdict.MISMATCH
    # Either ownership collision or forbidden effect observed
    assert result.reason_code in (
        REASON_OWNERSHIP_COLLISION_DETECTED,
        REASON_FORBIDDEN_EFFECT_OBSERVED,
    )
    assert len(result.evidence_references) > 0
    ref = result.evidence_references[0]
    assert ref.source == "state_diff"
    assert "slot_0" in ref.identifier


# ---------------------------------------------------------------------------
# Test 3: Proven unclaimed material transfer => MISMATCH
# ---------------------------------------------------------------------------
def test_unclaimed_material_transfer_mismatch():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_unexpected_transfer.json")

    result = compare(claims_json, sim_json)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code == REASON_UNCLAIMED_MATERIAL_TRANSFER
    assert len(result.unclaimed_effects) == 1
    unclaimed = result.unclaimed_effects[0]
    assert unclaimed["amount"] == "1000000000000000000000000"
    assert "0x9999" in unclaimed["to"]


# ---------------------------------------------------------------------------
# Test 4: Delegatecall risk without proven mismatch => NEEDS_REVIEW
# ---------------------------------------------------------------------------
def test_delegatecall_risk_needs_review():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_risky_delegatecall.json")

    result = compare(claims_json, sim_json)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_RISKY_OPERATION_FLAG
    assert any("DELEGATECALL" in f["code"] for f in result.findings)


# ---------------------------------------------------------------------------
# Test 5: Ambiguous claims => NEEDS_REVIEW
# ---------------------------------------------------------------------------
def test_ambiguous_claims_needs_review():
    claims_json = read_fixture("claims_ambiguous.json")
    sim_json = read_fixture("simulation_honest.json")

    result = compare(claims_json, sim_json)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_CLAIMS_AMBIGUOUS
    assert result.verdict != Verdict.VERIFIED


# ---------------------------------------------------------------------------
# Test 6: Missing / incomplete trace => never VERIFIED (NEEDS_REVIEW)
# ---------------------------------------------------------------------------
def test_incomplete_trace_never_verified():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_incomplete_trace.json")

    result = compare(claims_json, sim_json)
    assert result.verdict != Verdict.VERIFIED
    assert result.verdict == Verdict.NEEDS_REVIEW
    # Incomplete trace or errors reported by tracer
    assert result.reason_code in (REASON_TRACE_INCOMPLETE, REASON_SIMULATION_ERRORS)


# ---------------------------------------------------------------------------
# Test 7: Reverted execution => never VERIFIED (NEEDS_REVIEW)
# ---------------------------------------------------------------------------
def test_reverted_execution_never_verified():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_reverted.json")

    result = compare(claims_json, sim_json)
    assert result.verdict != Verdict.VERIFIED
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_SIMULATION_FAILED


# ---------------------------------------------------------------------------
# Test 8: Missing required evidence fields in simulation => never VERIFIED
# ---------------------------------------------------------------------------
def test_missing_simulation_fields_fails_closed():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_missing_fields.json")

    result = compare(claims_json, sim_json)
    assert result.verdict != Verdict.VERIFIED
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_REQUIRED_EVIDENCE_MISSING


# ---------------------------------------------------------------------------
# Test 9: Unsupported claim type => NEEDS_REVIEW
# ---------------------------------------------------------------------------
def test_unsupported_claim_type_rejected():
    claims_json = read_fixture("claims_unsupported_type.json")
    sim_json = read_fixture("simulation_honest.json")

    result = compare(claims_json, sim_json)
    assert result.verdict != Verdict.VERIFIED
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_CLAIMS_UNSUPPORTED_TYPE


# ---------------------------------------------------------------------------
# Test 10: Token transfer amount mismatch => MISMATCH
# ---------------------------------------------------------------------------
def test_token_transfer_amount_mismatch():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    # Mutate simulation log to transfer 4M instead of 5M
    sim_data = json.loads(read_fixture("simulation_honest.json"))
    sim_data["logs"][0]["decoded"]["value"] = "4000000000000000000000000"
    sim_data["logs"][0]["data"] = "0x00000000000000000000000000000000000000000000003504ae67f6262000"

    result = compare(claims_json, sim_data)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code == REASON_PROVEN_TRANSFER_AMOUNT_MISMATCH


# ---------------------------------------------------------------------------
# Test 11: Token transfer recipient mismatch => MISMATCH
# ---------------------------------------------------------------------------
def test_token_transfer_recipient_mismatch():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_data = json.loads(read_fixture("simulation_honest.json"))
    wrong_recipient = "0x8888888888888888888888888888888888888888"
    sim_data["logs"][0]["decoded"]["to"] = wrong_recipient
    sim_data["logs"][0]["topics"][2] = "0x0000000000000000000000008888888888888888888888888888888888888888"

    result = compare(claims_json, sim_data)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code == REASON_PROVEN_TRANSFER_RECIPIENT_MISMATCH


# ---------------------------------------------------------------------------
# Test 12: Missing claimed token transfer => MISMATCH
# ---------------------------------------------------------------------------
def test_missing_claimed_token_transfer():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_data = json.loads(read_fixture("simulation_honest.json"))
    sim_data["logs"] = []  # No logs emitted!

    result = compare(claims_json, sim_data)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code == REASON_PROVEN_TRANSFER_MISSING


# ---------------------------------------------------------------------------
# Test 13: Deterministic Precedence: Proven Mismatch Overrides Risky Delegatecall Flag
# ---------------------------------------------------------------------------
def test_precedence_proven_mismatch_overrides_risky_flag():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    # simulation_malicious has BOTH:
    # 1. Slot 0 ownership collision (proven mismatch)
    # 2. DELEGATECALL_DETECTED finding (risky flag)
    sim_json = read_fixture("simulation_malicious.json")

    result = compare(claims_json, sim_json)
    # By deterministic precedence rule 1, proven material mismatch MUST yield MISMATCH!
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code in (
        REASON_OWNERSHIP_COLLISION_DETECTED,
        REASON_FORBIDDEN_EFFECT_OBSERVED,
    )


# ---------------------------------------------------------------------------
# Test 14: Deterministic Precedence: Proven Mismatch Overrides Incomplete Trace
# ---------------------------------------------------------------------------
def test_precedence_proven_mismatch_overrides_incomplete_trace():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_data = json.loads(read_fixture("simulation_malicious.json"))
    # Mark trace as incomplete
    sim_data["trace_complete"] = False

    result = compare(claims_json, sim_data)
    # Proven ownership violation is proven by the diff; proven mismatch overrides uncertainty!
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code in (
        REASON_OWNERSHIP_COLLISION_DETECTED,
        REASON_FORBIDDEN_EFFECT_OBSERVED,
    )


# ---------------------------------------------------------------------------
# Test 15: Forbid Ownership Claims against Honest & Malicious
# ---------------------------------------------------------------------------
def test_forbid_ownership_claims_verdicts():
    claims_json = read_fixture("claims_forbid_ownership.json")

    honest_sim = read_fixture("simulation_honest.json")
    result_honest = compare(claims_json, honest_sim)
    assert result_honest.verdict == Verdict.VERIFIED

    malicious_sim = read_fixture("simulation_malicious.json")
    result_malicious = compare(claims_json, malicious_sim)
    assert result_malicious.verdict == Verdict.MISMATCH
    assert result_malicious.reason_code == REASON_FORBIDDEN_EFFECT_OBSERVED


# ---------------------------------------------------------------------------
# Test 16: Input Type Equivalence (objects vs dicts vs JSON strings)
# ---------------------------------------------------------------------------
def test_input_type_equivalence():
    claims_str = read_fixture("claims_honest_5m_grant.json")
    sim_str = read_fixture("simulation_honest.json")

    claims_dict = json.loads(claims_str)
    sim_dict = json.loads(sim_str)

    claims_obj = load_claims_from_json(claims_str)
    sim_obj = load_simulation_result_from_json(sim_str)

    res_str = compare(claims_str, sim_str)
    res_dict = compare(claims_dict, sim_dict)
    res_obj = compare(claims_obj, sim_obj)

    assert res_str.verdict == res_dict.verdict == res_obj.verdict == Verdict.VERIFIED
    assert res_str.reason_code == res_dict.reason_code == res_obj.reason_code
    assert res_str.to_dict() == res_dict.to_dict() == res_obj.to_dict()


# ---------------------------------------------------------------------------
# Test 17: Native Transfer Claim Handling
# ---------------------------------------------------------------------------
def test_native_transfer_matching_and_mismatch():
    token = "0x4444444444444444444444444444444444444444"
    recipient = "0x3333333333333333333333333333333333333333"

    claims_data = {
        "schema_version": "veritas-claims-v1.0",
        "proposal_id": "prop-native-transfer",
        "title": "Native ETH Grant",
        "claims": [
            {
                "claim_id": "claim-eth-1",
                "type": "NATIVE_TRANSFER",
                "recipient": recipient,
                "amount": "1000000000000000000",
                "unit": "wei",
            }
        ],
    }

    sim_data = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "scenario-native-transfer",
        "chain_id": 1,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [],
        "logs": [],
        "findings": [],
        "errors": [],
        "native_transfers": [
            {
                "from": "0x1111111111111111111111111111111111111111",
                "to": recipient,
                "value": 1000000000000000000,
                "call_index": 0,
            }
        ],
    }

    res_match = compare(claims_data, sim_data)
    assert res_match.verdict == Verdict.VERIFIED
    assert "claim-eth-1" in res_match.matched_claims

    # Mismatch amount
    sim_data_bad = json.loads(json.dumps(sim_data))
    sim_data_bad["native_transfers"][0]["value"] = 500000000000000000
    res_mismatch = compare(claims_data, sim_data_bad)
    assert res_mismatch.verdict == Verdict.MISMATCH


# ---------------------------------------------------------------------------
# Test 18: Allowance Expectation & Forbidden Allowance Mutation
# ---------------------------------------------------------------------------
def test_allowance_expectation_and_forbidden_mutation():
    token = "0x4444444444444444444444444444444444444444"
    treasury = "0x1111111111111111111111111111111111111111"
    spender = "0x7777777777777777777777777777777777777777"

    claims_allowance = {
        "schema_version": "veritas-claims-v1.0",
        "proposal_id": "prop-allowance",
        "title": "Approval Test",
        "claims": [
            {
                "claim_id": "claim-allowance-1",
                "type": "ALLOWANCE_EXPECTATION",
                "token": token,
                "owner": treasury,
                "spender": spender,
                "expected_allowance": "1000000",
                "unit": "raw",
            }
        ],
    }

    # Simulation emitting approval
    sim_approval = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "scenario-approval",
        "chain_id": 1,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [],
        "logs": [
            {
                "log_index": 0,
                "address": token,
                "event_name": "Approval",
                "decoded": {
                    "owner": treasury,
                    "spender": spender,
                    "value": "1000000",
                },
                "topics": [],
                "data": "0x0",
            }
        ],
        "findings": [],
        "errors": [],
    }

    res_app = compare(claims_allowance, sim_approval)
    assert res_app.verdict == Verdict.VERIFIED

    # Claims forbidding allowance mutation
    claims_forbid_app = {
        "schema_version": "veritas-claims-v1.0",
        "proposal_id": "prop-forbid-app",
        "title": "Forbid Allowance Mutation",
        "claims": [
            {
                "claim_id": "claim-forbid-app-1",
                "type": "FORBIDDEN_EFFECT",
                "effect_type": "ALLOWANCE_MUTATION",
                "target": token,
                "unit": "none",
            }
        ],
    }

    res_forbid = compare(claims_forbid_app, sim_approval)
    assert res_forbid.verdict == Verdict.MISMATCH
    assert res_forbid.reason_code == REASON_FORBIDDEN_EFFECT_OBSERVED


# ---------------------------------------------------------------------------
# Test 19: Unclaimed Storage Mutation on Treasury => MISMATCH
# ---------------------------------------------------------------------------
def test_unclaimed_treasury_storage_mutation():
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_data = json.loads(read_fixture("simulation_honest.json"))
    # Add an unclaimed storage mutation on Treasury at slot 5
    sim_data["state_diffs"] = [
        {
            "address": "0x1111111111111111111111111111111111111111",
            "slot": "0x5",
            "slot_name": "unknown_var",
            "before": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "after": "0x0000000000000000000000000000000000000000000000000000000000000001",
        }
    ]

    res = compare(claims_json, sim_data)
    assert res.verdict == Verdict.MISMATCH

