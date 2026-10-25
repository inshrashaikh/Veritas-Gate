"""Local EVM simulation engine for Veritas Gate Phase 2.

Executes proposals against local Anvil nodes, records observable state diffs,
fetches opcode/call traces, applies security rules, and emits veritas.simulation.v1 JSON.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

from analyzer.schemas import (
    SCHEMA_VERSION,
    EffectDiff,
    EffectType,
    ScenarioConfig,
    SimulationMode,
    SimulationResult,
)
from analyzer.trace_rules import TraceAnalyzer

logger = logging.getLogger("veritas.analyzer")


class SimulationError(Exception):
    """Base error during simulation."""


class RPCConnectionError(SimulationError):
    """Raised when connection to local RPC fails."""


class ChainIdMismatchError(SimulationError):
    """Raised when node chain ID does not match scenario chain ID."""


class AnvilRPCClient:
    """Lightweight JSON-RPC client for Anvil / EVM interaction with strict local bounds."""

    def __init__(self, rpc_url: str = "http://127.0.0.1:8545", timeout_sec: int = 15):
        self.rpc_url = rpc_url
        self.timeout_sec = timeout_sec
        self._req_id = 0

    def call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        """Sends a JSON-RPC request to the local node."""
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params or [],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.rpc_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as response:
                body = response.read().decode("utf-8")
                res = json.loads(body)
                if "error" in res:
                    err = res["error"]
                    err_msg = err.get("message", str(err))
                    raise SimulationError(f"RPC method '{method}' returned error: {err_msg}")
                return res.get("result")
        except urllib.error.URLError as e:
            raise RPCConnectionError(f"Failed to connect to local RPC at {self.rpc_url}: {e.reason}")
        except json.JSONDecodeError as e:
            raise SimulationError(f"Failed to parse JSON-RPC response from {self.rpc_url}: {e}")


class Simulator:
    """Executes a scenario against Anvil and produces a standardized SimulationResult."""

    def __init__(self, scenario: ScenarioConfig, client: Optional[AnvilRPCClient] = None):
        self.scenario = scenario
        self.scenario.validate()
        self.client = client or AnvilRPCClient(self.scenario.rpc_url)

    def run(self) -> SimulationResult:
        """Executes the simulation workflow."""
        errors: List[str] = []

        # 1. Verify chain ID
        try:
            actual_chain_id_hex = self.client.call("eth_chainId")
            actual_chain_id = int(actual_chain_id_hex, 16) if isinstance(actual_chain_id_hex, str) else int(actual_chain_id_hex)
            if actual_chain_id != self.scenario.chain_id:
                raise ChainIdMismatchError(
                    f"Chain ID mismatch: scenario expects chain_id {self.scenario.chain_id}, "
                    f"but connected RPC node has chain_id {actual_chain_id}."
                )
        except Exception as e:
            errors.append(str(e))
            return SimulationResult(
                schema_version=SCHEMA_VERSION,
                scenario_id=self.scenario.scenario_id,
                chain_id=self.scenario.chain_id,
                simulation_mode=self.scenario.simulation_mode.value,
                success=False,
                state_diffs=[],
                logs=[],
                trace_complete=False,
                findings=[],
                errors=errors,
            )

        # 2. Capture baseline state
        try:
            baseline_state = self._capture_state()
        except Exception as e:
            errors.append(f"Failed to capture baseline state: {e}")
            return SimulationResult(
                schema_version=SCHEMA_VERSION,
                scenario_id=self.scenario.scenario_id,
                chain_id=self.scenario.chain_id,
                simulation_mode=self.scenario.simulation_mode.value,
                success=False,
                state_diffs=[],
                logs=[],
                trace_complete=False,
                findings=[],
                errors=errors,
            )

        # 3. Execute according to simulation mode
        if self.scenario.simulation_mode == SimulationMode.READ_ONLY:
            return self._execute_read_only(baseline_state)
        else:
            return self._execute_stateful(baseline_state)

    def _execute_read_only(self, baseline_state: Dict[str, Any]) -> SimulationResult:
        """Simulates transaction via read-only eth_call."""
        errors: List[str] = []
        success = False
        tx_obj = {
            "from": self.scenario.sender,
            "to": self.scenario.target,
            "data": self.scenario.calldata,
            "value": hex(self.scenario.value),
        }

        try:
            ret = self.client.call("eth_call", [tx_obj, "latest"])
            success = True
            logger.info("Read-only simulation returned: %s", ret)
        except Exception as e:
            success = False
            errors.append(f"Read-only execution reverted or failed: {e}")

        # In pure read-only mode, on-chain state does not change, but we report trace limitations
        trace_complete = False
        trace_reason = "Opcode-level tracing is not recorded in read-only eth_call mode."
        trace_analyzer = TraceAnalyzer(raw_trace=None, is_complete=trace_complete, trace_error=trace_reason)
        _, findings, trace_errors = trace_analyzer.analyze(logs=[], state_diffs=[])
        errors.extend(trace_errors)

        return SimulationResult(
            schema_version=SCHEMA_VERSION,
            scenario_id=self.scenario.scenario_id,
            chain_id=self.scenario.chain_id,
            simulation_mode=self.scenario.simulation_mode.value,
            success=success,
            state_diffs=[],
            logs=[],
            trace_complete=trace_complete,
            findings=[f.to_dict() for f in findings],
            errors=errors,
        )

    def _execute_stateful(self, baseline_state: Dict[str, Any]) -> SimulationResult:
        """Executes transaction against local Anvil inside a snapshot/revert sandbox."""
        errors: List[str] = []
        snapshot_id: Optional[str] = None
        logs: List[Dict[str, Any]] = []
        state_diffs: List[EffectDiff] = []
        raw_trace: Optional[Any] = None
        trace_complete = False
        trace_error: Optional[str] = None
        success = False

        # Take Anvil snapshot
        try:
            snapshot_id = self.client.call("evm_snapshot")
        except Exception as e:
            errors.append(f"Failed to create Anvil snapshot: {e}")
            return SimulationResult(
                schema_version=SCHEMA_VERSION,
                scenario_id=self.scenario.scenario_id,
                chain_id=self.scenario.chain_id,
                simulation_mode=self.scenario.simulation_mode.value,
                success=False,
                state_diffs=[],
                logs=[],
                trace_complete=False,
                findings=[],
                errors=errors,
            )

        try:
            # Impersonate sender and ensure sender has sufficient native gas funds
            try:
                self.client.call("anvil_impersonateAccount", [self.scenario.sender])
                # Provide 100 ETH for gas if sender is empty
                self.client.call("anvil_setBalance", [self.scenario.sender, hex(100 * 10**18)])
            except Exception as e:
                logger.debug("Optional anvil impersonation call failed (might be unlocked): %s", e)

            # Send transaction
            tx_payload = {
                "from": self.scenario.sender,
                "to": self.scenario.target,
                "data": self.scenario.calldata,
                "value": hex(self.scenario.value),
                "gas": hex(5_000_000),
            }

            tx_hash: Optional[str] = None
            try:
                tx_hash = self.client.call("eth_sendTransaction", [tx_payload])
            except Exception as e:
                errors.append(f"Transaction submission failed: {e}")
                success = False

            if tx_hash:
                # Retrieve receipt with polling and optional evm_mine trigger
                receipt = None
                for _ in range(40):
                    receipt = self.client.call("eth_getTransactionReceipt", [tx_hash])
                    if receipt is not None:
                        break
                    try:
                        self.client.call("evm_mine")
                    except Exception:
                        pass
                    time.sleep(0.05)

                if receipt:
                    raw_status = receipt.get("status")
                    success = (raw_status == "0x1" or raw_status == 1)
                    logs = receipt.get("logs", [])

                    if not success:
                        revert_msg = "Transaction execution reverted (receipt status 0x0)"
                        try:
                            self.client.call("eth_call", [tx_payload, "latest"])
                        except Exception as rev_err:
                            revert_msg = f"Transaction reverted: {rev_err}"
                        errors.append(revert_msg)
                else:
                    errors.append(f"Receipt not found for tx_hash {tx_hash}")

                # Capture post-execution state
                resulting_state = self._capture_state()
                state_diffs = self._compute_diffs(baseline_state, resulting_state)

                # Attempt to retrieve trace
                raw_trace, trace_complete, trace_error = self._fetch_trace(tx_hash)

        except Exception as e:
            errors.append(f"Unexpected simulation error during execution: {e}")
            success = False
        finally:
            # RESTORE SNAPSHOT unconditionally
            if snapshot_id is not None:
                try:
                    revert_success = self.client.call("evm_revert", [snapshot_id])
                    if not revert_success:
                        errors.append(f"Anvil snapshot revert returned false for snapshot {snapshot_id}.")
                except Exception as e:
                    errors.append(f"Failed to restore Anvil snapshot {snapshot_id}: {e}")

        # Analyze traces & findings
        trace_analyzer = TraceAnalyzer(
            raw_trace=raw_trace, is_complete=trace_complete, trace_error=trace_error
        )
        diff_dicts = [d.to_dict() for d in state_diffs]
        is_trace_ok, findings, trace_errors = trace_analyzer.analyze(logs=logs, state_diffs=diff_dicts)
        errors.extend(trace_errors)

        return SimulationResult(
            schema_version=SCHEMA_VERSION,
            scenario_id=self.scenario.scenario_id,
            chain_id=self.scenario.chain_id,
            simulation_mode=self.scenario.simulation_mode.value,
            success=success,
            state_diffs=diff_dicts,
            logs=logs,
            trace_complete=is_trace_ok,
            findings=[f.to_dict() for f in findings],
            errors=errors,
        )

    def _fetch_trace(self, tx_hash: str) -> Tuple[Optional[Any], bool, Optional[str]]:
        """Attempts to retrieve an execution trace from Anvil using debug_traceTransaction or trace_transaction."""
        # Method 1: Geth callTracer
        try:
            trace = self.client.call("debug_traceTransaction", [tx_hash, {"tracer": "callTracer"}])
            if trace:
                return trace, True, None
        except Exception as e1:
            logger.debug("debug_traceTransaction callTracer failed: %s", e1)

        # Method 2: Parity trace_transaction
        try:
            trace = self.client.call("trace_transaction", [tx_hash])
            if trace:
                return trace, True, None
        except Exception as e2:
            logger.debug("trace_transaction failed: %s", e2)

        # Method 3: Standard opcode structLogs
        try:
            trace = self.client.call("debug_traceTransaction", [tx_hash])
            if trace:
                return trace, True, None
        except Exception as e3:
            logger.debug("debug_traceTransaction standard failed: %s", e3)

        return None, False, "RPC node does not support debug_traceTransaction or trace_transaction."

    def _capture_state(self) -> Dict[str, Any]:
        """Collects native balances, token balances, Treasury owner, allowances, and storage slots."""
        state: Dict[str, Any] = {
            "native_balances": {},
            "token_balances": {},
            "treasury_owner": {},
            "allowances": {},
            "storage_slots": {},
        }

        # Addresses to observe: all watched addresses + sender + target
        observe_addrs = set(self.scenario.watched_addresses)
        observe_addrs.add(self.scenario.sender)
        observe_addrs.add(self.scenario.target)

        # 1. Native balances
        for addr in observe_addrs:
            try:
                bal_hex = self.client.call("eth_getBalance", [addr, "latest"])
                state["native_balances"][addr] = int(bal_hex, 16) if isinstance(bal_hex, str) else int(bal_hex)
            except Exception:
                state["native_balances"][addr] = None

        # 2. Token balances for watched tokens
        for token in self.scenario.watched_tokens:
            state["token_balances"][token] = {}
            for addr in observe_addrs:
                val = self._query_token_balance(token, addr)
                state["token_balances"][token][addr] = val

        # 3. Treasury owner check for target and watched addresses
        for addr in observe_addrs:
            owner = self._query_contract_owner(addr)
            if owner is not None:
                state["treasury_owner"][addr] = owner

        # 4. Allowances
        for wa in self.scenario.watched_allowances:
            key = f"{wa.token}:{wa.owner}:{wa.spender}"
            state["allowances"][key] = self._query_allowance(wa.token, wa.owner, wa.spender)

        # 5. Storage slots
        for ws in self.scenario.watched_storage:
            state["storage_slots"][ws.address] = {}
            for slot in ws.slots:
                try:
                    slot_val = self.client.call("eth_getStorageAt", [ws.address, slot, "latest"])
                    state["storage_slots"][ws.address][slot] = slot_val
                except Exception:
                    state["storage_slots"][ws.address][slot] = None

        return state

    def _compute_diffs(self, before: Dict[str, Any], after: Dict[str, Any]) -> List[EffectDiff]:
        """Calculates differences between baseline and resulting state."""
        diffs: List[EffectDiff] = []

        # A. Native balances
        before_native = before.get("native_balances", {})
        after_native = after.get("native_balances", {})
        for addr, b_val in before_native.items():
            a_val = after_native.get(addr)
            if b_val != a_val:
                delta = (a_val - b_val) if (a_val is not None and b_val is not None) else None
                diffs.append(
                    EffectDiff(
                        effect_id=f"native_balance:{addr}",
                        effect_type=EffectType.NATIVE_BALANCE.value,
                        address=addr,
                        token_address=None,
                        before_value=b_val,
                        after_value=a_val,
                        delta=delta,
                        evidence="eth_getBalance",
                    )
                )

        # B. Token balances
        before_tokens = before.get("token_balances", {})
        after_tokens = after.get("token_balances", {})
        for token, addrs in before_tokens.items():
            for addr, b_val in addrs.items():
                a_val = after_tokens.get(token, {}).get(addr)
                if b_val != a_val:
                    delta = (a_val - b_val) if (a_val is not None and b_val is not None) else None
                    diffs.append(
                        EffectDiff(
                            effect_id=f"token_balance:{token}:{addr}",
                            effect_type=EffectType.TOKEN_BALANCE.value,
                            address=addr,
                            token_address=token,
                            before_value=b_val,
                            after_value=a_val,
                            delta=delta,
                            evidence="ERC20.balanceOf",
                        )
                    )

        # C. Treasury owner
        before_owners = before.get("treasury_owner", {})
        after_owners = after.get("treasury_owner", {})
        for addr, b_owner in before_owners.items():
            a_owner = after_owners.get(addr)
            if b_owner != a_owner:
                diffs.append(
                    EffectDiff(
                        effect_id=f"treasury_owner:{addr}",
                        effect_type=EffectType.TREASURY_OWNER.value,
                        address=addr,
                        token_address=None,
                        before_value=b_owner,
                        after_value=a_owner,
                        delta=None,
                        evidence="Treasury.owner() / eth_getStorageAt:0x0",
                    )
                )

        # D. Allowances
        before_allowances = before.get("allowances", {})
        after_allowances = after.get("allowances", {})
        for key, b_val in before_allowances.items():
            a_val = after_allowances.get(key)
            if b_val != a_val:
                token_addr, owner_addr, spender_addr = key.split(":")
                delta = (a_val - b_val) if (a_val is not None and b_val is not None) else None
                diffs.append(
                    EffectDiff(
                        effect_id=f"allowance:{key}",
                        effect_type=EffectType.ALLOWANCE.value,
                        address=owner_addr,
                        token_address=token_addr,
                        before_value=b_val,
                        after_value=a_val,
                        delta=delta,
                        evidence="ERC20.allowance",
                    )
                )

        # E. Storage slots
        before_storage = before.get("storage_slots", {})
        after_storage = after.get("storage_slots", {})
        for addr, slots in before_storage.items():
            for slot, b_val in slots.items():
                a_val = after_storage.get(addr, {}).get(slot)
                if b_val != a_val:
                    diffs.append(
                        EffectDiff(
                            effect_id=f"storage_slot:{addr}:{slot}",
                            effect_type=EffectType.STORAGE_SLOT.value,
                            address=addr,
                            token_address=None,
                            before_value=b_val,
                            after_value=a_val,
                            delta=None,
                            evidence=f"eth_getStorageAt:{slot}",
                        )
                    )

        return diffs

    def _query_token_balance(self, token_address: str, account: str) -> Optional[int]:
        """Calls balanceOf(address) (0x70a08231)."""
        clean_addr = account.lower().replace("0x", "").zfill(64)
        calldata = f"0x70a08231{clean_addr}"
        try:
            res = self.client.call("eth_call", [{"to": token_address, "data": calldata}, "latest"])
            if res and res != "0x":
                return int(res, 16)
            return None
        except Exception:
            return None

    def _query_contract_owner(self, contract_address: str) -> Optional[str]:
        """Calls owner() (0x8da5cb5b), falling back to slot 0 query."""
        calldata = "0x8da5cb5b"
        try:
            res = self.client.call("eth_call", [{"to": contract_address, "data": calldata}, "latest"])
            if res and len(res) >= 66:
                return "0x" + res[-40:].lower()
        except Exception:
            pass

        # Fallback to slot 0
        try:
            slot0 = self.client.call("eth_getStorageAt", [contract_address, "0x0", "latest"])
            if slot0 and len(slot0) >= 42 and slot0 != "0x" + "0" * 64:
                return "0x" + slot0[-40:].lower()
        except Exception:
            pass
        return None

    def _query_allowance(self, token_address: str, owner: str, spender: str) -> Optional[int]:
        """Calls allowance(address,address) (0xdd62ed3e)."""
        clean_owner = owner.lower().replace("0x", "").zfill(64)
        clean_spender = spender.lower().replace("0x", "").zfill(64)
        calldata = f"0xdd62ed3e{clean_owner}{clean_spender}"
        try:
            res = self.client.call("eth_call", [{"to": token_address, "data": calldata}, "latest"])
            if res and res != "0x":
                return int(res, 16)
            return None
        except Exception:
            return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m analyzer.simulate <path_to_scenario.json>")
        sys.exit(1)

    scenario_file = sys.argv[1]
    with open(scenario_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    config = ScenarioConfig.from_dict(raw_data)
    simulator = Simulator(config)
    res = simulator.run()
    print(json.dumps(res.to_dict(), indent=2))

