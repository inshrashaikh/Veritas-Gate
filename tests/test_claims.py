"""
tests/test_claims.py
====================
Unit tests for structured proposal claims loading, validation, and serialization.
"""

import json
import pytest

from analyzer.claims import (
    ClaimsValidationError,
    ClaimType,
    ForbiddenEffectClaim,
    ForbiddenEffectType,
    NativeTransferClaim,
    OwnershipExpectationClaim,
    OwnershipState,
    ProposalClaims,
    TokenTransferClaim,
    get_forbid_ownership_claims,
    get_honest_5m_grant_claims,
    load_claims_from_dict,
    load_claims_from_json,
    normalize_address,
    parse_raw_amount,
    validate_claims_dict,
)


def test_normalize_address_valid():
    addr = "0x1111111111111111111111111111111111111111"
    assert normalize_address(addr) == addr.lower()
    # Mixed case checksummed
    mixed = "0x11111111111111111111111111111111111111Aa"
    assert normalize_address(mixed) == mixed.lower()


def test_normalize_address_invalid():
    with pytest.raises(ClaimsValidationError, match="not a valid 20-byte hex"):
        normalize_address("0x123")  # too short
    with pytest.raises(ClaimsValidationError, match="not a valid 20-byte hex"):
        normalize_address("not-an-address")
    with pytest.raises(ClaimsValidationError, match="must be a string"):
        normalize_address(12345)  # not string


def test_parse_raw_amount_valid():
    assert parse_raw_amount(5000000) == 5000000
    assert parse_raw_amount("5000000000000000000000000") == 5000000000000000000000000
    assert parse_raw_amount(0) == 0
    assert parse_raw_amount("0") == 0


def test_parse_raw_amount_invalid():
    with pytest.raises(ClaimsValidationError, match="ambiguous or non-integer"):
        parse_raw_amount("5.0")
    with pytest.raises(ClaimsValidationError, match="ambiguous or non-integer"):
        parse_raw_amount("5M")
    with pytest.raises(ClaimsValidationError, match="ambiguous or non-integer"):
        parse_raw_amount("5,000,000")
    with pytest.raises(ClaimsValidationError, match="cannot be negative"):
        parse_raw_amount(-100)
    with pytest.raises(ClaimsValidationError, match="boolean value is not a valid amount"):
        parse_raw_amount(True)


def test_load_honest_5m_grant_claims():
    token = "0x4444444444444444444444444444444444444444"
    recipient = "0x3333333333333333333333333333333333333333"
    treasury = "0x1111111111111111111111111111111111111111"

    claims_obj = get_honest_5m_grant_claims(token, recipient, treasury)
    assert claims_obj.proposal_id == "prop-honest-5m-grant"
    assert len(claims_obj.claims) == 3

    # Check token claim
    c1 = claims_obj.claims[0]
    assert isinstance(c1, TokenTransferClaim)
    assert c1.amount == 5_000_000 * 10**18
    assert c1.unit == "raw_tokens"
    assert c1.token == token
    assert c1.recipient == recipient

    # Check serialization round-trip
    data = claims_obj.to_dict()
    reloaded = load_claims_from_dict(data)
    assert reloaded.proposal_id == claims_obj.proposal_id
    assert len(reloaded.claims) == len(claims_obj.claims)


def test_load_forbid_ownership_claims():
    token = "0x4444444444444444444444444444444444444444"
    recipient = "0x3333333333333333333333333333333333333333"
    treasury = "0x1111111111111111111111111111111111111111"

    claims_obj = get_forbid_ownership_claims(token, recipient, treasury)
    forbidden_claims = [c for c in claims_obj.claims if isinstance(c, ForbiddenEffectClaim)]
    assert len(forbidden_claims) == 2
    types = {c.effect_type for c in forbidden_claims}
    assert ForbiddenEffectType.OWNERSHIP_CHANGE in types
    assert ForbiddenEffectType.UNAPPROVED_TRANSFER in types


def test_reject_unsupported_claim_type():
    raw = {
      "schema_version": "veritas-claims-v1.0",
      "proposal_id": "prop-test",
      "title": "Invalid Type Test",
      "claims": [
        {
          "claim_id": "c1",
          "type": "UNKNOWN_CLAIM_TYPE",
          "unit": "foo"
        }
      ]
    }
    with pytest.raises(ClaimsValidationError, match="unsupported claim type"):
        load_claims_from_dict(raw)


def test_reject_duplicate_claim_id():
    token = "0x4444444444444444444444444444444444444444"
    recipient = "0x3333333333333333333333333333333333333333"
    raw = {
      "schema_version": "veritas-claims-v1.0",
      "proposal_id": "prop-test",
      "title": "Duplicate ID Test",
      "claims": [
        {
          "claim_id": "claim-dup",
          "type": "TOKEN_TRANSFER",
          "unit": "raw_tokens",
          "token": token,
          "recipient": recipient,
          "amount": 100
        },
        {
          "claim_id": "claim-dup",
          "type": "TOKEN_TRANSFER",
          "unit": "raw_tokens",
          "token": token,
          "recipient": recipient,
          "amount": 200
        }
      ]
    }
    with pytest.raises(ClaimsValidationError, match="Duplicate claim_id detected"):
        load_claims_from_dict(raw)


def test_reject_missing_required_fields():
    raw = {
      "schema_version": "veritas-claims-v1.0",
      "proposal_id": "prop-test",
      "title": "Missing Field Test",
      "claims": [
        {
          "claim_id": "c1",
          "type": "TOKEN_TRANSFER",
          "unit": "raw_tokens",
          # missing token, recipient, amount
        }
      ]
    }
    with pytest.raises(ClaimsValidationError, match="missing required field"):
        load_claims_from_dict(raw)


def test_reject_invalid_schema_version():
    raw = {
      "schema_version": "veritas-claims-v99.0",
      "proposal_id": "prop-test",
      "title": "Bad Version",
      "claims": []
    }
    with pytest.raises(ClaimsValidationError, match="Unsupported schema_version"):
        load_claims_from_dict(raw)


def test_validate_claims_dict_helper():
    valid_data = get_honest_5m_grant_claims(
        "0x4444444444444444444444444444444444444444",
        "0x3333333333333333333333333333333333333333",
        "0x1111111111111111111111111111111111111111",
    ).to_dict()

    is_valid, errors = validate_claims_dict(valid_data)
    assert is_valid is True
    assert errors == []

    invalid_data = valid_data.copy()
    invalid_data["schema_version"] = "bad"
    is_valid, errors = validate_claims_dict(invalid_data)
    assert is_valid is False
    assert len(errors) > 0
