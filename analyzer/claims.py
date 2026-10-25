"""
analyzer/claims.py
==================
Structured proposal claims data models, validation, and JSON loading for Veritas Gate Phase 3.

Claims represent explicit declarations made by proposal authors about the intended
execution effects of a governance action (e.g., token transfers, native transfers,
ownership assertions, allowance assertions, and explicitly forbidden effects).

Interface Discipline:
- Strict versioned schema: 'veritas-claims-v1.0'.
- Fails closed: ambiguous or unsupported claim types are rejected, never ignored.
- Units, addresses, and integer amounts are explicitly validated.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

EVM_ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")
INTEGER_STRING_REGEX = re.compile(r"^[0-9]+$")

DEFAULT_CLAIMS_SCHEMA_VERSION = "veritas-claims-v1.0"


class ClaimsValidationError(ValueError):
    """Raised when proposal claims JSON or structure fails validation."""
    pass


class ClaimType(str, Enum):
    """Supported claim types for governance proposals."""
    TOKEN_TRANSFER = "TOKEN_TRANSFER"
    NATIVE_TRANSFER = "NATIVE_TRANSFER"
    OWNERSHIP_EXPECTATION = "OWNERSHIP_EXPECTATION"
    ALLOWANCE_EXPECTATION = "ALLOWANCE_EXPECTATION"
    FORBIDDEN_EFFECT = "FORBIDDEN_EFFECT"


class ForbiddenEffectType(str, Enum):
    """Supported forbidden effect types."""
    OWNERSHIP_CHANGE = "OWNERSHIP_CHANGE"
    UNAPPROVED_TRANSFER = "UNAPPROVED_TRANSFER"
    ALLOWANCE_MUTATION = "ALLOWANCE_MUTATION"
    ARBITRARY_STORAGE_WRITE = "ARBITRARY_STORAGE_WRITE"


class OwnershipState(str, Enum):
    """Expected state for ownership assertions."""
    UNCHANGED = "UNCHANGED"
    SET_TO = "SET_TO"


def normalize_address(address: str, field_name: str = "address") -> str:
    """
    Validates and normalizes an EVM address to lowercase format.
    Raises ClaimsValidationError if address is malformed.
    """
    if not isinstance(address, str):
        raise ClaimsValidationError(f"Invalid {field_name}: address must be a string, got {type(address).__name__}")
    addr = address.strip()
    if not EVM_ADDRESS_REGEX.match(addr):
        raise ClaimsValidationError(f"Invalid {field_name}: '{address}' is not a valid 20-byte hex EVM address")
    return addr.lower()


def parse_raw_amount(amount: Any, field_name: str = "amount") -> int:
    """
    Validates and parses a raw integer amount (e.g. uint256 in wei or base units).
    Rejects floats, ranges, negative values, and non-numeric strings to prevent ambiguity.
    Accepts exact non-negative integers, decimal integer strings, and 0x-prefixed hex integer strings.
    """
    if isinstance(amount, bool):
        raise ClaimsValidationError(f"Invalid {field_name}: boolean value is not a valid amount")
    if isinstance(amount, int):
        if amount < 0:
            raise ClaimsValidationError(f"Invalid {field_name}: amount cannot be negative ({amount})")
        return amount
    if isinstance(amount, str):
        cleaned = amount.strip()
        if cleaned.startswith("0x") or cleaned.startswith("0X"):
            clean_hex = cleaned[2:]
            if not clean_hex or not re.match(r"^[0-9a-fA-F]+$", clean_hex):
                raise ClaimsValidationError(
                    f"Invalid {field_name}: ambiguous or non-integer value '{amount}'. "
                    f"Amounts must be exact raw non-negative integer strings without decimals or ranges."
                )
            val = int(cleaned, 16)
            if val < 0:
                raise ClaimsValidationError(f"Invalid {field_name}: amount cannot be negative ({val})")
            return val
        if not INTEGER_STRING_REGEX.match(cleaned):
            raise ClaimsValidationError(
                f"Invalid {field_name}: ambiguous or non-integer value '{amount}'. "
                f"Amounts must be exact raw non-negative integer strings without decimals or ranges."
            )
        val = int(cleaned)
        if val < 0:
            raise ClaimsValidationError(f"Invalid {field_name}: amount cannot be negative ({val})")
        return val
    raise ClaimsValidationError(
        f"Invalid {field_name}: expected integer or decimal string, got {type(amount).__name__}"
    )


@dataclass(frozen=True, kw_only=True)
class BaseClaim:
    claim_id: str
    type: ClaimType
    unit: str
    description: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class TokenTransferClaim(BaseClaim):
    token: str
    recipient: str
    amount: int
    sender: Optional[str] = None

    def __post_init__(self):
        if not self.claim_id or not self.claim_id.strip():
            raise ClaimsValidationError("TokenTransferClaim requires a non-empty 'claim_id'")
        if not self.unit or not self.unit.strip():
            raise ClaimsValidationError("TokenTransferClaim requires a non-empty 'unit'")


@dataclass(frozen=True, kw_only=True)
class NativeTransferClaim(BaseClaim):
    recipient: str
    amount: int
    sender: Optional[str] = None

    def __post_init__(self):
        if not self.claim_id or not self.claim_id.strip():
            raise ClaimsValidationError("NativeTransferClaim requires a non-empty 'claim_id'")
        if not self.unit or not self.unit.strip():
            raise ClaimsValidationError("NativeTransferClaim requires a non-empty 'unit'")


@dataclass(frozen=True, kw_only=True)
class OwnershipExpectationClaim(BaseClaim):
    contract: str
    expected_state: OwnershipState = OwnershipState.UNCHANGED
    expected_owner: Optional[str] = None

    def __post_init__(self):
        if not self.claim_id or not self.claim_id.strip():
            raise ClaimsValidationError("OwnershipExpectationClaim requires a non-empty 'claim_id'")
        if not self.unit or not self.unit.strip():
            raise ClaimsValidationError("OwnershipExpectationClaim requires a non-empty 'unit'")
        if self.expected_state == OwnershipState.SET_TO and not self.expected_owner:
            raise ClaimsValidationError(
                "OwnershipExpectationClaim with expected_state='SET_TO' requires 'expected_owner' address"
            )


@dataclass(frozen=True, kw_only=True)
class AllowanceExpectationClaim(BaseClaim):
    token: str
    owner: str
    spender: str
    expected_allowance: int

    def __post_init__(self):
        if not self.claim_id or not self.claim_id.strip():
            raise ClaimsValidationError("AllowanceExpectationClaim requires a non-empty 'claim_id'")
        if not self.unit or not self.unit.strip():
            raise ClaimsValidationError("AllowanceExpectationClaim requires a non-empty 'unit'")


@dataclass(frozen=True, kw_only=True)
class ForbiddenEffectClaim(BaseClaim):
    effect_type: ForbiddenEffectType
    target: str

    def __post_init__(self):
        if not self.claim_id or not self.claim_id.strip():
            raise ClaimsValidationError("ForbiddenEffectClaim requires a non-empty 'claim_id'")
        if not self.unit or not self.unit.strip():
            raise ClaimsValidationError("ForbiddenEffectClaim requires a non-empty 'unit'")


@dataclass(frozen=True, kw_only=True)
class ProposalClaims:
    schema_version: str
    proposal_id: str
    title: str
    claims: List[BaseClaim] = field(default_factory=list)
    target_treasury: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert ProposalClaims to a clean JSON-serializable dictionary."""
        claims_list = []
        for c in self.claims:
            claim_dict: Dict[str, Any] = {
                "claim_id": c.claim_id,
                "type": c.type.value if isinstance(c.type, Enum) else str(c.type),
                "unit": c.unit,
            }
            if c.description:
                claim_dict["description"] = c.description

            if isinstance(c, TokenTransferClaim):
                claim_dict.update({
                    "token": c.token,
                    "recipient": c.recipient,
                    "amount": str(c.amount),
                })
                if c.sender:
                    claim_dict["sender"] = c.sender
            elif isinstance(c, NativeTransferClaim):
                claim_dict.update({
                    "recipient": c.recipient,
                    "amount": str(c.amount),
                })
                if c.sender:
                    claim_dict["sender"] = c.sender
            elif isinstance(c, OwnershipExpectationClaim):
                claim_dict.update({
                    "contract": c.contract,
                    "expected_state": c.expected_state.value if isinstance(c.expected_state, Enum) else str(c.expected_state),
                })
                if c.expected_owner:
                    claim_dict["expected_owner"] = c.expected_owner
            elif isinstance(c, AllowanceExpectationClaim):
                claim_dict.update({
                    "token": c.token,
                    "owner": c.owner,
                    "spender": c.spender,
                    "expected_allowance": str(c.expected_allowance),
                })
            elif isinstance(c, ForbiddenEffectClaim):
                claim_dict.update({
                    "effect_type": c.effect_type.value if isinstance(c.effect_type, Enum) else str(c.effect_type),
                    "target": c.target,
                })
            claims_list.append(claim_dict)

        result: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "title": self.title,
            "claims": claims_list,
        }
        if self.target_treasury:
            result["target_treasury"] = self.target_treasury
        if self.description:
            result["description"] = self.description
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def get_token_transfer_claims(self) -> List[TokenTransferClaim]:
        return [c for c in self.claims if isinstance(c, TokenTransferClaim)]

    def get_native_transfer_claims(self) -> List[NativeTransferClaim]:
        return [c for c in self.claims if isinstance(c, NativeTransferClaim)]

    def get_ownership_claims(self) -> List[OwnershipExpectationClaim]:
        return [c for c in self.claims if isinstance(c, OwnershipExpectationClaim)]

    def get_allowance_claims(self) -> List[AllowanceExpectationClaim]:
        return [c for c in self.claims if isinstance(c, AllowanceExpectationClaim)]

    def get_forbidden_effect_claims(self) -> List[ForbiddenEffectClaim]:
        return [c for c in self.claims if isinstance(c, ForbiddenEffectClaim)]


def parse_claim_item(raw_claim: Dict[str, Any], index: int) -> BaseClaim:
    """
    Parses and strictly validates a single claim object.
    Fails closed: rejects ambiguous or unsupported claim types.
    """
    if not isinstance(raw_claim, dict):
        raise ClaimsValidationError(f"Claim at index {index} must be a JSON object")

    claim_id = raw_claim.get("claim_id")
    if not claim_id or not isinstance(claim_id, str) or not claim_id.strip():
        raise ClaimsValidationError(f"Claim at index {index} is missing required string 'claim_id'")

    raw_type = raw_claim.get("type")
    if not raw_type or not isinstance(raw_type, str):
        raise ClaimsValidationError(f"Claim '{claim_id}' is missing required string 'type'")

    unit = raw_claim.get("unit")
    if not unit or not isinstance(unit, str) or not unit.strip():
        raise ClaimsValidationError(f"Claim '{claim_id}' is missing required string 'unit'")

    description = raw_claim.get("description")
    if description is not None and not isinstance(description, str):
        raise ClaimsValidationError(f"Claim '{claim_id}' 'description' must be a string")

    # Match supported claim types strictly
    try:
        claim_type = ClaimType(raw_type.upper())
    except ValueError:
        raise ClaimsValidationError(
            f"Claim '{claim_id}' specifies unsupported claim type '{raw_type}'. "
            f"Supported types: {[t.value for t in ClaimType]}"
        )

    if claim_type == ClaimType.TOKEN_TRANSFER:
        if "token" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (TOKEN_TRANSFER) missing required field 'token'")
        if "recipient" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (TOKEN_TRANSFER) missing required field 'recipient'")
        if "amount" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (TOKEN_TRANSFER) missing required field 'amount'")

        token = normalize_address(raw_claim["token"], f"claim '{claim_id}'.token")
        recipient = normalize_address(raw_claim["recipient"], f"claim '{claim_id}'.recipient")
        amount = parse_raw_amount(raw_claim["amount"], f"claim '{claim_id}'.amount")
        sender = normalize_address(raw_claim["sender"], f"claim '{claim_id}'.sender") if raw_claim.get("sender") else None

        return TokenTransferClaim(
            claim_id=claim_id.strip(),
            type=claim_type,
            unit=unit.strip(),
            description=description,
            token=token,
            recipient=recipient,
            amount=amount,
            sender=sender,
        )

    elif claim_type == ClaimType.NATIVE_TRANSFER:
        if "recipient" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (NATIVE_TRANSFER) missing required field 'recipient'")
        if "amount" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (NATIVE_TRANSFER) missing required field 'amount'")

        recipient = normalize_address(raw_claim["recipient"], f"claim '{claim_id}'.recipient")
        amount = parse_raw_amount(raw_claim["amount"], f"claim '{claim_id}'.amount")
        sender = normalize_address(raw_claim["sender"], f"claim '{claim_id}'.sender") if raw_claim.get("sender") else None

        return NativeTransferClaim(
            claim_id=claim_id.strip(),
            type=claim_type,
            unit=unit.strip(),
            description=description,
            recipient=recipient,
            amount=amount,
            sender=sender,
        )

    elif claim_type == ClaimType.OWNERSHIP_EXPECTATION:
        if "contract" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (OWNERSHIP_EXPECTATION) missing required field 'contract'")

        contract_addr = normalize_address(raw_claim["contract"], f"claim '{claim_id}'.contract")
        raw_state = raw_claim.get("expected_state", "UNCHANGED")
        if not isinstance(raw_state, str):
            raise ClaimsValidationError(f"Claim '{claim_id}'.expected_state must be a string")

        try:
            expected_state = OwnershipState(raw_state.upper())
        except ValueError:
            raise ClaimsValidationError(
                f"Claim '{claim_id}' specifies unsupported expected_state '{raw_state}'. "
                f"Supported: {[s.value for s in OwnershipState]}"
            )

        expected_owner = None
        if raw_claim.get("expected_owner"):
            expected_owner = normalize_address(raw_claim["expected_owner"], f"claim '{claim_id}'.expected_owner")

        if expected_state == OwnershipState.SET_TO and not expected_owner:
            raise ClaimsValidationError(f"Claim '{claim_id}' specifies 'SET_TO' but lacks 'expected_owner'")

        return OwnershipExpectationClaim(
            claim_id=claim_id.strip(),
            type=claim_type,
            unit=unit.strip(),
            description=description,
            contract=contract_addr,
            expected_state=expected_state,
            expected_owner=expected_owner,
        )

    elif claim_type == ClaimType.ALLOWANCE_EXPECTATION:
        for req in ("token", "owner", "spender", "expected_allowance"):
            if req not in raw_claim:
                raise ClaimsValidationError(f"Claim '{claim_id}' (ALLOWANCE_EXPECTATION) missing required field '{req}'")

        token = normalize_address(raw_claim["token"], f"claim '{claim_id}'.token")
        owner = normalize_address(raw_claim["owner"], f"claim '{claim_id}'.owner")
        spender = normalize_address(raw_claim["spender"], f"claim '{claim_id}'.spender")
        expected_allowance = parse_raw_amount(raw_claim["expected_allowance"], f"claim '{claim_id}'.expected_allowance")

        return AllowanceExpectationClaim(
            claim_id=claim_id.strip(),
            type=claim_type,
            unit=unit.strip(),
            description=description,
            token=token,
            owner=owner,
            spender=spender,
            expected_allowance=expected_allowance,
        )

    elif claim_type == ClaimType.FORBIDDEN_EFFECT:
        if "effect_type" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (FORBIDDEN_EFFECT) missing required field 'effect_type'")
        if "target" not in raw_claim:
            raise ClaimsValidationError(f"Claim '{claim_id}' (FORBIDDEN_EFFECT) missing required field 'target'")

        raw_effect = raw_claim["effect_type"]
        if not isinstance(raw_effect, str):
            raise ClaimsValidationError(f"Claim '{claim_id}'.effect_type must be a string")

        try:
            effect_type = ForbiddenEffectType(raw_effect.upper())
        except ValueError:
            raise ClaimsValidationError(
                f"Claim '{claim_id}' specifies unsupported forbidden effect '{raw_effect}'. "
                f"Supported: {[e.value for e in ForbiddenEffectType]}"
            )

        target = normalize_address(raw_claim["target"], f"claim '{claim_id}'.target")

        return ForbiddenEffectClaim(
            claim_id=claim_id.strip(),
            type=claim_type,
            unit=unit.strip(),
            description=description,
            effect_type=effect_type,
            target=target,
        )

    raise ClaimsValidationError(f"Unhandled claim type: {claim_type}")


def load_claims_from_dict(data: Dict[str, Any]) -> ProposalClaims:
    """
    Validates and constructs a ProposalClaims object from a dictionary.
    Rejects malformed versions, missing required top-level attributes, and duplicate claim IDs.
    """
    if not isinstance(data, dict):
        raise ClaimsValidationError(f"Proposal claims must be a JSON object, got {type(data).__name__}")

    schema_version = data.get("schema_version")
    if not schema_version or not isinstance(schema_version, str):
        raise ClaimsValidationError("Missing or non-string 'schema_version' in claims document")
    if schema_version != DEFAULT_CLAIMS_SCHEMA_VERSION:
        raise ClaimsValidationError(
            f"Unsupported schema_version '{schema_version}'. Expected '{DEFAULT_CLAIMS_SCHEMA_VERSION}'"
        )

    proposal_id = data.get("proposal_id")
    if not proposal_id or not isinstance(proposal_id, str) or not proposal_id.strip():
        raise ClaimsValidationError("Missing or empty 'proposal_id' in claims document")

    title = data.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        raise ClaimsValidationError("Missing or empty 'title' in claims document")

    target_treasury = None
    if data.get("target_treasury"):
        target_treasury = normalize_address(data["target_treasury"], "target_treasury")

    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise ClaimsValidationError("'description' must be a string if provided")

    raw_claims = data.get("claims")
    if raw_claims is None or not isinstance(raw_claims, list):
        raise ClaimsValidationError("'claims' must be a list of claim objects")

    parsed_claims: List[BaseClaim] = []
    seen_ids: Set[str] = set()

    for idx, raw_claim in enumerate(raw_claims):
        claim_obj = parse_claim_item(raw_claim, idx)
        if claim_obj.claim_id in seen_ids:
            raise ClaimsValidationError(f"Duplicate claim_id detected: '{claim_obj.claim_id}'")
        seen_ids.add(claim_obj.claim_id)
        parsed_claims.append(claim_obj)

    return ProposalClaims(
        schema_version=schema_version.strip(),
        proposal_id=proposal_id.strip(),
        title=title.strip(),
        claims=parsed_claims,
        target_treasury=target_treasury,
        description=description,
    )


def load_claims_from_json(json_str: str) -> ProposalClaims:
    """Loads and validates ProposalClaims from a JSON string."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ClaimsValidationError(f"Invalid JSON syntax in claims: {exc}") from exc
    return load_claims_from_dict(data)


def validate_claims_dict(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Non-raising validation helper. Returns (is_valid, list_of_error_messages).
    """
    try:
        load_claims_from_dict(data)
        return True, []
    except ClaimsValidationError as e:
        return False, [str(e)]


# ---------------------------------------------------------------------------
# Standard Example Proposal Claims Generators (Honest 5M grant & Ownership protection)
# ---------------------------------------------------------------------------

def get_honest_5m_grant_claims(
    token_address: str,
    recipient_address: str,
    treasury_address: str,
    grant_amount_wei: int = 5_000_000 * 10**18,
    proposal_id: str = "prop-honest-5m-grant",
) -> ProposalClaims:
    """
    Returns verified claims specification for an honest 5M token grant.
    Specifies:
    1. Exact 5,000,000 * 10^18 token transfer to recipient.
    2. Treasury ownership expectation: UNCHANGED.
    3. Forbidden effect: Treasury ownership change explicitly forbidden.
    """
    token_norm = normalize_address(token_address, "token_address")
    recipient_norm = normalize_address(recipient_address, "recipient_address")
    treasury_norm = normalize_address(treasury_address, "treasury_address")

    claims: List[BaseClaim] = [
        TokenTransferClaim(
            claim_id="claim-001-grant-distribution",
            type=ClaimType.TOKEN_TRANSFER,
            token=token_norm,
            recipient=recipient_norm,
            amount=grant_amount_wei,
            unit="raw_tokens",
            sender=treasury_norm,
            description="5,000,000 mock tokens transferred from Treasury to grant recipient",
        ),
        OwnershipExpectationClaim(
            claim_id="claim-002-ownership-preserved",
            type=ClaimType.OWNERSHIP_EXPECTATION,
            contract=treasury_norm,
            expected_state=OwnershipState.UNCHANGED,
            unit="address",
            description="Treasury owner address must remain unchanged",
        ),
        ForbiddenEffectClaim(
            claim_id="claim-003-forbid-ownership-hijack",
            type=ClaimType.FORBIDDEN_EFFECT,
            effect_type=ForbiddenEffectType.OWNERSHIP_CHANGE,
            target=treasury_norm,
            unit="none",
            description="Slot 0 ownership modification on Treasury is explicitly forbidden",
        ),
    ]

    return ProposalClaims(
        schema_version=DEFAULT_CLAIMS_SCHEMA_VERSION,
        proposal_id=proposal_id,
        title="DAO Grant: 5,000,000 Token Ecosystem Distribution",
        target_treasury=treasury_norm,
        description="Transfers 5,000,000 tokens to recipient; strictly preserves Treasury ownership.",
        claims=claims,
    )


def get_forbid_ownership_claims(
    token_address: str,
    recipient_address: str,
    treasury_address: str,
    grant_amount_wei: int = 5_000_000 * 10**18,
    proposal_id: str = "prop-forbid-ownership",
) -> ProposalClaims:
    """
    Returns proposal claims explicitly focused on strictly forbidding any ownership changes
    or unapproved state writes while executing a grant.
    """
    token_norm = normalize_address(token_address, "token_address")
    recipient_norm = normalize_address(recipient_address, "recipient_address")
    treasury_norm = normalize_address(treasury_address, "treasury_address")

    claims: List[BaseClaim] = [
        TokenTransferClaim(
            claim_id="claim-grant-transfer",
            type=ClaimType.TOKEN_TRANSFER,
            token=token_norm,
            recipient=recipient_norm,
            amount=grant_amount_wei,
            unit="raw_tokens",
            sender=treasury_norm,
            description="Authorize standard grant token transfer",
        ),
        ForbiddenEffectClaim(
            claim_id="claim-forbid-ownership-change",
            type=ClaimType.FORBIDDEN_EFFECT,
            effect_type=ForbiddenEffectType.OWNERSHIP_CHANGE,
            target=treasury_norm,
            unit="none",
            description="Explicitly forbids mutating Treasury ownership slot 0",
        ),
        ForbiddenEffectClaim(
            claim_id="claim-forbid-unapproved-transfers",
            type=ClaimType.FORBIDDEN_EFFECT,
            effect_type=ForbiddenEffectType.UNAPPROVED_TRANSFER,
            target=treasury_norm,
            unit="none",
            description="Explicitly forbids any transfer other than the authorized grant",
        ),
    ]

    return ProposalClaims(
        schema_version=DEFAULT_CLAIMS_SCHEMA_VERSION,
        proposal_id=proposal_id,
        title="Grant Proposal with Explicit Ownership and Transfer Protection",
        target_treasury=treasury_norm,
        description="Enforces strict immutability of Treasury ownership and forbids unexpected transfers.",
        claims=claims,
    )
