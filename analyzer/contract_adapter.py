"""Local Ethereum chain adapter for Veritas Gate Phase 4 contracts.

Provides local-only RPC interaction with ProposalRegistry, VerdictOracle, and GuardedTreasury.
Uses local Anvil accounts without requesting or storing private keys.
Distinguishes off-chain queue status from confirmed on-chain transactions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from web3 import Web3

logger = logging.getLogger("veritas.contract_adapter")
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ContractAdapterError(Exception):
    """Base error for contract adapter operations."""


class ContractAdapter:
    """Interacts with Phase 4 contracts on a local Anvil node."""

    def __init__(
        self,
        rpc_url: str = "http://127.0.0.1:8545",
        registry_address: Optional[str] = None,
        oracle_address: Optional[str] = None,
        treasury_address: Optional[str] = None,
    ):
        self.rpc_url = rpc_url
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))

        # Enforce local RPC constraint
        lower = rpc_url.lower()
        if not ("://127.0.0.1" in lower or "://localhost" in lower or "://[::1]" in lower):
            raise ValueError(f"ContractAdapter can only connect to local Anvil RPC, attempted: {rpc_url}")

        self.registry_address = Web3.to_checksum_address(registry_address) if registry_address else None
        self.oracle_address = Web3.to_checksum_address(oracle_address) if oracle_address else None
        self.treasury_address = Web3.to_checksum_address(treasury_address) if treasury_address else None

        self._load_abis()

    def _load_abis(self) -> None:
        def load_abi(filename: str, name: str) -> List[Dict[str, Any]]:
            p = PROJECT_ROOT / "out" / filename / f"{name}.json"
            if p.is_file():
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f).get("abi", [])
            return []

        self.registry_abi = load_abi("ProposalRegistry.sol", "ProposalRegistry")
        self.oracle_abi = load_abi("VerdictOracle.sol", "VerdictOracle")
        self.treasury_abi = load_abi("GuardedTreasury.sol", "GuardedTreasury")

    def is_connected(self) -> bool:
        try:
            return bool(self.w3.is_connected())
        except Exception:
            return False

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    def get_on_chain_proposal(self, proposal_id_bytes32: bytes, version: int) -> Optional[Dict[str, Any]]:
        """Reads proposal version details from ProposalRegistry."""
        if not self.registry_address or not self.is_connected():
            return None
        contract = self.w3.eth.contract(address=self.registry_address, abi=self.registry_abi)
        try:
            pv = contract.functions.getProposalVersion(proposal_id_bytes32, version).call()
            return {
                "version": pv[0],
                "text_hash": "0x" + pv[1].hex(),
                "calldata_hash": "0x" + pv[2].hex(),
                "disclosed_wallets": list(pv[3]),
                "timestamp": pv[4],
                "author": pv[5],
            }
        except Exception as e:
            logger.debug("Failed to read proposal from registry: %s", e)
            return None

    def get_on_chain_verdict(self, proposal_id_bytes32: bytes, version: int) -> Optional[Dict[str, Any]]:
        """Reads automated verdict from VerdictOracle."""
        if not self.oracle_address or not self.is_connected():
            return None
        contract = self.w3.eth.contract(address=self.oracle_address, abi=self.oracle_abi)
        try:
            v = contract.functions.getVerdict(proposal_id_bytes32, version).call()
            status_map = {0: "NONE", 1: "VERIFIED", 2: "MISMATCH", 3: "NEEDS_REVIEW"}
            return {
                "status": status_map.get(v[0], "UNKNOWN"),
                "text_hash": "0x" + v[1].hex(),
                "calldata_hash": "0x" + v[2].hex(),
                "evidence_hash": "0x" + v[3].hex(),
                "timestamp": v[4],
                "finalized": v[5] == 1,
            }
        except Exception as e:
            logger.debug("Failed to read verdict from oracle: %s", e)
            return None

    def is_on_chain_eligible(self, proposal_id_bytes32: bytes, version: int) -> Tuple[bool, str]:
        """Checks if proposal version is eligible for execution per VerdictOracle."""
        if not self.oracle_address or not self.is_connected():
            return (False, "Contract adapter not connected or oracle address unconfigured")
        contract = self.w3.eth.contract(address=self.oracle_address, abi=self.oracle_abi)
        try:
            return contract.functions.isEligibleForExecution(proposal_id_bytes32, version).call()
        except Exception as e:
            return (False, f"RPC query failed: {e}")

    def get_on_chain_review(self, proposal_id_bytes32: bytes, version: int) -> Optional[Dict[str, Any]]:
        """Reads latest human review decision from VerdictOracle."""
        if not self.oracle_address or not self.is_connected():
            return None
        contract = self.w3.eth.contract(address=self.oracle_address, abi=self.oracle_abi)
        try:
            r = contract.functions.getLatestReview(proposal_id_bytes32, version).call()
            decision_map = {0: "NONE", 1: "APPROVE", 2: "REJECT", 3: "ESCALATE"}
            return {
                "reviewer": r[0],
                "decision": decision_map.get(r[1], "UNKNOWN"),
                "reason_hash": "0x" + r[2].hex(),
                "timestamp": r[3],
            }
        except Exception as e:
            logger.debug("Failed to read latest review from oracle: %s", e)
            return None

    def get_on_chain_challenge_status(self, proposal_id_bytes32: bytes, version: int) -> Dict[str, Any]:
        """Reads active challenge and disqualification state from VerdictOracle."""
        if not self.oracle_address or not self.is_connected():
            return {"active_challenge": False, "disqualified": False, "connected": False}
        contract = self.w3.eth.contract(address=self.oracle_address, abi=self.oracle_abi)
        try:
            active = contract.functions.hasActiveChallenge(proposal_id_bytes32, version).call()
            disqualified = contract.functions.isDisqualified(proposal_id_bytes32, version).call()
            return {"active_challenge": active, "disqualified": disqualified, "connected": True}
        except Exception as e:
            logger.debug("Failed to query challenge status: %s", e)
            return {"active_challenge": False, "disqualified": False, "connected": False, "error": str(e)}

    def get_treasury_status(
        self,
        proposal_id_bytes32: Optional[bytes] = None,
        version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Reads emergency pause state and execution status from GuardedTreasury."""
        if not self.treasury_address or not self.is_connected():
            return {"is_paused": False, "connected": False}
        contract = self.w3.eth.contract(address=self.treasury_address, abi=self.treasury_abi)
        try:
            paused = contract.functions.isPaused().call()
            reason_hash = contract.functions.pauseReasonHash().call()
            challenge_window = contract.functions.challengeWindow().call()
            result = {
                "is_paused": paused,
                "pause_reason_hash": "0x" + reason_hash.hex() if hasattr(reason_hash, "hex") else str(reason_hash),
                "challenge_window": challenge_window,
                "connected": True,
            }
            if proposal_id_bytes32 is not None and version is not None:
                executed = contract.functions.executed(proposal_id_bytes32, version).call()
                authorized = contract.functions.authorizedProposals(proposal_id_bytes32, version).call()
                result["executed"] = executed
                result["authorized"] = authorized
            return result
        except Exception as e:
            logger.debug("Failed to query treasury status: %s", e)
            return {"is_paused": False, "connected": False, "error": str(e)}

    def verify_on_chain_hashes(
        self,
        proposal_id_bytes32: bytes,
        expected_text_hash: bytes,
        expected_calldata_hash: bytes,
    ) -> Tuple[bool, int]:
        """Verifies text and calldata hashes against ProposalRegistry on chain."""
        if not self.registry_address or not self.is_connected():
            return False, 0
        contract = self.w3.eth.contract(address=self.registry_address, abi=self.registry_abi)
        try:
            return contract.functions.verifyLatestHashes(
                proposal_id_bytes32,
                expected_text_hash,
                expected_calldata_hash,
            ).call()
        except Exception as e:
            logger.debug("Failed to verify hashes on registry: %s", e)
            return False, 0

    # =========================================================================
    # WRITE OPERATIONS (Operator-requested, local Anvil accounts only)
    # =========================================================================

    def post_review_on_chain(
        self,
        proposal_id_bytes32: bytes,
        version: int,
        reviewer_address: str,
        decision_str: str,
        reason_hash_bytes32: bytes,
    ) -> Tuple[Optional[str], bool, Optional[str]]:
        """Submits human review to VerdictOracle using unlocked reviewer address on Anvil.

        Returns: (tx_hash, confirmed, error_message)
        """
        if not self.oracle_address:
            return None, False, "Oracle address not configured"
        if not self.is_connected():
            return None, False, "Not connected to local Anvil RPC"

        decision_map = {"APPROVE": 1, "REJECT": 2, "ESCALATE": 3}
        decision_enum = decision_map.get(decision_str.upper())
        if not decision_enum:
            return None, False, f"Invalid decision {decision_str}"

        contract = self.w3.eth.contract(address=self.oracle_address, abi=self.oracle_abi)
        reviewer_checksum = Web3.to_checksum_address(reviewer_address)

        try:
            # Unlock/impersonate account on Anvil
            self.w3.provider.make_request("anvil_impersonateAccount", [reviewer_checksum])
            self.w3.provider.make_request("anvil_setBalance", [reviewer_checksum, hex(10**19)])

            tx_hash = contract.functions.postReview(
                proposal_id_bytes32,
                version,
                decision_enum,
                reason_hash_bytes32,
            ).transact({"from": reviewer_checksum, "gas": 500_000})

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=5)
            confirmed = receipt.status == 1
            return tx_hash.hex(), confirmed, None if confirmed else "Transaction reverted on chain"
        except Exception as e:
            logger.error("Failed to post review on-chain: %s", e)
            return None, False, str(e)
