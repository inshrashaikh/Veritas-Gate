"""Unit tests for Evidence Provenance and content integrity verification."""

import tempfile
from pathlib import Path
import pytest
from analyzer.provenance import EvidenceProvenance, TamperedContentError


def test_register_and_verify_evidence():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "provenance.json"
        prov = EvidenceProvenance(str(storage_path))

        content = b"Grant proposal research paper details"
        import hashlib
        expected_hash = "0x" + hashlib.sha256(content).hexdigest()

        item = prov.register_evidence(
            proposal_id="PROPOSAL-EVID-1",
            version=1,
            item_id="paper_pdf",
            media_type="application/pdf",
            source_uri="ipfs://QmTest123",
            content=content,
            expected_hash=expected_hash,
        )

        assert item.item_id == "paper_pdf"
        assert item.integrity_verified is True
        assert item.content_hash == expected_hash

        manifest = prov.get_manifest("PROPOSAL-EVID-1", 1)
        assert len(manifest) == 1
        assert manifest[0].item_id == "paper_pdf"


def test_reject_tampered_content():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "provenance.json"
        prov = EvidenceProvenance(str(storage_path))

        actual_content = b"Malicious modified payload text"
        faked_hash = "0x" + "a" * 64

        with pytest.raises(TamperedContentError, match="Content hash mismatch"):
            prov.register_evidence(
                proposal_id="PROPOSAL-TAMPER",
                version=1,
                item_id="tampered_doc",
                media_type="text/plain",
                source_uri="local://test",
                content=actual_content,
                expected_hash=faked_hash,
            )


def test_provenance_persistence_reload():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = Path(tmpdir) / "provenance.json"
        prov1 = EvidenceProvenance(str(storage_path))

        prov1.register_evidence(
            proposal_id="PROPOSAL-PERSIST",
            version=1,
            item_id="doc1",
            media_type="text/plain",
            source_uri="local://doc1.txt",
            content=b"Persistent content",
        )

        # Reload with new instance from same storage file
        prov2 = EvidenceProvenance(str(storage_path))
        items = prov2.get_manifest("PROPOSAL-PERSIST", 1)
        assert len(items) == 1
        assert items[0].item_id == "doc1"
        assert items[0].integrity_verified is True
