"""Evidence Provenance and Artifact Manifest module for Veritas Gate Phase 5.

Maintains cryptographic proof of proposal text, supporting documentation,
and simulation analysis outputs. Verifies content integrity against supplied hashes,
detects tampering, and distinguishes source metadata from verified factual claims.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("veritas.provenance")


class ProvenanceError(Exception):
    """Base error for evidence provenance."""


class TamperedContentError(ProvenanceError):
    """Raised when supplied content hash does not match expected cryptographic hash."""


@dataclass
class EvidenceItem:
    item_id: str
    proposal_id: str
    version: int
    media_type: str
    source_uri: str
    content_hash: str
    retrieval_timestamp: float
    integrity_verified: bool = False
    disclaimer: str = (
        "Cryptographic content integrity validates byte fidelity to source; "
        "it does NOT verify the factual truth of claims made within the source text."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceProvenance:
    """Stores and verifies evidence artifacts associated with proposal versions."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else None
        # key: f"{proposal_id}:{version}" => List[EvidenceItem]
        self._manifests: Dict[str, List[EvidenceItem]] = {}
        if self.storage_path:
            self._load()

    def register_evidence(
        self,
        proposal_id: str,
        version: int,
        item_id: str,
        media_type: str,
        source_uri: str,
        content: Optional[bytes] = None,
        expected_hash: Optional[str] = None,
    ) -> EvidenceItem:
        """Registers an evidence item and verifies hash integrity if content is provided."""
        if not proposal_id or not isinstance(proposal_id, str):
            raise ValueError("proposal_id must be a non-empty string")
        if not isinstance(version, int) or version <= 0:
            raise ValueError("version must be a positive integer")
        if not item_id or not isinstance(item_id, str):
            raise ValueError("item_id must be a non-empty string")

        computed_hash: Optional[str] = None
        integrity_verified = False

        if content is not None:
            computed_hash = "0x" + hashlib.sha256(content).hexdigest()
            if expected_hash:
                expected_clean = expected_hash.lower()
                if not expected_clean.startswith("0x"):
                    expected_clean = "0x" + expected_clean
                if computed_hash != expected_clean:
                    raise TamperedContentError(
                        f"Content hash mismatch for {item_id}: computed {computed_hash}, expected {expected_hash}"
                    )
            integrity_verified = True
        elif expected_hash:
            computed_hash = expected_hash if expected_hash.startswith("0x") else "0x" + expected_hash
            integrity_verified = False
        else:
            raise ValueError("Must provide either content bytes or expected_hash")

        item = EvidenceItem(
            item_id=item_id,
            proposal_id=proposal_id,
            version=version,
            media_type=media_type,
            source_uri=source_uri,
            content_hash=computed_hash,
            retrieval_timestamp=time.time(),
            integrity_verified=integrity_verified,
        )

        key = f"{proposal_id}:{version}"
        if key not in self._manifests:
            self._manifests[key] = []

        # Avoid duplicate item_id in same version
        self._manifests[key] = [it for it in self._manifests[key] if it.item_id != item_id]
        self._manifests[key].append(item)

        self._persist()
        logger.info(
            "Registered evidence item %s for proposal %s v%d (verified=%s)",
            item_id,
            proposal_id,
            version,
            integrity_verified,
        )
        return item

    def get_manifest(self, proposal_id: str, version: int) -> List[EvidenceItem]:
        """Retrieves all evidence items for a proposal version."""
        key = f"{proposal_id}:{version}"
        return list(self._manifests.get(key, []))

    def _persist(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        raw_data = {
            k: [it.to_dict() for it in items]
            for k, items in self._manifests.items()
        }
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(self.storage_path.parent),
            prefix="provenance_",
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
            logger.error("Failed to persist evidence provenance: %s", e)
            raise ProvenanceError(f"Persistence error: {e}")

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.is_file():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            self._manifests = {}
            for k, items in raw_data.items():
                self._manifests[k] = [
                    EvidenceItem(
                        item_id=it["item_id"],
                        proposal_id=it["proposal_id"],
                        version=it["version"],
                        media_type=it["media_type"],
                        source_uri=it["source_uri"],
                        content_hash=it["content_hash"],
                        retrieval_timestamp=it["retrieval_timestamp"],
                        integrity_verified=it.get("integrity_verified", False),
                    )
                    for it in items
                ]
            logger.info("Loaded evidence manifests for %d proposal versions", len(self._manifests))
        except Exception as e:
            logger.error("Failed to load provenance from %s: %s", self.storage_path, e)
            raise ProvenanceError(f"Error loading provenance: {e}")
