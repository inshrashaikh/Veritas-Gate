"""Security trace analysis rules for Veritas Gate Phase 2.

Analyzes execution traces, logs, and state diffs to detect critical security events:
- R001_DELEGATECALL: High-risk delegatecall invocations
- R002_SELFDESTRUCT: Contract destruction operations
- R003_PROXY_UPGRADE: Proxy implementation / admin slot mutations
- R004_UNLIMITED_APPROVAL: Unlimited or max-uint256 token allowances
- R000_INCONCLUSIVE_TRACE: Incomplete or unavailable trace evidence warning
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from analyzer.schemas import FindingSeverity, TraceFinding

# Constants for EIP-1967 storage slots (hex strings normalized)
EIP1967_IMPLEMENTATION_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
EIP1967_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
EIP1967_BEACON_SLOT = "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50"

# ERC-1967 Upgraded event topic
UPGRADED_EVENT_TOPIC = "0xbc7cd75a20bf279770e3d116bc57b510c6d9009d2360e88022e53abf834e304a"

# ERC-20 Approval event topic: keccak256("Approval(address,address,uint256)")
APPROVAL_EVENT_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

# Threshold for unlimited approval detection (>= 2^255)
UNLIMITED_APPROVAL_THRESHOLD = 2**255


class TraceAnalyzer:
    """Evaluates security rules against EVM traces, transaction receipts, and state diffs."""

    def __init__(self, raw_trace: Optional[Any] = None, is_complete: bool = True, trace_error: Optional[str] = None):
        self.raw_trace = raw_trace
        self.is_complete = is_complete
        self.trace_error = trace_error

    def analyze(
        self,
        logs: List[Dict[str, Any]],
        state_diffs: List[Dict[str, Any]],
    ) -> Tuple[bool, List[TraceFinding], List[str]]:
        """Runs all detection rules.

        Returns:
            (trace_complete: bool, findings: List[TraceFinding], errors: List[str])
        """
        findings: List[TraceFinding] = []
        errors: List[str] = []

        # 1. Check trace completeness
        if not self.is_complete or self.raw_trace is None:
            reason = self.trace_error or "Trace data was unavailable or returned empty from RPC."
            errors.append(f"Incomplete trace: {reason}")
            findings.append(
                TraceFinding(
                    rule_id="R000_INCONCLUSIVE_TRACE",
                    severity=FindingSeverity.WARNING.value,
                    title="Inconclusive Trace Evidence",
                    explanation=(
                        f"Opcode/call trace evidence is unavailable or incomplete ({reason}). "
                        "Trace-dependent security checks (such as internal DELEGATECALL or SELFDESTRUCT opcodes) "
                        "cannot be conclusively ruled safe. Never interpret a missing trace as a clean trace."
                    ),
                    evidence={"reason": reason, "trace_complete": False},
                )
            )

        # 2. Check for DELEGATECALL
        delegatecall_findings = self._check_delegatecall()
        findings.extend(delegatecall_findings)

        # 3. Check for SELFDESTRUCT
        selfdestruct_findings = self._check_selfdestruct()
        findings.extend(selfdestruct_findings)

        # 4. Check for Proxy Upgrades & EIP-1967 Slot writes
        proxy_findings = self._check_proxy_upgrades(logs, state_diffs)
        findings.extend(proxy_findings)

        # 5. Check for Unlimited Approvals
        approval_findings = self._check_unlimited_approvals(logs, state_diffs)
        findings.extend(approval_findings)

        return self.is_complete and self.raw_trace is not None, findings, errors

    def _check_delegatecall(self) -> List[TraceFinding]:
        """Detects DELEGATECALL opcodes in callTracer trees, parity traces, or structLogs."""
        findings: List[TraceFinding] = []
        if not self.raw_trace:
            return findings

        # A. Geth callTracer format: recursive dict with 'type' and 'calls'
        if isinstance(self.raw_trace, dict) and "type" in self.raw_trace:
            self._walk_call_tracer(self.raw_trace, findings)

        # B. Parity trace_transaction format: list of trace entries
        elif isinstance(self.raw_trace, list):
            for entry in self.raw_trace:
                if isinstance(entry, dict):
                    action = entry.get("action", {})
                    call_type = str(action.get("callType", "")).upper()
                    entry_type = str(entry.get("type", "")).upper()
                    if call_type == "DELEGATECALL" or entry_type == "DELEGATECALL":
                        findings.append(
                            TraceFinding(
                                rule_id="R001_DELEGATECALL",
                                severity=FindingSeverity.HIGH.value,
                                title="Dangerous DELEGATECALL Execution Detected",
                                explanation=(
                                    "A contract invoked DELEGATECALL. The callee code executes within the caller's "
                                    "storage and context, which can enable storage collision attacks and ownership takeover."
                                ),
                                evidence={
                                    "caller": action.get("from"),
                                    "target": action.get("to"),
                                    "value": action.get("value", "0"),
                                    "trace_type": "parity_call",
                                },
                            )
                        )

        # C. Opcode structLogs format: dict with 'structLogs' list
        elif isinstance(self.raw_trace, dict) and "structLogs" in self.raw_trace:
            for log in self.raw_trace.get("structLogs", []):
                if str(log.get("op", "")).upper() == "DELEGATECALL":
                    findings.append(
                        TraceFinding(
                            rule_id="R001_DELEGATECALL",
                            severity=FindingSeverity.HIGH.value,
                            title="Dangerous DELEGATECALL Execution Detected",
                            explanation=(
                                "Opcode structLogs revealed a DELEGATECALL instruction. Callee executes in caller storage."
                            ),
                            evidence={
                                "pc": log.get("pc"),
                                "gas": log.get("gas"),
                                "trace_type": "structLog",
                            },
                        )
                    )
        return findings

    def _walk_call_tracer(self, node: Dict[str, Any], findings: List[TraceFinding]) -> None:
        call_type = str(node.get("type", "")).upper()
        if call_type == "DELEGATECALL":
            findings.append(
                TraceFinding(
                    rule_id="R001_DELEGATECALL",
                    severity=FindingSeverity.HIGH.value,
                    title="Dangerous DELEGATECALL Execution Detected",
                    explanation=(
                        "A contract invoked DELEGATECALL. The callee code executes within the caller's "
                        "storage and context, creating significant storage collision and ownership hijacking risks."
                    ),
                    evidence={
                        "caller": node.get("from"),
                        "target": node.get("to"),
                        "from": node.get("from"),
                        "to": node.get("to"),
                        "gas": node.get("gas"),
                        "input_prefix": str(node.get("input", ""))[:34],
                        "trace_type": "callTracer",
                    },
                )
            )

        for child in node.get("calls", []):
            if isinstance(child, dict):
                self._walk_call_tracer(child, findings)

    def _check_selfdestruct(self) -> List[TraceFinding]:
        """Detects SELFDESTRUCT opcodes in traces."""
        findings: List[TraceFinding] = []
        if not self.raw_trace:
            return findings

        # Parity trace format
        if isinstance(self.raw_trace, list):
            for entry in self.raw_trace:
                if isinstance(entry, dict) and str(entry.get("type", "")).lower() in ("suicide", "selfdestruct"):
                    action = entry.get("action", {})
                    findings.append(
                        TraceFinding(
                            rule_id="R002_SELFDESTRUCT",
                            severity=FindingSeverity.HIGH.value,
                            title="Contract SELFDESTRUCT Detected",
                            explanation="Contract invoked SELFDESTRUCT, wiping bytecode and forcing ether transfer.",
                            evidence={
                                "address": action.get("address"),
                                "refund_address": action.get("refundAddress"),
                                "balance": action.get("balance"),
                            },
                        )
                    )

        # Opcode structLogs format
        elif isinstance(self.raw_trace, dict) and "structLogs" in self.raw_trace:
            for log in self.raw_trace.get("structLogs", []):
                if str(log.get("op", "")).upper() in ("SELFDESTRUCT", "SUICIDE"):
                    findings.append(
                        TraceFinding(
                            rule_id="R002_SELFDESTRUCT",
                            severity=FindingSeverity.HIGH.value,
                            title="Contract SELFDESTRUCT Detected",
                            explanation="Opcode structLogs revealed a SELFDESTRUCT instruction.",
                            evidence={"pc": log.get("pc"), "gas": log.get("gas")},
                        )
                    )

        # Geth callTracer format (selfdestruct in callTracer is represented as type SELFDESTRUCT)
        elif isinstance(self.raw_trace, dict):
            self._walk_call_tracer_selfdestruct(self.raw_trace, findings)

        return findings

    def _walk_call_tracer_selfdestruct(self, node: Dict[str, Any], findings: List[TraceFinding]) -> None:
        call_type = str(node.get("type", "")).upper()
        if call_type in ("SELFDESTRUCT", "SUICIDE"):
            findings.append(
                TraceFinding(
                    rule_id="R002_SELFDESTRUCT",
                    severity=FindingSeverity.HIGH.value,
                    title="Contract SELFDESTRUCT Detected",
                    explanation="Contract executed a SELFDESTRUCT call frame.",
                    evidence={"from": node.get("from"), "to": node.get("to")},
                )
            )
        for child in node.get("calls", []):
            if isinstance(child, dict):
                self._walk_call_tracer_selfdestruct(child, findings)

    def _check_proxy_upgrades(
        self, logs: List[Dict[str, Any]], state_diffs: List[Dict[str, Any]]
    ) -> List[TraceFinding]:
        """Detects proxy implementation writes (EIP-1967 slots) or Upgraded events."""
        findings: List[TraceFinding] = []

        # A. Check Upgraded events in logs
        for i, log_entry in enumerate(logs):
            topics = log_entry.get("topics", [])
            if topics and str(topics[0]).lower() == UPGRADED_EVENT_TOPIC:
                impl_address = "0x" + topics[1][-40:] if len(topics) > 1 else "unknown"
                findings.append(
                    TraceFinding(
                        rule_id="R003_PROXY_UPGRADE",
                        severity=FindingSeverity.HIGH.value,
                        title="Proxy Implementation Upgrade Detected",
                        explanation="An EIP-1967 Upgraded event was emitted, indicating the logic contract was replaced.",
                        evidence={
                            "log_index": i,
                            "proxy_address": log_entry.get("address"),
                            "new_implementation": impl_address,
                        },
                    )
                )

        # B. Check state diffs for EIP-1967 implementation slot writes
        for diff in state_diffs:
            if diff.get("effect_type") == "storage_slot":
                effect_id = str(diff.get("effect_id", "")).lower()
                if (
                    EIP1967_IMPLEMENTATION_SLOT.lower() in effect_id
                    or EIP1967_ADMIN_SLOT.lower() in effect_id
                    or EIP1967_BEACON_SLOT.lower() in effect_id
                ):
                    before = diff.get("before_value")
                    after = diff.get("after_value")
                    if before != after:
                        findings.append(
                            TraceFinding(
                                rule_id="R003_PROXY_UPGRADE",
                                severity=FindingSeverity.HIGH.value,
                                title="Proxy Storage Slot Modified",
                                explanation=(
                                    "A recognized EIP-1967 proxy storage slot (implementation, admin, or beacon) "
                                    "was modified during execution."
                                ),
                                evidence={
                                    "address": diff.get("address"),
                                    "slot_id": effect_id,
                                    "before": before,
                                    "after": after,
                                },
                            )
                        )
        return findings

    def _check_unlimited_approvals(
        self, logs: List[Dict[str, Any]], state_diffs: List[Dict[str, Any]]
    ) -> List[TraceFinding]:
        """Detects unlimited or max-uint256 token allowances in logs or state diffs."""
        findings: List[TraceFinding] = []

        # A. Check Approval logs
        for i, log_entry in enumerate(logs):
            topics = log_entry.get("topics", [])
            if topics and str(topics[0]).lower() == APPROVAL_EVENT_TOPIC:
                data_hex = str(log_entry.get("data", "0x"))
                try:
                    val = int(data_hex, 16) if data_hex.startswith("0x") else int(data_hex)
                    if val >= UNLIMITED_APPROVAL_THRESHOLD:
                        owner = "0x" + topics[1][-40:] if len(topics) > 1 else "unknown"
                        spender = "0x" + topics[2][-40:] if len(topics) > 2 else "unknown"
                        findings.append(
                            TraceFinding(
                                rule_id="R004_UNLIMITED_APPROVAL",
                                severity=FindingSeverity.MEDIUM.value,
                                title="Unlimited Token Approval Granted",
                                explanation=(
                                    f"An approval of {val} (>= 2^255) tokens was granted to spender {spender}. "
                                    "Unlimited approvals expose user or treasury balances to total drainage if the spender is compromised."
                                ),
                                evidence={
                                    "log_index": i,
                                    "token": log_entry.get("address"),
                                    "owner": owner,
                                    "spender": spender,
                                    "raw_value": val,
                                },
                            )
                        )
                except (ValueError, TypeError):
                    pass

        # B. Check state diffs for allowance
        for diff in state_diffs:
            if diff.get("effect_type") == "allowance":
                after_val = diff.get("after_value")
                if isinstance(after_val, int) and after_val >= UNLIMITED_APPROVAL_THRESHOLD:
                    # Avoid duplicate if already reported via logs
                    findings.append(
                        TraceFinding(
                            rule_id="R004_UNLIMITED_APPROVAL",
                            severity=FindingSeverity.MEDIUM.value,
                            title="Unlimited Token Approval Recorded in State",
                            explanation=(
                                f"Observed post-execution allowance is {after_val} (>= 2^255). "
                                "Unlimited allowances grant perpetual transfer authority."
                            ),
                            evidence={
                                "effect_id": diff.get("effect_id"),
                                "token": diff.get("token_address"),
                                "raw_value": after_val,
                            },
                        )
                    )
        return findings
