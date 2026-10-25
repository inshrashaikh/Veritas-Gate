"""
tests/test_determinism.py
=========================
Tests verifying that Veritas Gate Phase 3 comparison engine is purely deterministic:
- Identical inputs always yield bit-for-bit identical results.
- Key ordering in JSON or dict inputs does not alter verdict or reason code.
- No randomness, external network calls, or LLM non-determinism exist.
"""

import json
from pathlib import Path
import random
import pytest

from analyzer import Verdict, compare

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def read_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def test_identical_inputs_identical_results_repeated():
    """Prove 100 repeated runs of compare() return identical results."""
    claims_json = read_fixture("claims_honest_5m_grant.json")
    sim_json = read_fixture("simulation_honest.json")

    baseline = compare(claims_json, sim_json)
    baseline_dict = baseline.to_dict()
    baseline_json = baseline.to_json()

    for i in range(100):
        run_res = compare(claims_json, sim_json)
        assert run_res.verdict == baseline.verdict, f"Run {i} verdict differed"
        assert run_res.reason_code == baseline.reason_code, f"Run {i} reason differed"
        assert run_res.to_dict() == baseline_dict, f"Run {i} dict representation differed"
        assert run_res.to_json() == baseline_json, f"Run {i} JSON representation differed"


def test_determinism_across_all_fixtures():
    """Verify determinism across all fixture types."""
    fixture_pairs = [
        ("claims_honest_5m_grant.json", "simulation_honest.json", Verdict.VERIFIED),
        ("claims_honest_5m_grant.json", "simulation_malicious.json", Verdict.MISMATCH),
        ("claims_honest_5m_grant.json", "simulation_risky_delegatecall.json", Verdict.NEEDS_REVIEW),
        ("claims_honest_5m_grant.json", "simulation_incomplete_trace.json", Verdict.NEEDS_REVIEW),
        ("claims_honest_5m_grant.json", "simulation_reverted.json", Verdict.NEEDS_REVIEW),
        ("claims_honest_5m_grant.json", "simulation_unexpected_transfer.json", Verdict.MISMATCH),
        ("claims_honest_5m_grant.json", "simulation_missing_fields.json", Verdict.NEEDS_REVIEW),
        ("claims_ambiguous.json", "simulation_honest.json", Verdict.NEEDS_REVIEW),
        ("claims_unsupported_type.json", "simulation_honest.json", Verdict.NEEDS_REVIEW),
        ("claims_forbid_ownership.json", "simulation_honest.json", Verdict.VERIFIED),
        ("claims_forbid_ownership.json", "simulation_malicious.json", Verdict.MISMATCH),
    ]

    for claims_file, sim_file, expected_verdict in fixture_pairs:
        claims_str = read_fixture(claims_file)
        sim_str = read_fixture(sim_file)

        res1 = compare(claims_str, sim_str)
        res2 = compare(claims_str, sim_str)

        assert res1.verdict == expected_verdict, f"Mismatch on {claims_file} + {sim_file}"
        assert res1.verdict == res2.verdict
        assert res1.reason_code == res2.reason_code
        assert res1.to_dict() == res2.to_dict()


def test_dict_key_ordering_independence():
    """Verify that JSON key permutation does not affect output."""
    claims_raw = json.loads(read_fixture("claims_honest_5m_grant.json"))
    sim_raw = json.loads(read_fixture("simulation_honest.json"))

    # Shuffled key dictionary
    def shuffle_keys(d):
        if not isinstance(d, dict):
            return d
        items = list(d.items())
        random.seed(42)
        random.shuffle(items)
        return {k: shuffle_keys(v) if isinstance(v, dict) else v for k, v in items}

    shuffled_claims = shuffle_keys(claims_raw)
    shuffled_sim = shuffle_keys(sim_raw)

    baseline = compare(claims_raw, sim_raw)
    shuffled_result = compare(shuffled_claims, shuffled_sim)

    assert baseline.verdict == shuffled_result.verdict
    assert baseline.reason_code == shuffled_result.reason_code
    assert baseline.matched_claims == shuffled_result.matched_claims
