"""Human review queue for Veritas Gate Phase 5.

Manages proposals requiring human inspection (e.g., NEEDS_REVIEW status),
tracks decision states (PENDING, APPROVED, REJECTED, ESCALATED),
enforces reviewer authorization, preserves complete auditable review history,
and persists state atomically to local disk.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("veritas.review_queue")


class ReviewState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"


class ReviewDecision(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


class ReviewQueueError(Exception):
    """Base error for review queue operations."""


class UnauthorizedReviewerError(ReviewQueueError):
    """Raised when an unauthorized address attempts to submit a review."""


class InvalidStateTransitionError(ReviewQueueError):
    """Raised on invalid review state transition."""


class ItemNotFoundError(ReviewQueueError):
    """Raised when an item is not found in the queue."""


@dataclass
class ReviewRecord:
    reviewer: str
    decision: str
    reason: str
    reason_hash: str
    timestamp: float
    evidence_refs: List[str] = field(default_factory=list)
    tx_hash: Optional[str] = None
    on_chain_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QueueItem:
    proposal_id: str
    version: int
    state: str
    automated_verdict: Dict[str, Any]
    reviews: List[ReviewRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def key(self) -> str:
        return f"{self.proposal_id}:{self.version}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "version": self.version,
            "state": self.state,
            "automated_verdict": self.automated_verdict,
            "reviews": [r.to_dict() for r in self.reviews],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QueueItem:
        reviews = [
            ReviewRecord(
                reviewer=r["reviewer"],
                decision=r["decision"],
                reason=r["reason"],
                reason_hash=r.get("reason_hash", ""),
                timestamp=r["timestamp"],
                evidence_refs=r.get("evidence_refs", []),
                tx_hash=r.get("tx_hash"),
                on_chain_confirmed=r.get("on_chain_confirmed", False),
            )
            for r in data.get("reviews", [])
        ]
        return cls(
            proposal_id=data["proposal_id"],
            version=int(data["version"]),
            state=data.get("state", ReviewState.PENDING.value),
            automated_verdict=data.get("automated_verdict", {}),
            reviews=reviews,
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


class ReviewQueue:
    """In-memory review queue backed by atomic JSON disk persistence."""

    def __init__(
        self,
        storage_path: Optional[str] = None,
        authorized_reviewers: Optional[Set[str]] = None,
    ):
        self.storage_path = Path(storage_path) if storage_path else None
        self._items: Dict[str, QueueItem] = {}

        # Default local authorized reviewers (Anvil default accounts)
        self.authorized_reviewers: Set[str] = {
            r.lower()
            for r in (
                authorized_reviewers
                or {
                    "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",  # Anvil 0
                    "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",  # Anvil 1
                    "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc",  # Anvil 2
                }
            )
        }

        if self.storage_path:
            self._load()

    def enqueue(
        self,
        proposal_id: str,
        version: int,
        automated_verdict: Dict[str, Any],
    ) -> QueueItem:
        """Enqueues a proposal version for human review."""
        if not proposal_id or not isinstance(proposal_id, str):
            raise ValueError("proposal_id must be a non-empty string")
        if not isinstance(version, int) or version <= 0:
            raise ValueError("version must be a positive integer")

        key = f"{proposal_id}:{version}"
        if key in self._items:
            # Already queued; return existing item without modifying
            return self._items[key]

        item = QueueItem(
            proposal_id=proposal_id,
            version=version,
            state=ReviewState.PENDING.value,
            automated_verdict=automated_verdict,
        )
        self._items[key] = item
        self._persist()
        logger.info("Enqueued proposal %s v%d for review", proposal_id, version)
        return item

    def post_review(
        self,
        proposal_id: str,
        version: int,
        reviewer: str,
        decision_str: str,
        reason: str,
        evidence_refs: Optional[List[str]] = None,
        tx_hash: Optional[str] = None,
        on_chain_confirmed: bool = False,
    ) -> QueueItem:
        """Appends a human review decision and updates the queue item's status."""
        key = f"{proposal_id}:{version}"
        if key not in self._items:
            raise ItemNotFoundError(f"No queued item found for proposal {proposal_id} v{version}")

        # 1. Validate reviewer address & authorization
        clean_reviewer = self._validate_address(reviewer)
        if clean_reviewer not in self.authorized_reviewers:
            raise UnauthorizedReviewerError(f"Address {reviewer} is not an authorized reviewer")

        # 2. Validate non-empty reason
        if not reason or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Reviewer reason is mandatory and cannot be empty")

        # 3. Validate decision
        try:
            decision = ReviewDecision(decision_str.upper())
        except ValueError:
            raise ValueError(f"Invalid decision '{decision_str}'. Supported: APPROVE, REJECT, ESCALATE")

        item = self._items[key]

        # 4. Validate state transition & verdict eligibility
        current_state = ReviewState(item.state)
        if current_state in (ReviewState.APPROVED, ReviewState.REJECTED):
            raise InvalidStateTransitionError(
                f"Cannot review proposal in terminal state {current_state.value}"
            )

        # MISMATCH cannot be overturned with APPROVE (invariant matching VerdictOracle.sol)
        verdict_status = str(item.automated_verdict.get("status", "")).upper()
        if verdict_status == "MISMATCH" and decision == ReviewDecision.APPROVE:
            raise InvalidStateTransitionError(
                "MISMATCH automated verdict indicates proven divergence; cannot be APPROVED"
            )

        # 5. Determine new state
        if decision == ReviewDecision.APPROVE:
            new_state = ReviewState.APPROVED
        elif decision == ReviewDecision.REJECT:
            new_state = ReviewState.REJECTED
        elif decision == ReviewDecision.ESCALATE:
            new_state = ReviewState.ESCALATED
        else:
            raise InvalidStateTransitionError(f"Unexpected decision {decision}")

        # 6. Compute reason hash (keccak256 or sha256 compatible)
        import hashlib
        reason_hash = "0x" + hashlib.sha256(reason.strip().encode("utf-8")).hexdigest()

        # 7. Append to review history (IMMUTABLE LOG)
        record = ReviewRecord(
            reviewer=clean_reviewer,
            decision=decision.value,
            reason=reason.strip(),
            reason_hash=reason_hash,
            timestamp=time.time(),
            evidence_refs=evidence_refs or [],
            tx_hash=tx_hash,
            on_chain_confirmed=on_chain_confirmed,
        )
        item.reviews.append(record)
        item.state = new_state.value
        item.updated_at = time.time()

        self._persist()
        logger.info(
            "Review recorded for %s v%d: %s by %s",
            proposal_id,
            version,
            decision.value,
            clean_reviewer,
        )
        return item

    def get(self, proposal_id: str, version: int) -> Optional[QueueItem]:
        return self._items.get(f"{proposal_id}:{version}")

    def list_items(self, state_filter: Optional[str] = None) -> List[QueueItem]:
        """Returns queued items, optionally filtered by state."""
        items = list(self._items.values())
        if state_filter:
            upper_filter = state_filter.upper()
            return [it for it in items if it.state == upper_filter]
        return items

    def get_summary(self) -> Dict[str, int]:
        """Returns count of review queue items categorized by state."""
        summary = {
            "total": len(self._items),
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "escalated": 0,
        }
        for it in self._items.values():
            s = it.state.lower()
            if s in summary:
                summary[s] += 1
        return summary

    def update_on_chain_confirmation(
        self,
        proposal_id: str,
        version: int,
        tx_hash: str,
        confirmed: bool,
    ) -> bool:
        """Updates on-chain transaction confirmation status for latest review."""
        item = self.get(proposal_id, version)
        if not item or not item.reviews:
            return False
        latest_rev = item.reviews[-1]
        latest_rev.tx_hash = tx_hash
        latest_rev.on_chain_confirmed = confirmed
        item.updated_at = time.time()
        self._persist()
        return True

    def _validate_address(self, addr: str) -> str:
        if not isinstance(addr, str) or not re.match(r"^0x[0-9a-fA-F]{40}$", addr):
            raise ValueError(f"Invalid Ethereum address: {addr}")
        return addr.lower()

    def _persist(self) -> None:
        """Atomically persists queue state to disk."""
        if not self.storage_path:
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        raw_data = {k: v.to_dict() for k, v in self._items.items()}

        # Safe atomic write via temporary file
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(self.storage_path.parent),
            prefix="review_queue_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2)
            os.replace(temp_path, str(self.storage_path))
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            logger.error("Failed to persist review queue: %s", e)
            raise ReviewQueueError(f"Persistence error: {e}")

    def _load(self) -> None:
        """Loads queue state from disk."""
        if not self.storage_path or not self.storage_path.is_file():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self._items = {k: QueueItem.from_dict(v) for k, v in raw_data.items()}
            logger.info("Loaded %d items into review queue from disk", len(self._items))
        except Exception as e:
            logger.error("Failed to load review queue from %s: %s", self.storage_path, e)
            raise ReviewQueueError(f"Error loading review queue: {e}")
