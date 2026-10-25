"""
tests/test_phase3_cases.py
==========================
Dedicated comprehensive tests for Veritas Gate Phase 3 Claims & Verdict Engine:
1. Honest proposal scenarios: verified against Phase 2 SimulationResult objects and raw logs.
2. Malicious proposal scenarios: proven mismatches (ownership hijack, exact 1-wei amount
   differences, recipient mismatch, forbidden effects, unclaimed transfers).
3. Incomplete evidence and risky flags: missing trace, missing fields, missing state data,
   reverts, simulation errors, and Phase 2 risk rules (R001-R004, R000).
4. Strict fail-closed integer arithmetic: ensures missing values never count as zero or imply safety.
"""

import json
from pathlib import Path
import pytest

from analyzer import (
    ClaimType,
    ComparisonResult,
    EffectDiff,
    EffectType,
    EvidenceReference,
    ForbiddenEffectClaim,
    ForbiddenEffectType,
    NativeTransferClaim,
    ObservedApproval,
    ObservedFinding,
    ObservedNativeTransfer,
    ObservedStorageDiff,
    ObservedTokenTransfer,
    OwnershipExpectationClaim,
    OwnershipState,
    ProposalClaims,
    SimulationResult,
    TokenTransferClaim,
    Verdict,
    VerdictEngineConfig,
    compare,
    get_forbid_ownership_claims,
    get_honest_5m_grant_claims,
    load_claims_from_dict,
    load_claims_from_json,
    load_simulation_result_from_dict,
    REASON_ALL_CLAIMS_VERIFIED,
    REASON_ALLOWANCE_VIOLATION,
    REASON_CLAIMS_AMBIGUOUS,
    REASON_CLAIMS_UNSUPPORTED_TYPE,
    REASON_FORBIDDEN_EFFECT_OBSERVED,
    REASON_OWNERSHIP_COLLISION_DETECTED,
    REASON_PROVEN_NATIVE_TRANSFER_AMOUNT_MISMATCH,
    REASON_PROVEN_NATIVE_TRANSFER_MISSING,
    REASON_PROVEN_TRANSFER_AMOUNT_MISMATCH,
    REASON_PROVEN_TRANSFER_MISSING,
    REASON_PROVEN_TRANSFER_RECIPIENT_MISMATCH,
    REASON_REQUIRED_EVIDENCE_MISSING,
    REASON_RISKY_OPERATION_FLAG,
    REASON_SIMULATION_ERRORS,
    REASON_SIMULATION_FAILED,
    REASON_TRACE_INCOMPLETE,
    REASON_UNCLAIMED_MATERIAL_TRANSFER,
    REASON_UNCLAIMED_STATE_MUTATION,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

TOKEN_ADDR = "0x4444444444444444444444444444444444444444"
RECIPIENT_ADDR = "0x3333333333333333333333333333333333333333"
TREASURY_ADDR = "0x1111111111111111111111111111111111111111"
ATTACKER_ADDR = "0x9999999999999999999999999999999999999999"
ORIGINAL_OWNER = "0x2222222222222222222222222222222222222222"
GRANT_5M = 5_000_000 * 10**18


# ===========================================================================
# 1. Honest Scenarios (Clean Complete Evidence -> VERIFIED)
# ===========================================================================

def test_honest_proposal_with_phase2_simulation_result():
    """Verify clean match using direct Phase 2 SimulationResult and EffectDiff objects."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    sim = SimulationResult(
        scenario_id="scenario-honest-grant",
        chain_id=31337,
        simulation_mode="local_evm",
        success=True,
        trace_complete=True,
        state_diffs=[
            EffectDiff(
                effect_id=f"token_balance:{TOKEN_ADDR}:{TREASURY_ADDR}",
                effect_type=EffectType.TOKEN_BALANCE.value,
                address=TREASURY_ADDR,
                token_address=TOKEN_ADDR,
                before_value=10_000_000 * 10**18,
                after_value=5_000_000 * 10**18,
                delta=-GRANT_5M,
                evidence="ERC20.balanceOf",
            ),
            EffectDiff(
                effect_id=f"token_balance:{TOKEN_ADDR}:{RECIPIENT_ADDR}",
                effect_type=EffectType.TOKEN_BALANCE.value,
                address=RECIPIENT_ADDR,
                token_address=TOKEN_ADDR,
                before_value=0,
                after_value=GRANT_5M,
                delta=GRANT_5M,
                evidence="ERC20.balanceOf",
            ),
            EffectDiff(
                effect_id=f"treasury_owner:{TREASURY_ADDR}",
                effect_type=EffectType.TREASURY_OWNER.value,
                address=TREASURY_ADDR,
                token_address=None,
                before_value=ORIGINAL_OWNER,
                after_value=ORIGINAL_OWNER,  # Unchanged!
                delta=None,
                evidence="Treasury.owner()",
            ),
        ],
        logs=[
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": str(GRANT_5M),
                },
            }
        ],
        findings=[],
        errors=[],
    )

    result = compare(claims, sim)
    assert result.verdict == Verdict.VERIFIED
    assert result.reason_code == REASON_ALL_CLAIMS_VERIFIED
    assert len(result.unmatched_claims) == 0
    assert len(result.unclaimed_effects) == 0
    assert "claim-001-grant-distribution" in result.matched_claims
    assert "claim-002-ownership-preserved" in result.matched_claims


def test_honest_native_transfer_exact_wei():
    """Verify native ETH transfer with exact wei integer matching."""
    one_eth = 1_000_000_000_000_000_000
    claims = ProposalClaims(
        schema_version="veritas-claims-v1.0",
        proposal_id="prop-eth-grant",
        title="1 ETH Ecosystem Grant",
        target_treasury=TREASURY_ADDR,
        claims=[
            NativeTransferClaim(
                claim_id="claim-eth-1",
                type=ClaimType.NATIVE_TRANSFER,
                recipient=RECIPIENT_ADDR,
                amount=one_eth,
                unit="wei",
                sender=TREASURY_ADDR,
            ),
            OwnershipExpectationClaim(
                claim_id="claim-owner-1",
                type=ClaimType.OWNERSHIP_EXPECTATION,
                contract=TREASURY_ADDR,
                expected_state=OwnershipState.UNCHANGED,
                unit="address",
            ),
        ],
    )

    sim = SimulationResult(
        scenario_id="scenario-eth-grant",
        chain_id=1,
        simulation_mode="local_evm",
        success=True,
        trace_complete=True,
        state_diffs=[],
        logs=[],
        findings=[],
        errors=[],
        raw_data={
            "native_transfers": [
                {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": one_eth,
                    "call_index": 0,
                }
            ]
        },
    )

    result = compare(claims, sim)
    assert result.verdict == Verdict.VERIFIED
    assert result.reason_code == REASON_ALL_CLAIMS_VERIFIED


def test_honest_hex_amount_claims_support():
    """Verify claims with 0x-prefixed hex integer amount strings parse and match cleanly."""
    raw_claims = {
        "schema_version": "veritas-claims-v1.0",
        "proposal_id": "prop-hex-amount",
        "title": "Hex Grant Amount",
        "claims": [
            {
                "claim_id": "c-hex",
                "type": "TOKEN_TRANSFER",
                "token": TOKEN_ADDR,
                "recipient": RECIPIENT_ADDR,
                "amount": hex(GRANT_5M),  # 0x-prefixed hex string
                "unit": "raw_tokens",
            }
        ],
    }
    claims = load_claims_from_dict(raw_claims)
    assert claims.claims[0].amount == GRANT_5M

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-hex",
        "chain_id": 1,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [],
        "logs": [
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": str(GRANT_5M),
                },
            }
        ],
        "findings": [],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.VERIFIED


# ===========================================================================
# 2. Malicious Scenarios (Proven Material Mismatch -> MISMATCH)
# ===========================================================================

def test_malicious_ownership_hijack_via_effect_diff():
    """Verify ownership collision detection when using Phase 2 EffectDiff format."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    # Simulation where Treasury owner changed to attacker
    sim = SimulationResult(
        scenario_id="scenario-malicious-hijack",
        chain_id=31337,
        simulation_mode="local_evm",
        success=True,
        trace_complete=True,
        state_diffs=[
            EffectDiff(
                effect_id=f"treasury_owner:{TREASURY_ADDR}",
                effect_type=EffectType.TREASURY_OWNER.value,
                address=TREASURY_ADDR,
                token_address=None,
                before_value=ORIGINAL_OWNER,
                after_value=ATTACKER_ADDR,
                delta=None,
                evidence="Treasury.owner() / eth_getStorageAt:0x0",
            ),
        ],
        logs=[
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": str(GRANT_5M),
                },
            }
        ],
        findings=[],
        errors=[],
    )

    result = compare(claims, sim)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code in (
        REASON_OWNERSHIP_COLLISION_DETECTED,
        REASON_FORBIDDEN_EFFECT_OBSERVED,
    )
    assert len(result.evidence_references) > 0


def test_exact_integer_1_wei_difference_mismatch():
    """Prove that uint256 comparisons are strictly exact with zero float rounding."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    # 1 wei less than claimed: 4999999999999999999999999
    subtle_stolen_wei = GRANT_5M - 1

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-subtle-theft",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [],
        "logs": [
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": str(subtle_stolen_wei),
                },
            }
        ],
        "findings": [],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code == REASON_PROVEN_TRANSFER_AMOUNT_MISMATCH


def test_malicious_recipient_mismatch():
    """Verify mismatch when tokens are routed to attacker instead of intended recipient."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-wrong-recipient",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [],
        "logs": [
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": ATTACKER_ADDR,
                    "value": str(GRANT_5M),
                },
            }
        ],
        "findings": [],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code == REASON_PROVEN_TRANSFER_RECIPIENT_MISMATCH


def test_forbidden_unapproved_transfer_observed():
    """Verify ForbiddenEffectType.UNAPPROVED_TRANSFER detects unapproved extra transfers."""
    claims = get_forbid_ownership_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-unapproved-transfer",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [],
        "logs": [
            # Legitimate transfer
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": str(GRANT_5M),
                },
            },
            # Forbidden unapproved second transfer to attacker
            {
                "log_index": 1,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": ATTACKER_ADDR,
                    "value": "1000000000000000000",
                },
            },
        ],
        "findings": [],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.MISMATCH
    assert result.reason_code in (
        REASON_FORBIDDEN_EFFECT_OBSERVED,
        REASON_UNCLAIMED_MATERIAL_TRANSFER,
    )


def test_precedence_proven_mismatch_overrides_all_risky_findings():
    """
    Determinism Precedence Rule 1:
    Even when multiple risky findings (R001, R002, R003) exist, a proven material
    mismatch MUST result in MISMATCH (not NEEDS_REVIEW).
    """
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-attack-with-flags",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [
            {
                "address": TREASURY_ADDR,
                "slot": "0x0",
                "slot_name": "owner",
                "before": ORIGINAL_OWNER,
                "after": ATTACKER_ADDR,
            }
        ],
        "logs": [],
        "findings": [
            {"rule_id": "R001_DELEGATECALL", "severity": "HIGH", "explanation": "Delegatecall used"},
            {"rule_id": "R002_SELFDESTRUCT", "severity": "CRITICAL", "explanation": "Selfdestruct used"},
        ],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.MISMATCH
    assert result.verdict != Verdict.NEEDS_REVIEW


# ===========================================================================
# 3. Incomplete Evidence & Risky Flags (NEEDS_REVIEW)
# ===========================================================================

def test_missing_data_never_implies_safety():
    """State diff with missing before/after values must NEVER imply safety."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    # State diff where before_value is None (could not query baseline state)
    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-missing-state",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": True,
        "state_diffs": [
            {
                "address": TREASURY_ADDR,
                "slot": "0x0",
                "slot_name": "owner",
                "before": None,  # MISSING!
                "after": ORIGINAL_OWNER,
            }
        ],
        "logs": [
            {
                "log_index": 0,
                "address": TOKEN_ADDR,
                "event_name": "Transfer",
                "decoded": {
                    "from": TREASURY_ADDR,
                    "to": RECIPIENT_ADDR,
                    "value": str(GRANT_5M),
                },
            }
        ],
        "findings": [],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_REQUIRED_EVIDENCE_MISSING
    assert result.verdict != Verdict.VERIFIED


def test_phase2_rule_findings_trigger_needs_review():
    """Verify Phase 2 rule finding codes (R001, R002, R003, R004, R000) trigger NEEDS_REVIEW."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    rules_to_test = [
        ("R001_DELEGATECALL", "HIGH"),
        ("R002_SELFDESTRUCT", "CRITICAL"),
        ("R003_PROXY_UPGRADE", "MEDIUM"),
        ("R004_UNLIMITED_APPROVAL", "MEDIUM"),
        ("R000_INCONCLUSIVE_TRACE", "MEDIUM"),
    ]

    for rule_code, severity in rules_to_test:
        sim = {
            "schema_version": "veritas-simulation-v1.0",
            "scenario_id": f"sim-rule-{rule_code}",
            "chain_id": 31337,
            "simulation_mode": "local_evm",
            "success": True,
            "trace_complete": True,
            "state_diffs": [],
            "logs": [
                {
                    "log_index": 0,
                    "address": TOKEN_ADDR,
                    "event_name": "Transfer",
                    "decoded": {
                        "from": TREASURY_ADDR,
                        "to": RECIPIENT_ADDR,
                        "value": str(GRANT_5M),
                    },
                }
            ],
            "findings": [
                {
                    "rule_id": rule_code,
                    "code": rule_code,
                    "severity": severity,
                    "explanation": f"Finding triggered by {rule_code}",
                }
            ],
            "errors": [],
        }

        result = compare(claims, sim)
        assert result.verdict == Verdict.NEEDS_REVIEW, f"Expected NEEDS_REVIEW for {rule_code}"
        assert result.reason_code == REASON_RISKY_OPERATION_FLAG
        assert any(rule_code in str(f) for f in result.findings)


def test_missing_trace_with_missing_transfer_is_needs_review():
    """
    If trace is incomplete and claimed transfer was not observed, fail-closed
    discipline dictates NEEDS_REVIEW (incomplete evidence), not MISMATCH.
    """
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-truncated",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "trace_complete": False,  # Truncated trace!
        "state_diffs": [],
        "logs": [],  # No logs captured because trace truncated
        "findings": [],
        "errors": [],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_TRACE_INCOMPLETE


def test_simulation_reverted_is_needs_review():
    """Reverted simulation must never be verified."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-revert",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": False,  # Reverted!
        "trace_complete": True,
        "state_diffs": [],
        "logs": [],
        "findings": [],
        "errors": ["Transaction execution reverted: EvmError: Revert"],
    }

    result = compare(claims, sim)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_SIMULATION_FAILED


def test_missing_simulation_fields_rejected():
    """Missing required top-level schema fields must trigger NEEDS_REVIEW."""
    claims = get_honest_5m_grant_claims(TOKEN_ADDR, RECIPIENT_ADDR, TREASURY_ADDR, GRANT_5M)

    # Missing "trace_complete" and "state_diffs"
    incomplete_sim = {
        "schema_version": "veritas-simulation-v1.0",
        "scenario_id": "sim-missing-fields",
        "chain_id": 31337,
        "simulation_mode": "local_evm",
        "success": True,
        "logs": [],
        "findings": [],
        "errors": [],
    }

    result = compare(claims, incomplete_sim)
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason_code == REASON_REQUIRED_EVIDENCE_MISSING
