"""Unit tests for ReviewQueue state machine, authorization, and persistence."""

import tempfile
from pathlib import Path
import pytest
from analyzer.review_queue import (
    InvalidStateTransitionError,
    ItemNotFoundError,
    ReviewQueue,
    ReviewState,
    UnauthorizedReviewerError,
)
from analyzer.contract_adapter import ContractAdapter


def test_queue_enqueue_and_review_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "queue.json"
        authorized_reviewer = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
        queue = ReviewQueue(
            storage_path=str(storage_file),
            authorized_reviewers={authorized_reviewer},
        )

        # 1. Enqueue proposal
        item = queue.enqueue(
            proposal_id="PROP-LIFE-1",
            version=1,
            automated_verdict={"status": "NEEDS_REVIEW", "reason": "High risk pattern"},
        )
        assert item.state == ReviewState.PENDING.value

        # 2. Reject unauthorized reviewer
        with pytest.raises(UnauthorizedReviewerError):
            queue.post_review(
                proposal_id="PROP-LIFE-1",
                version=1,
                reviewer="0x000000000000000000000000000000000000dEaD",
                decision_str="APPROVE",
                reason="Looks good",
            )

        # 3. Reject empty reason
        with pytest.raises(ValueError, match="reason is mandatory"):
            queue.post_review(
                proposal_id="PROP-LIFE-1",
                version=1,
                reviewer=authorized_reviewer,
                decision_str="APPROVE",
                reason="   ",
            )

        # 4. Escalate decision
        item = queue.post_review(
            proposal_id="PROP-LIFE-1",
            version=1,
            reviewer=authorized_reviewer,
            decision_str="ESCALATE",
            reason="Requires second review",
        )
        assert item.state == ReviewState.ESCALATED.value
        assert len(item.reviews) == 1

        # 5. Final Approve decision
        item = queue.post_review(
            proposal_id="PROP-LIFE-1",
            version=1,
            reviewer=authorized_reviewer,
            decision_str="APPROVE",
            reason="Confirmed safe by lead auditor",
        )
        assert item.state == ReviewState.APPROVED.value
        assert len(item.reviews) == 2

        # 6. Reject subsequent review on terminal state
        with pytest.raises(InvalidStateTransitionError, match="terminal state"):
            queue.post_review(
                proposal_id="PROP-LIFE-1",
                version=1,
                reviewer=authorized_reviewer,
                decision_str="REJECT",
                reason="Too late to reject",
            )


def test_queue_persistence_and_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_file = Path(tmpdir) / "queue.json"
        authorized_reviewer = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"

        queue1 = ReviewQueue(
            storage_path=str(storage_file),
            authorized_reviewers={authorized_reviewer},
        )
        queue1.enqueue(
            proposal_id="PROP-PERSIST",
            version=1,
            automated_verdict={"status": "NEEDS_REVIEW"},
        )
        queue1.post_review(
            proposal_id="PROP-PERSIST",
            version=1,
            reviewer=authorized_reviewer,
            decision_str="APPROVE",
            reason="Audited and approved",
        )

        # Reload in a completely separate instance
        queue2 = ReviewQueue(
            storage_path=str(storage_file),
            authorized_reviewers={authorized_reviewer},
        )
        reloaded = queue2.get("PROP-PERSIST", 1)
        assert reloaded is not None
        assert reloaded.state == ReviewState.APPROVED.value
        assert len(reloaded.reviews) == 1
        assert reloaded.reviews[0].reason == "Audited and approved"


def test_contract_adapter_rpc_failure_handling():
    # Pointing to inactive port
    adapter = ContractAdapter(rpc_url="http://127.0.0.1:59999", oracle_address="0x1111111111111111111111111111111111111111")
    assert adapter.is_connected() is False

    tx_hash, confirmed, err = adapter.post_review_on_chain(
        proposal_id_bytes32=b"P" * 32,
        version=1,
        reviewer_address="0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
        decision_str="APPROVE",
        reason_hash_bytes32=b"R" * 32,
    )

    assert tx_hash is None
    assert confirmed is False
    assert err == "Not connected to local Anvil RPC"
