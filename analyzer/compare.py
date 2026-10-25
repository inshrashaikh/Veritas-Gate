"""
analyzer/compare.py
===================
Deterministic Claims Comparison and Verdict Engine for Veritas Gate Phase 3.

Compares structured proposal claims against observed execution effects from EVM simulation.
Returns exactly one verdict: VERIFIED, MISMATCH, or NEEDS_REVIEW.

Precedence Rules:
1. Proven material mismatch => MISMATCH
   (Reliable evidence proves a claimed effect was violated, an unclaimed material effect
   occurred, an ownership collision took place, or a forbidden effect was observed).
2. Otherwise, uncertainty or risky flags => NEEDS_REVIEW
   (Ambiguous claims, configured risky trace flags like delegatecall, incomplete trace,
   missing required evidence, or reverted execution).
3. VERIFIED only when all required effects match, no unclaimed material effects are observed,
   required evidence is complete, and no risky trace flag exists.

Safety Discipline:
- Fail-closed: missing, incomplete, malformed, or unsupported evidence never yields VERIFIED.
- Never infers safety from missing logs, missing state diffs, or absent trace data.
- Never uses an LLM. Purely deterministic and reproducible.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from .claims import (
    AllowanceExpectationClaim,
    BaseClaim,
    ClaimsValidationError,
    ClaimType,
    ForbiddenEffectClaim,
    ForbiddenEffectType,
    NativeTransferClaim,
    OwnershipExpectationClaim,
    OwnershipState,
    ProposalClaims,
    TokenTransferClaim,
    load_claims_from_dict,
    load_claims_from_json,
    normalize_address,
)
from .schemas import (
    DEFAULT_SIMULATION_SCHEMA_VERSION,
    ObservedApproval,
    ObservedFinding,
    ObservedNativeTransfer,
    ObservedStorageDiff,
    ObservedTokenTransfer,
    SimulationResult,
    SimulationSchemaError,
    load_simulation_result_from_dict,
    load_simulation_result_from_json,
    validate_simulation_result_dict,
)

# ---------------------------------------------------------------------------
# Verdict and Stable Reason Codes
# ---------------------------------------------------------------------------

class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    NEEDS_REVIEW = "NEEDS_REVIEW"


# Stable machine-readable reason codes
REASON_PROVEN_TRANSFER_AMOUNT_MISMATCH = "MISMATCH_TOKEN_TRANSFER_AMOUNT"
REASON_PROVEN_TRANSFER_RECIPIENT_MISMATCH = "MISMATCH_TOKEN_TRANSFER_RECIPIENT"
REASON_PROVEN_TRANSFER_MISSING = "MISMATCH_TOKEN_TRANSFER_MISSING"
REASON_PROVEN_NATIVE_TRANSFER_MISMATCH = "MISMATCH_NATIVE_TRANSFER_AMOUNT"
REASON_PROVEN_NATIVE_TRANSFER_AMOUNT_MISMATCH = REASON_PROVEN_NATIVE_TRANSFER_MISMATCH
REASON_PROVEN_NATIVE_TRANSFER_MISSING = "MISMATCH_NATIVE_TRANSFER_MISSING"
REASON_UNCLAIMED_MATERIAL_TRANSFER = "MISMATCH_UNCLAIMED_MATERIAL_TRANSFER"
REASON_OWNERSHIP_COLLISION_DETECTED = "MISMATCH_OWNERSHIP_COLLISION"
REASON_FORBIDDEN_EFFECT_OBSERVED = "MISMATCH_FORBIDDEN_EFFECT_OBSERVED"
REASON_ALLOWANCE_VIOLATION = "MISMATCH_ALLOWANCE_VIOLATED"
REASON_UNCLAIMED_STATE_MUTATION = "MISMATCH_UNCLAIMED_STATE_MUTATION"

REASON_RISKY_OPERATION_FLAG = "NEEDS_REVIEW_RISKY_OPERATION_FLAG"
REASON_TRACE_INCOMPLETE = "NEEDS_REVIEW_TRACE_INCOMPLETE"
REASON_REQUIRED_EVIDENCE_MISSING = "NEEDS_REVIEW_REQUIRED_EVIDENCE_MISSING"
REASON_SIMULATION_FAILED = "NEEDS_REVIEW_SIMULATION_FAILED"
REASON_SIMULATION_ERRORS = "NEEDS_REVIEW_SIMULATION_ERRORS"
REASON_CLAIMS_AMBIGUOUS = "NEEDS_REVIEW_CLAIMS_AMBIGUOUS"
REASON_CLAIMS_UNSUPPORTED_TYPE = "NEEDS_REVIEW_UNSUPPORTED_CLAIM_TYPE"
REASON_MALFORMED_INPUT = "NEEDS_REVIEW_MALFORMED_INPUT"

REASON_ALL_CLAIMS_VERIFIED = "VERIFIED_ALL_CLAIMS_MATCH"


@dataclass(frozen=True)
class EvidenceReference:
    """Detailed pointer to specific evidence in claims or simulation."""
    source: str  # 'state_diff', 'log', 'claim', 'finding', 'schema'
    identifier: str  # e.g. 'log[0]', 'slot:0x0', 'claim-001'
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "identifier": self.identifier,
            "details": self.details,
        }


@dataclass(frozen=True)
class ComparisonResult:
    verdict: Verdict
    reason_code: str
    explanation: str
    evidence_references: List[EvidenceReference] = field(default_factory=list)
    matched_claims: List[str] = field(default_factory=list)
    unmatched_claims: List[str] = field(default_factory=list)
    unclaimed_effects: List[Dict[str, Any]] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "evidence_references": [e.to_dict() for e in self.evidence_references],
            "matched_claims": self.matched_claims,
            "unmatched_claims": self.unmatched_claims,
            "unclaimed_effects": self.unclaimed_effects,
            "findings": self.findings,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


@dataclass
class VerdictEngineConfig:
    """Configuration for deterministic verdict engine."""
    risky_finding_codes: Set[str] = field(
        default_factory=lambda: {
            "DELEGATECALL_DETECTED",
            "DELEGATECALL",
            "SELFDESTRUCT_DETECTED",
            "SELFDESTRUCT",
            "UNVERIFIED_TARGET",
            "DYNAMIC_DISPATCH",
            "ARBITRARY_CALL",
        }
    )
    strict_unclaimed_transfers: bool = True
    strict_treasury_storage: bool = True


# ---------------------------------------------------------------------------
# Core Comparison Logic
# ---------------------------------------------------------------------------

def compare(
    claims: Union[ProposalClaims, Dict[str, Any], str],
    simulation: Union[SimulationResult, Dict[str, Any], str],
    config: Optional[VerdictEngineConfig] = None,
) -> ComparisonResult:
    """
    Deterministic comparison engine entrypoint.
    Consumes proposal claims and simulation result, evaluating execution effects against claims.
    """
    cfg = config or VerdictEngineConfig()

    # Step 1: Normalize and validate claims input
    parsed_claims: Optional[ProposalClaims] = None
    claims_error: Optional[str] = None
    claims_unsupported: bool = False

    if isinstance(claims, ProposalClaims):
        parsed_claims = claims
    elif isinstance(claims, (dict, str)):
        try:
            if isinstance(claims, str):
                parsed_claims = load_claims_from_json(claims)
            else:
                parsed_claims = load_claims_from_dict(claims)
        except ClaimsValidationError as e:
            claims_error = str(e)
            if "unsupported claim type" in claims_error.lower():
                claims_unsupported = True
    else:
        claims_error = f"Unsupported claims input type: {type(claims).__name__}"

    # Step 2: Validate simulation result schema
    parsed_sim: Optional[SimulationResult] = None
    sim_schema_errors: List[str] = []
    raw_sim_dict: Optional[Dict[str, Any]] = None

    if isinstance(simulation, SimulationResult):
        parsed_sim = simulation
        raw_sim_dict = simulation.raw_data
    elif isinstance(simulation, dict):
        raw_sim_dict = simulation
        is_valid, errors = validate_simulation_result_dict(simulation)
        if not is_valid:
            sim_schema_errors = errors
        else:
            try:
                parsed_sim = load_simulation_result_from_dict(simulation)
            except SimulationSchemaError as e:
                sim_schema_errors = [str(e)]
    elif isinstance(simulation, str):
        try:
            raw_sim_dict = json.loads(simulation)
            if isinstance(raw_sim_dict, dict):
                is_valid, errors = validate_simulation_result_dict(raw_sim_dict)
                if not is_valid:
                    sim_schema_errors = errors
                else:
                    parsed_sim = load_simulation_result_from_dict(raw_sim_dict)
            else:
                sim_schema_errors = ["Simulation JSON must represent a root object"]
        except json.JSONDecodeError as e:
            sim_schema_errors = [f"Invalid simulation JSON: {e}"]
    else:
        sim_schema_errors = [f"Unsupported simulation input type: {type(simulation).__name__}"]

    # -----------------------------------------------------------------------
    # Step 3: Check for Proven Material Mismatches (Rule 1 of Precedence)
    # Even if trace is incomplete or risky flags exist, if reliable evidence proves
    # a violation or unclaimed material transfer, verdict is MISMATCH.
    # -----------------------------------------------------------------------

    # We can check for proven mismatches if we have parsed_claims and at least
    # partial logs / state diffs from simulation.
    if parsed_claims is not None:
        target_treasury = parsed_claims.target_treasury

        # Extract observed transfers and diffs from simulation (parsed or raw fallback)
        observed_transfers: List[ObservedTokenTransfer] = []
        observed_diffs: List[ObservedStorageDiff] = []
        observed_approvals: List[ObservedApproval] = []
        observed_native: List[ObservedNativeTransfer] = []

        if parsed_sim is not None:
            observed_transfers = parsed_sim.get_token_transfers()
            observed_diffs = parsed_sim.state_diffs
            observed_approvals = parsed_sim.get_allowance_approvals()
            observed_native = parsed_sim.get_native_transfers()
        elif raw_sim_dict is not None:
            # Fallback extraction to check for proven attacks even on malformed schemas
            try:
                temp_sim = load_simulation_result_from_dict({
                    "scenario_id": raw_sim_dict.get("scenario_id", "temp"),
                    "chain_id": raw_sim_dict.get("chain_id", 1),
                    "simulation_mode": raw_sim_dict.get("simulation_mode", "temp"),
                    "success": raw_sim_dict.get("success", False),
                    "trace_complete": raw_sim_dict.get("trace_complete", False),
                    "state_diffs": raw_sim_dict.get("state_diffs", []),
                    "logs": raw_sim_dict.get("logs", []),
                    "findings": raw_sim_dict.get("findings", []),
                    "errors": raw_sim_dict.get("errors", []),
                })
                observed_transfers = temp_sim.get_token_transfers()
                observed_diffs = temp_sim.state_diffs
                observed_approvals = temp_sim.get_allowance_approvals()
                observed_native = temp_sim.get_native_transfers()
            except Exception:
                pass

        # 3.1 Check Ownership Expectations & Collisions
        for claim in parsed_claims.claims:
            if isinstance(claim, OwnershipExpectationClaim):
                contract_diffs = [d for d in observed_diffs if d.address == claim.contract]
                # Check slot 0 (ownership slot in Treasury)
                for diff in contract_diffs:
                    if diff.slot_index == 0 or diff.slot in ("0x0", "0x00") or diff.slot_name == "owner":
                        if diff.has_mutated:
                            if claim.expected_state == OwnershipState.UNCHANGED:
                                return ComparisonResult(
                                    verdict=Verdict.MISMATCH,
                                    reason_code=REASON_OWNERSHIP_COLLISION_DETECTED,
                                    explanation=(
                                        f"Contract {claim.contract} ownership mutated from {diff.before} to {diff.after}, "
                                        f"violating UNCHANGED expectation (Slot 0 collision)."
                                    ),
                                    evidence_references=[
                                        EvidenceReference(
                                            source="state_diff",
                                            identifier=f"{diff.address}:slot_0",
                                            details={
                                                "claim_id": claim.claim_id,
                                                "slot": diff.slot,
                                                "before": diff.before,
                                                "after": diff.after,
                                                "slot_name": diff.slot_name,
                                            },
                                        )
                                    ],
                                )
                            elif claim.expected_state == OwnershipState.SET_TO:
                                if diff.after_as_address != claim.expected_owner:
                                    return ComparisonResult(
                                        verdict=Verdict.MISMATCH,
                                        reason_code=REASON_OWNERSHIP_COLLISION_DETECTED,
                                        explanation=(
                                            f"Contract {claim.contract} owner set to {diff.after_as_address}, "
                                            f"expected {claim.expected_owner}."
                                        ),
                                        evidence_references=[
                                            EvidenceReference(
                                                source="state_diff",
                                                identifier=f"{diff.address}:slot_0",
                                                details={
                                                    "claim_id": claim.claim_id,
                                                    "expected_owner": claim.expected_owner,
                                                    "observed_after": diff.after,
                                                },
                                            )
                                        ],
                                    )

        # 3.2 Check Forbidden Effects
        for claim in parsed_claims.claims:
            if isinstance(claim, ForbiddenEffectClaim):
                if claim.effect_type == ForbiddenEffectType.OWNERSHIP_CHANGE:
                    target_diffs = [d for d in observed_diffs if d.address == claim.target]
                    for diff in target_diffs:
                        if (diff.slot_index == 0 or diff.slot in ("0x0", "0x00") or diff.slot_name == "owner") and diff.has_mutated:
                            return ComparisonResult(
                                verdict=Verdict.MISMATCH,
                                reason_code=REASON_FORBIDDEN_EFFECT_OBSERVED,
                                explanation=(
                                    f"Forbidden effect observed: Ownership of {claim.target} was mutated "
                                    f"from {diff.before} to {diff.after}."
                                ),
                                evidence_references=[
                                    EvidenceReference(
                                        source="state_diff",
                                        identifier=f"{diff.address}:slot_0",
                                        details={
                                            "claim_id": claim.claim_id,
                                            "forbidden_effect": claim.effect_type.value,
                                            "before": diff.before,
                                            "after": diff.after,
                                        },
                                    )
                                ],
                            )
                elif claim.effect_type == ForbiddenEffectType.ALLOWANCE_MUTATION:
                    for app in observed_approvals:
                        if app.token == claim.target or app.owner == claim.target:
                            return ComparisonResult(
                                verdict=Verdict.MISMATCH,
                                reason_code=REASON_FORBIDDEN_EFFECT_OBSERVED,
                                explanation=(
                                    f"Forbidden allowance mutation observed on {claim.target}: "
                                    f"Approved {app.spender} for {app.value}."
                                ),
                                evidence_references=[
                                    EvidenceReference(
                                        source="log",
                                        identifier=f"log[{app.log_index}]",
                                        details={
                                            "claim_id": claim.claim_id,
                                            "token": app.token,
                                            "owner": app.owner,
                                            "spender": app.spender,
                                            "value": str(app.value),
                                        },
                                    )
                                ],
                            )
                elif claim.effect_type == ForbiddenEffectType.ARBITRARY_STORAGE_WRITE:
                    target_diffs = [d for d in observed_diffs if d.address == claim.target and d.has_mutated]
                    if target_diffs:
                        first_diff = target_diffs[0]
                        return ComparisonResult(
                            verdict=Verdict.MISMATCH,
                            reason_code=REASON_FORBIDDEN_EFFECT_OBSERVED,
                            explanation=f"Forbidden arbitrary storage write on {claim.target} at slot {first_diff.slot}.",
                            evidence_references=[
                                EvidenceReference(
                                    source="state_diff",
                                    identifier=f"{first_diff.address}:{first_diff.slot}",
                                    details={"claim_id": claim.claim_id, "diff": asdict(first_diff)},
                                )
                            ],
                        )

        # 3.3 Match Claimed Token Transfers & Detect Mismatches
        matched_claim_ids: Set[str] = set()
        matched_transfer_indices: Set[int] = set()
        unmatched_claim_ids: List[str] = []

        token_claims = [c for c in parsed_claims.claims if isinstance(c, TokenTransferClaim)]

        for claim in token_claims:
            matched = False
            for t_idx, obs in enumerate(observed_transfers):
                if t_idx in matched_transfer_indices:
                    continue
                # Check recipient, token, and amount
                if obs.token == claim.token and obs.to_address == claim.recipient:
                    if claim.sender and obs.from_address != claim.sender:
                        continue
                    if obs.amount == claim.amount:
                        matched = True
                        matched_claim_ids.add(claim.claim_id)
                        matched_transfer_indices.add(t_idx)
                        break

            if not matched:
                unmatched_claim_ids.append(claim.claim_id)
                # Check if there was an amount mismatch or recipient mismatch for same token/sender
                for obs in observed_transfers:
                    if obs.token == claim.token:
                        if obs.to_address == claim.recipient and obs.amount != claim.amount:
                            return ComparisonResult(
                                verdict=Verdict.MISMATCH,
                                reason_code=REASON_PROVEN_TRANSFER_AMOUNT_MISMATCH,
                                explanation=(
                                    f"Token transfer amount mismatch for claim '{claim.claim_id}': "
                                    f"Expected {claim.amount} raw units, observed {obs.amount}."
                                ),
                                evidence_references=[
                                    EvidenceReference(
                                        source="log",
                                        identifier=f"log[{obs.log_index}]",
                                        details={
                                            "claim_id": claim.claim_id,
                                            "expected_amount": str(claim.amount),
                                            "observed_amount": str(obs.amount),
                                            "token": claim.token,
                                            "recipient": claim.recipient,
                                        },
                                    )
                                ],
                            )
                        elif obs.amount == claim.amount and obs.to_address != claim.recipient:
                            return ComparisonResult(
                                verdict=Verdict.MISMATCH,
                                reason_code=REASON_PROVEN_TRANSFER_RECIPIENT_MISMATCH,
                                explanation=(
                                    f"Token transfer recipient mismatch for claim '{claim.claim_id}': "
                                    f"Expected recipient {claim.recipient}, observed {obs.to_address}."
                                ),
                                evidence_references=[
                                    EvidenceReference(
                                        source="log",
                                        identifier=f"log[{obs.log_index}]",
                                        details={
                                            "claim_id": claim.claim_id,
                                            "expected_recipient": claim.recipient,
                                            "observed_recipient": obs.to_address,
                                            "token": claim.token,
                                        },
                                    )
                                ],
                            )

                # If simulation succeeded and trace complete, a missing claimed transfer is a proven mismatch
                if parsed_sim is not None and parsed_sim.success and parsed_sim.trace_complete:
                    return ComparisonResult(
                        verdict=Verdict.MISMATCH,
                        reason_code=REASON_PROVEN_TRANSFER_MISSING,
                        explanation=f"Required token transfer for claim '{claim.claim_id}' was not observed in execution.",
                        evidence_references=[
                            EvidenceReference(
                                source="claim",
                                identifier=claim.claim_id,
                                details={
                                    "token": claim.token,
                                    "recipient": claim.recipient,
                                    "expected_amount": str(claim.amount),
                                },
                            )
                        ],
                    )

        # 3.4 Match Native Transfers
        native_claims = [c for c in parsed_claims.claims if isinstance(c, NativeTransferClaim)]
        for claim in native_claims:
            matched_n = False
            for obs_n in observed_native:
                if obs_n.to_address == claim.recipient and obs_n.amount == claim.amount:
                    matched_n = True
                    matched_claim_ids.add(claim.claim_id)
                    break
            if not matched_n:
                for obs_n in observed_native:
                    if obs_n.to_address == claim.recipient and obs_n.amount != claim.amount:
                        return ComparisonResult(
                            verdict=Verdict.MISMATCH,
                            reason_code=REASON_PROVEN_NATIVE_TRANSFER_MISMATCH,
                            explanation=(
                                f"Native transfer amount mismatch for claim '{claim.claim_id}': "
                                f"Expected {claim.amount} wei, observed {obs_n.amount} wei."
                            ),
                            evidence_references=[
                                EvidenceReference(
                                    source="trace",
                                    identifier=f"call[{obs_n.call_index}]",
                                    details={"expected": str(claim.amount), "observed": str(obs_n.amount)},
                                )
                            ],
                        )
                if parsed_sim is not None and parsed_sim.success and parsed_sim.trace_complete:
                    return ComparisonResult(
                        verdict=Verdict.MISMATCH,
                        reason_code=REASON_PROVEN_NATIVE_TRANSFER_MISSING,
                        explanation=f"Required native transfer for claim '{claim.claim_id}' was not observed.",
                        evidence_references=[EvidenceReference(source="claim", identifier=claim.claim_id)],
                    )

        # 3.5 Match Allowance Expectations
        allowance_claims = [c for c in parsed_claims.claims if isinstance(c, AllowanceExpectationClaim)]
        for claim in allowance_claims:
            matched_a = False
            for obs_a in observed_approvals:
                if obs_a.token == claim.token and obs_a.owner == claim.owner and obs_a.spender == claim.spender:
                    if obs_a.value == claim.expected_allowance:
                        matched_a = True
                        matched_claim_ids.add(claim.claim_id)
                        break
                    else:
                        return ComparisonResult(
                            verdict=Verdict.MISMATCH,
                            reason_code=REASON_ALLOWANCE_VIOLATION,
                            explanation=(
                                f"Allowance expectation violated for claim '{claim.claim_id}': "
                                f"Expected allowance {claim.expected_allowance}, observed {obs_a.value}."
                            ),
                            evidence_references=[
                                EvidenceReference(
                                    source="log",
                                    identifier=f"log[{obs_a.log_index}]",
                                    details={
                                        "claim_id": claim.claim_id,
                                        "token": obs_a.token,
                                        "owner": obs_a.owner,
                                        "spender": obs_a.spender,
                                        "expected": str(claim.expected_allowance),
                                        "observed": str(obs_a.value),
                                    },
                                )
                            ],
                        )
            if not matched_a:
                if parsed_sim is not None and parsed_sim.success and parsed_sim.trace_complete:
                    return ComparisonResult(
                        verdict=Verdict.MISMATCH,
                        reason_code=REASON_ALLOWANCE_VIOLATION,
                        explanation=f"Expected allowance approval for claim '{claim.claim_id}' was not observed.",
                        evidence_references=[EvidenceReference(source="claim", identifier=claim.claim_id)],
                    )

        # 3.6 Check for Unclaimed Material Transfers
        if cfg.strict_unclaimed_transfers:
            for t_idx, obs in enumerate(observed_transfers):
                if t_idx not in matched_transfer_indices:
                    # An extra token transfer occurred with amount > 0 that was never claimed
                    if obs.amount > 0:
                        return ComparisonResult(
                            verdict=Verdict.MISMATCH,
                            reason_code=REASON_UNCLAIMED_MATERIAL_TRANSFER,
                            explanation=(
                                f"Observed unclaimed material transfer of {obs.amount} tokens ({obs.token}) "
                                f"from {obs.from_address} to {obs.to_address} (Log #{obs.log_index})."
                            ),
                            evidence_references=[
                                EvidenceReference(
                                    source="log",
                                    identifier=f"log[{obs.log_index}]",
                                    details={
                                        "token": obs.token,
                                        "from": obs.from_address,
                                        "to": obs.to_address,
                                        "amount": str(obs.amount),
                                    },
                                )
                            ],
                            unclaimed_effects=[
                                {
                                    "type": "TOKEN_TRANSFER",
                                    "token": obs.token,
                                    "from": obs.from_address,
                                    "to": obs.to_address,
                                    "amount": str(obs.amount),
                                    "log_index": obs.log_index,
                                }
                            ],
                        )

        # 3.5 Check for Unclaimed Treasury Storage Mutations
        if cfg.strict_treasury_storage and target_treasury:
            claimed_slots: Set[int] = set()
            for c in parsed_claims.claims:
                if isinstance(c, OwnershipExpectationClaim) and c.contract == target_treasury:
                    claimed_slots.add(0)

            for diff in observed_diffs:
                if diff.address == target_treasury and diff.has_mutated:
                    if diff.slot_index not in claimed_slots and diff.slot not in ("0x0", "0x00"):
                        return ComparisonResult(
                            verdict=Verdict.MISMATCH,
                            reason_code=REASON_UNCLAIMED_STATE_MUTATION,
                            explanation=(
                                f"Observed unclaimed storage mutation on Treasury {target_treasury} "
                                f"at slot {diff.slot} ({diff.before} -> {diff.after})."
                            ),
                            evidence_references=[
                                EvidenceReference(
                                    source="state_diff",
                                    identifier=f"{diff.address}:{diff.slot}",
                                    details=asdict(diff),
                                )
                            ],
                        )

    # -----------------------------------------------------------------------
    # Step 4: Rule 2 - Uncertainty, Risky Flags, or Incomplete Evidence => NEEDS_REVIEW
    # -----------------------------------------------------------------------

    # 4.1 Claims schema or ambiguity errors
    if claims_error is not None:
        code = REASON_CLAIMS_UNSUPPORTED_TYPE if claims_unsupported else REASON_CLAIMS_AMBIGUOUS
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=code,
            explanation=f"Claims validation failed: {claims_error}",
            evidence_references=[EvidenceReference(source="claim", identifier="claims_root", details={"error": claims_error})],
        )

    # 4.2 Simulation schema errors (missing required fields)
    if sim_schema_errors:
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=REASON_REQUIRED_EVIDENCE_MISSING,
            explanation=f"Simulation result schema incomplete: {'; '.join(sim_schema_errors)}",
            evidence_references=[
                EvidenceReference(source="schema", identifier=err, details={"error": err})
                for err in sim_schema_errors
            ],
        )

    assert parsed_sim is not None
    assert parsed_claims is not None

    # 4.3 Simulation execution failure (revert)
    if not parsed_sim.success:
        err_msg = "; ".join(parsed_sim.errors) if parsed_sim.errors else "Execution reverted"
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=REASON_SIMULATION_FAILED,
            explanation=f"Simulation reverted or failed: {err_msg}",
            evidence_references=[
                EvidenceReference(source="schema", identifier="success", details={"errors": parsed_sim.errors})
            ],
        )

    # 4.4 Simulation errors reported
    if parsed_sim.errors:
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=REASON_SIMULATION_ERRORS,
            explanation=f"Simulation reported execution errors: {'; '.join(parsed_sim.errors)}",
            evidence_references=[
                EvidenceReference(source="schema", identifier="errors", details={"errors": parsed_sim.errors})
            ],
        )

    # 4.5 Trace incomplete
    if not parsed_sim.trace_complete:
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=REASON_TRACE_INCOMPLETE,
            explanation="Simulation execution trace is incomplete or was truncated; safety cannot be verified.",
            evidence_references=[
                EvidenceReference(source="schema", identifier="trace_complete", details={"trace_complete": False})
            ],
        )

    # 4.6 Configured risky trace flags (e.g. DELEGATECALL_DETECTED)
    observed_finding_codes = parsed_sim.get_finding_codes()
    risky_intersect = observed_finding_codes.intersection({c.upper() for c in cfg.risky_finding_codes})
    if risky_intersect:
        sorted_risky = sorted(risky_intersect)
        finding_objs = [asdict(f) for f in parsed_sim.findings if f.code.upper() in risky_intersect]
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=REASON_RISKY_OPERATION_FLAG,
            explanation=f"Simulation trace contains configured risky operation flag(s): {', '.join(sorted_risky)}.",
            evidence_references=[
                EvidenceReference(source="finding", identifier=code, details={"code": code})
                for code in sorted_risky
            ],
            findings=finding_objs,
        )

    # 4.7 Any unmatched claims remaining
    # Passive expectation claims (ownership, forbidden effects) are satisfied if no violations occurred
    for c in parsed_claims.claims:
        if isinstance(c, (OwnershipExpectationClaim, ForbiddenEffectClaim)):
            matched_claim_ids.add(c.claim_id)

    all_claim_ids = [c.claim_id for c in parsed_claims.claims]
    active_claim_ids = [
        c.claim_id
        for c in parsed_claims.claims
        if isinstance(c, (TokenTransferClaim, NativeTransferClaim, AllowanceExpectationClaim))
    ]
    unmatched_ids = [cid for cid in active_claim_ids if cid not in matched_claim_ids]
    if unmatched_ids:
        return ComparisonResult(
            verdict=Verdict.NEEDS_REVIEW,
            reason_code=REASON_PROVEN_TRANSFER_MISSING,
            explanation=f"Proposal claims were not fully satisfied. Unmatched claims: {', '.join(unmatched_ids)}",
            evidence_references=[EvidenceReference(source="claim", identifier=cid) for cid in unmatched_ids],
            matched_claims=sorted(matched_claim_ids),
            unmatched_claims=sorted(unmatched_ids),
        )

    # -----------------------------------------------------------------------
    # Step 5: Rule 3 - VERIFIED (All claims match, clean complete evidence)
    # -----------------------------------------------------------------------
    return ComparisonResult(
        verdict=Verdict.VERIFIED,
        reason_code=REASON_ALL_CLAIMS_VERIFIED,
        explanation="All claimed proposal effects verified cleanly against complete simulation trace.",
        evidence_references=[],
        matched_claims=sorted(all_claim_ids),
        unmatched_claims=[],
        unclaimed_effects=[],
        findings=[],
        metadata={
            "scenario_id": parsed_sim.scenario_id,
            "proposal_id": parsed_claims.proposal_id,
            "chain_id": parsed_sim.chain_id,
        },
    )
