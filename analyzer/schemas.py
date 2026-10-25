"""Shared schemas and data models for Veritas Gate Simulation & Security Engine.

Compatible with Phase 2 (Simulation Harness), Phase 3 (Claims & Verdict Engine),
Phase 4 (Governance Contracts), Phase 5 (API Server), and Phase 6 (Dashboard).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Version strings
SCHEMA_VERSION: str = "veritas.simulation.v1"
DEFAULT_SIMULATION_SCHEMA_VERSION: str = "veritas-simulation-v1.0"

EVM_ADDRESS_REGEX = re.compile(r"^0x[a-fA-F0-9]{40}$")
HEX_32_BYTES_REGEX = re.compile(r"^0x[a-fA-F0-9]{64}$")
HEX_FLEXIBLE_REGEX = re.compile(r"^0x[a-fA-F0-9]*$")

REQUIRED_SIMULATION_FIELDS = {
    "scenario_id",
    "chain_id",
    "simulation_mode",
    "success",
    "state_diffs",
    "logs",
    "trace_complete",
    "findings",
    "errors",
}

# Standard ERC-20 Transfer topic0 keccak256("Transfer(address,address,uint256)")
ERC20_TRANSFER_TOPIC0 = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# Standard ERC-20 Approval topic0 keccak256("Approval(address,address,uint256)")
ERC20_APPROVAL_TOPIC0 = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"


class SimulationSchemaError(ValueError):
    """Raised when simulation result JSON lacks required fields or has invalid structure."""
    pass


class SimulationMode(str, Enum):
    READ_ONLY = "read_only"
    STATEFUL_EXECUTION = "stateful_execution"


class EffectType(str, Enum):
    NATIVE_BALANCE = "native_balance"
    TOKEN_BALANCE = "token_balance"
    ALLOWANCE = "allowance"
    STORAGE_SLOT = "storage_slot"
    TREASURY_OWNER = "treasury_owner"


class FindingSeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    WARNING = "WARNING"


@dataclass
class WatchedAllowance:
    token: str
    owner: str
    spender: str

    def to_dict(self) -> Dict[str, str]:
        return {"token": self.token, "owner": self.owner, "spender": self.spender}


@dataclass
class WatchedStorage:
    address: str
    slots: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"address": self.address, "slots": self.slots}


@dataclass
class ScenarioConfig:
    scenario_id: str
    chain_id: int
    sender: str
    target: str
    calldata: str = "0x"
    value: int = 0
    simulation_mode: SimulationMode = SimulationMode.READ_ONLY
    watched_tokens: List[str] = field(default_factory=list)
    watched_addresses: List[str] = field(default_factory=list)
    watched_allowances: List[WatchedAllowance] = field(default_factory=list)
    watched_storage: List[WatchedStorage] = field(default_factory=list)
    rpc_url: str = "http://127.0.0.1:8545"

    def validate(self) -> None:
        """Validates all scenario fields and rejects malformed or non-local configurations."""
        if not self.scenario_id or not isinstance(self.scenario_id, str):
            raise ValueError("Scenario validation failed: 'scenario_id' must be a non-empty string.")

        if not isinstance(self.chain_id, int) or self.chain_id <= 0:
            raise ValueError("Scenario validation failed: 'chain_id' must be a positive integer.")

        if not isinstance(self.value, int) or self.value < 0:
            raise ValueError("Scenario validation failed: 'value' must be a non-negative integer (raw wei).")

        self.sender = self._validate_address(self.sender, "sender")
        self.target = self._validate_address(self.target, "target")

        if not isinstance(self.calldata, str) or not self._is_hex(self.calldata):
            raise ValueError(f"Scenario validation failed: 'calldata' must be a 0x-prefixed hex string, got '{self.calldata}'.")

        # Validate non-local RPC constraint
        self._validate_local_rpc(self.rpc_url)

        # Validate watched tokens and addresses
        validated_tokens = []
        for token in self.watched_tokens:
            validated_tokens.append(self._validate_address(token, "watched_token"))
        self.watched_tokens = validated_tokens

        validated_addresses = []
        for addr in self.watched_addresses:
            validated_addresses.append(self._validate_address(addr, "watched_address"))
        self.watched_addresses = validated_addresses

        # Validate allowances
        converted_allowances = []
        for wa in self.watched_allowances:
            if isinstance(wa, dict):
                wa = WatchedAllowance(token=wa["token"], owner=wa["owner"], spender=wa["spender"])
            wa.token = self._validate_address(wa.token, "allowance.token")
            wa.owner = self._validate_address(wa.owner, "allowance.owner")
            wa.spender = self._validate_address(wa.spender, "allowance.spender")
            converted_allowances.append(wa)
        self.watched_allowances = converted_allowances

        # Validate storage slots
        converted_storage = []
        for ws in self.watched_storage:
            if isinstance(ws, dict):
                ws = WatchedStorage(address=ws["address"], slots=ws.get("slots", []))
            ws.address = self._validate_address(ws.address, "watched_storage.address")
            cleaned_slots = []
            for slot in ws.slots:
                cleaned_slots.append(self._normalize_slot(slot))
            ws.slots = cleaned_slots
            converted_storage.append(ws)
        self.watched_storage = converted_storage

    @staticmethod
    def _validate_address(addr: str, field_name: str) -> str:
        if not isinstance(addr, str) or not re.match(r"^0x[0-9a-fA-F]{40}$", addr):
            raise ValueError(f"Scenario validation failed: '{field_name}' must be a 20-byte 0x-prefixed hex address, got '{addr}'.")
        return addr.lower()

    @staticmethod
    def _is_hex(s: str) -> bool:
        if not s.startswith("0x"):
            return False
        clean = s[2:]
        if len(clean) % 2 != 0:
            return False
        return bool(re.match(r"^[0-9a-fA-F]*$", clean))

    @staticmethod
    def _normalize_slot(slot: Union[str, int]) -> str:
        if isinstance(slot, int):
            return hex(slot)
        if isinstance(slot, str):
            if not slot.startswith("0x"):
                raise ValueError(f"Storage slot must be 0x-prefixed hex or integer, got '{slot}'.")
            return hex(int(slot, 16))
        raise ValueError(f"Storage slot must be string or integer, got {type(slot)}.")

    @staticmethod
    def _validate_local_rpc(rpc_url: str) -> None:
        """Ensures that execution connects ONLY to a local node (localhost, 127.0.0.1, ::1)."""
        lower = rpc_url.lower()
        if not ("://127.0.0.1" in lower or "://localhost" in lower or "://[::1]" in lower or lower.startswith("http://127.0.0.1") or lower.startswith("http://localhost")):
            raise ValueError(f"Security constraint violated: simulation can only connect to local RPCs (127.0.0.1 / localhost), attempted: '{rpc_url}'.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScenarioConfig:
        mode_val = data.get("simulation_mode", "read_only")
        try:
            mode = SimulationMode(mode_val)
        except ValueError:
            raise ValueError(f"Unsupported simulation_mode: '{mode_val}'. Supported modes: 'read_only', 'stateful_execution'.")

        raw_allowances = data.get("watched_allowances", [])
        allowances = [
            WatchedAllowance(
                token=a["token"],
                owner=a["owner"],
                spender=a["spender"]
            )
            for a in raw_allowances
        ]

        raw_storage = data.get("watched_storage", [])
        storage = [
            WatchedStorage(
                address=s["address"],
                slots=s.get("slots", [])
            )
            for s in raw_storage
        ]

        # Parse raw integer value
        raw_val = data.get("value", 0)
        if isinstance(raw_val, str):
            value = int(raw_val, 16) if raw_val.startswith("0x") else int(raw_val)
        else:
            value = int(raw_val)

        cfg = cls(
            scenario_id=data.get("scenario_id", ""),
            chain_id=int(data.get("chain_id", 0)),
            sender=data.get("sender", ""),
            target=data.get("target", ""),
            calldata=data.get("calldata", "0x"),
            value=value,
            simulation_mode=mode,
            watched_tokens=data.get("watched_tokens", []),
            watched_addresses=data.get("watched_addresses", []),
            watched_allowances=allowances,
            watched_storage=storage,
            rpc_url=data.get("rpc_url", "http://127.0.0.1:8545"),
        )
        cfg.validate()
        return cfg


@dataclass
class EffectDiff:
    effect_id: str
    effect_type: str
    address: str
    token_address: Optional[str]
    before_value: Optional[Union[int, str]]
    after_value: Optional[Union[int, str]]
    delta: Optional[int]
    evidence: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "effect_type": self.effect_type,
            "address": self.address,
            "token_address": self.token_address,
            "before_value": self.before_value,
            "after_value": self.after_value,
            "delta": self.delta,
            "evidence": self.evidence,
        }


@dataclass
class TraceFinding:
    rule_id: str
    severity: str
    title: str
    explanation: str
    evidence: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "title": self.title,
            "explanation": self.explanation,
            "evidence": self.evidence,
        }


def normalize_address(address: str, field_name: str = "address") -> str:
    if not isinstance(address, str):
        raise SimulationSchemaError(f"Invalid {field_name}: address must be a string, got {type(address).__name__}")
    addr = address.strip()
    if not EVM_ADDRESS_REGEX.match(addr):
        raise SimulationSchemaError(f"Invalid {field_name}: '{address}' is not a valid 20-byte hex EVM address")
    return addr.lower()


def address_from_hex32(hex_topic: str) -> str:
    """Extracts a 20-byte address from a 32-byte padded hex topic or string."""
    clean = hex_topic.strip()
    if clean.startswith("0x") or clean.startswith("0X"):
        clean = clean[2:]
    if len(clean) >= 40:
        addr_part = clean[-40:]
        return "0x" + addr_part.lower()
    raise ValueError(f"Cannot extract address from hex: '{hex_topic}'")


@dataclass(frozen=True)
class ObservedTokenTransfer:
    token: str
    from_address: str
    to_address: str
    amount: int
    log_index: int
    raw_log: Dict[str, Any]


@dataclass(frozen=True)
class ObservedApproval:
    token: str
    owner: str
    spender: str
    value: int
    log_index: int
    raw_log: Dict[str, Any]


@dataclass(frozen=True)
class ObservedNativeTransfer:
    from_address: str
    to_address: str
    amount: int
    call_index: int


@dataclass(frozen=True)
class ObservedStorageDiff:
    address: str
    slot: str  # Normalized hex string e.g. "0x0" or "0x00...00"
    slot_index: Optional[int]
    before: str
    after: str
    slot_name: Optional[str] = None

    @property
    def has_mutated(self) -> bool:
        return self.before.strip().lower() != self.after.strip().lower()

    @property
    def after_as_address(self) -> Optional[str]:
        """Parses the lower 20 bytes of 'after' as an EVM address."""
        try:
            return address_from_hex32(self.after)
        except Exception:
            return None


@dataclass(frozen=True)
class ObservedFinding:
    code: str
    severity: str
    description: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationResult:
    scenario_id: str
    chain_id: int
    simulation_mode: str
    success: bool
    state_diffs: List[Any]
    logs: List[Dict[str, Any]]
    trace_complete: bool
    findings: List[Any]
    errors: List[str]
    schema_version: str = DEFAULT_SIMULATION_SCHEMA_VERSION
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        serialized_diffs = []
        for d in self.state_diffs:
            if isinstance(d, dict):
                serialized_diffs.append(d)
            elif hasattr(d, "to_dict"):
                serialized_diffs.append(d.to_dict())
            else:
                serialized_diffs.append(asdict(d))

        serialized_findings = []
        for f in self.findings:
            if isinstance(f, dict):
                serialized_findings.append(f)
            elif hasattr(f, "to_dict"):
                serialized_findings.append(f.to_dict())
            else:
                serialized_findings.append(asdict(f))

        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "chain_id": self.chain_id,
            "simulation_mode": self.simulation_mode,
            "success": self.success,
            "state_diffs": serialized_diffs,
            "logs": self.logs,
            "trace_complete": self.trace_complete,
            "findings": serialized_findings,
            "errors": self.errors,
        }

    def get_token_transfers(self) -> List[ObservedTokenTransfer]:
        """
        Extracts and normalizes all ERC-20 transfers observed in logs.
        Decodes both pre-decoded log fields and raw ERC20 Transfer topics/data.
        """
        transfers: List[ObservedTokenTransfer] = []
        for idx, log in enumerate(self.logs):
            if not isinstance(log, dict):
                continue

            address = log.get("address")
            if not address or not isinstance(address, str):
                continue
            try:
                token_addr = normalize_address(address)
            except Exception:
                continue

            # Check if pre-decoded Transfer event is present
            decoded = log.get("decoded")
            event_name = log.get("event_name", "")
            if isinstance(decoded, dict) and (event_name.lower() == "transfer" or "value" in decoded):
                try:
                    from_addr = normalize_address(decoded["from"])
                    to_addr = normalize_address(decoded["to"])
                    val_raw = decoded["value"]
                    val = int(val_raw) if not isinstance(val_raw, int) else val_raw
                    log_idx = log.get("log_index", idx)
                    transfers.append(
                        ObservedTokenTransfer(
                            token=token_addr,
                            from_address=from_addr,
                            to_address=to_addr,
                            amount=val,
                            log_index=log_idx,
                            raw_log=log,
                        )
                    )
                    continue
                except Exception:
                    pass

            # Fallback to standard ERC-20 Transfer topic0 decoding
            topics = log.get("topics", [])
            if not isinstance(topics, list) or len(topics) < 3:
                continue

            topic0 = str(topics[0]).lower()
            if topic0 == ERC20_TRANSFER_TOPIC0:
                try:
                    from_addr = address_from_hex32(str(topics[1]))
                    to_addr = address_from_hex32(str(topics[2]))
                    raw_data = log.get("data", "0x0")
                    if isinstance(raw_data, str) and raw_data.startswith("0x"):
                        val = int(raw_data, 16) if len(raw_data) > 2 else 0
                    elif isinstance(raw_data, int):
                        val = raw_data
                    else:
                        val = int(str(raw_data))

                    log_idx = log.get("log_index", idx)
                    transfers.append(
                        ObservedTokenTransfer(
                            token=token_addr,
                            from_address=from_addr,
                            to_address=to_addr,
                            amount=val,
                            log_index=log_idx,
                            raw_log=log,
                        )
                    )
                except Exception:
                    continue

        return transfers

    def get_allowance_approvals(self) -> List[ObservedApproval]:
        """Extracts and normalizes all ERC-20 approvals observed in logs."""
        approvals: List[ObservedApproval] = []
        for idx, log in enumerate(self.logs):
            if not isinstance(log, dict):
                continue

            address = log.get("address")
            if not address or not isinstance(address, str):
                continue
            try:
                token_addr = normalize_address(address)
            except Exception:
                continue

            decoded = log.get("decoded")
            event_name = log.get("event_name", "")
            if isinstance(decoded, dict) and event_name.lower() == "approval":
                try:
                    owner_addr = normalize_address(decoded["owner"])
                    spender_addr = normalize_address(decoded["spender"])
                    val_raw = decoded["value"]
                    val = int(val_raw) if not isinstance(val_raw, int) else val_raw
                    approvals.append(
                        ObservedApproval(
                            token=token_addr,
                            owner=owner_addr,
                            spender=spender_addr,
                            value=val,
                            log_index=log.get("log_index", idx),
                            raw_log=log,
                        )
                    )
                    continue
                except Exception:
                    pass

            topics = log.get("topics", [])
            if isinstance(topics, list) and len(topics) >= 3:
                topic0 = str(topics[0]).lower()
                if topic0 == ERC20_APPROVAL_TOPIC0:
                    try:
                        owner_addr = address_from_hex32(str(topics[1]))
                        spender_addr = address_from_hex32(str(topics[2]))
                        raw_data = log.get("data", "0x0")
                        if isinstance(raw_data, str) and raw_data.startswith("0x"):
                            val = int(raw_data, 16) if len(raw_data) > 2 else 0
                        elif isinstance(raw_data, int):
                            val = raw_data
                        else:
                            val = int(str(raw_data))

                        approvals.append(
                            ObservedApproval(
                                token=token_addr,
                                owner=owner_addr,
                                spender=spender_addr,
                                value=val,
                                log_index=log.get("log_index", idx),
                                raw_log=log,
                            )
                        )
                    except Exception:
                        continue
        return approvals

    def get_native_transfers(self) -> List[ObservedNativeTransfer]:
        """Extracts native transfers from raw_data or call traces if recorded."""
        native_list: List[ObservedNativeTransfer] = []
        raw_native = self.raw_data.get("native_transfers", [])
        if isinstance(raw_native, list):
            for idx, item in enumerate(raw_native):
                if isinstance(item, dict):
                    try:
                        from_addr = normalize_address(item.get("from", "0x0000000000000000000000000000000000000000"))
                        to_addr = normalize_address(item.get("to", "0x0000000000000000000000000000000000000000"))
                        amount = int(item.get("value", item.get("amount", 0)))
                        native_list.append(
                            ObservedNativeTransfer(
                                from_address=from_addr,
                                to_address=to_addr,
                                amount=amount,
                                call_index=item.get("call_index", idx),
                            )
                        )
                    except Exception:
                        pass
        return native_list

    def get_storage_diffs_for_address(self, contract_address: str) -> List[ObservedStorageDiff]:
        norm = normalize_address(contract_address)
        diffs = []
        for d in self.state_diffs:
            if isinstance(d, ObservedStorageDiff):
                if d.address == norm:
                    diffs.append(d)
            elif isinstance(d, dict):
                try:
                    parsed = parse_state_diff_item(d, 0)
                    if parsed.address == norm:
                        diffs.append(parsed)
                except Exception:
                    pass
            elif hasattr(d, "address") and getattr(d, "address") == norm:
                diffs.append(d)
        return diffs

    def get_finding_codes(self) -> Set[str]:
        codes = set()
        for f in self.findings:
            if isinstance(f, ObservedFinding):
                codes.add(f.code.upper())
            elif isinstance(f, dict):
                code = f.get("code") or f.get("rule_id") or f.get("type")
                if code:
                    codes.add(str(code).upper())
            elif hasattr(f, "code"):
                codes.add(str(f.code).upper())
            elif hasattr(f, "rule_id"):
                codes.add(str(f.rule_id).upper())
        return codes


def parse_slot_index(slot_val: Any) -> Tuple[str, Optional[int]]:
    """Normalizes a storage slot representation to hex string and optional int index."""
    if isinstance(slot_val, int):
        return hex(slot_val), slot_val
    if isinstance(slot_val, str):
        cleaned = slot_val.strip()
        if cleaned.startswith("0x") or cleaned.startswith("0X"):
            try:
                int_val = int(cleaned, 16)
                return cleaned.lower(), int_val
            except ValueError:
                return cleaned.lower(), None
        if cleaned.isdigit():
            int_val = int(cleaned)
            return hex(int_val), int_val
        return cleaned, None
    return str(slot_val), None


def parse_state_diff_item(item: Dict[str, Any], idx: int) -> ObservedStorageDiff:
    """Parses a single state diff record."""
    if not isinstance(item, dict):
        raise SimulationSchemaError(f"State diff at index {idx} must be a JSON object")

    if "address" not in item:
        raise SimulationSchemaError(f"State diff at index {idx} missing required field 'address'")

    addr = normalize_address(item["address"], f"state_diff[{idx}].address")
    raw_slot = item.get("slot", "0x0")
    norm_slot, slot_idx = parse_slot_index(raw_slot)

    before = str(item.get("before", item.get("before_value", "0x0"))).strip()
    after = str(item.get("after", item.get("after_value", "0x0"))).strip()
    slot_name = item.get("slot_name", item.get("slot_key"))
    if slot_name is not None and not isinstance(slot_name, str):
        slot_name = str(slot_name)

    return ObservedStorageDiff(
        address=addr,
        slot=norm_slot,
        slot_index=slot_idx,
        before=before,
        after=after,
        slot_name=slot_name,
    )


def parse_finding_item(item: Any, idx: int) -> ObservedFinding:
    """Parses a finding record (object or string code)."""
    if isinstance(item, str):
        code = item.strip().upper()
        return ObservedFinding(code=code, severity="MEDIUM", description=code)
    if isinstance(item, dict):
        code = item.get("code") or item.get("rule_id") or item.get("type") or item.get("finding")
        if not code or not isinstance(code, str):
            code = f"UNKNOWN_FINDING_{idx}"
        severity = item.get("severity", "MEDIUM")
        description = item.get("description", item.get("explanation", item.get("title", code)))
        return ObservedFinding(
            code=str(code).strip().upper(),
            severity=str(severity).strip().upper(),
            description=str(description),
            details=item,
        )
    raise SimulationSchemaError(f"Finding at index {idx} must be a string or object")


def validate_simulation_result_dict(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a simulation result dictionary against the required schema.
    Returns (is_valid, list_of_missing_or_invalid_fields).
    Treats absent required fields as incomplete evidence.
    """
    if not isinstance(data, dict):
        return False, [f"Root simulation result must be a JSON object, got {type(data).__name__}"]

    errors: List[str] = []
    missing_fields = REQUIRED_SIMULATION_FIELDS - set(data.keys())
    if missing_fields:
        for mf in sorted(missing_fields):
            errors.append(f"Missing required field: '{mf}'")

    if "chain_id" in data and not isinstance(data["chain_id"], int):
        errors.append(f"Field 'chain_id' must be an integer, got {type(data['chain_id']).__name__}")

    if "success" in data and not isinstance(data["success"], bool):
        errors.append(f"Field 'success' must be a boolean, got {type(data['success']).__name__}")

    if "trace_complete" in data and not isinstance(data["trace_complete"], bool):
        errors.append(f"Field 'trace_complete' must be a boolean, got {type(data['trace_complete']).__name__}")

    if "state_diffs" in data and not isinstance(data["state_diffs"], (list, dict)):
        errors.append(f"Field 'state_diffs' must be a list or dict, got {type(data['state_diffs']).__name__}")

    if "logs" in data and not isinstance(data["logs"], list):
        errors.append(f"Field 'logs' must be a list, got {type(data['logs']).__name__}")

    if "findings" in data and not isinstance(data["findings"], list):
        errors.append(f"Field 'findings' must be a list, got {type(data['findings']).__name__}")

    if "errors" in data and not isinstance(data["errors"], list):
        errors.append(f"Field 'errors' must be a list, got {type(data['errors']).__name__}")

    return len(errors) == 0, errors


def load_simulation_result_from_dict(data: Dict[str, Any]) -> SimulationResult:
    """
    Constructs a SimulationResult from a dictionary.
    Fails closed: raises SimulationSchemaError if required fields are missing or malformed.
    """
    is_valid, errors = validate_simulation_result_dict(data)
    if not is_valid:
        raise SimulationSchemaError("Simulation result validation failed: " + "; ".join(errors))

    scenario_id = str(data["scenario_id"]).strip()
    chain_id = int(data["chain_id"])
    simulation_mode = str(data["simulation_mode"]).strip()
    success = bool(data["success"])
    trace_complete = bool(data["trace_complete"])
    schema_version = str(data.get("schema_version", DEFAULT_SIMULATION_SCHEMA_VERSION))

    raw_diffs = data["state_diffs"]
    parsed_diffs: List[ObservedStorageDiff] = []
    if isinstance(raw_diffs, list):
        for idx, diff_item in enumerate(raw_diffs):
            parsed_diffs.append(parse_state_diff_item(diff_item, idx))
    elif isinstance(raw_diffs, dict):
        storage_list = raw_diffs.get("storage", [])
        if isinstance(storage_list, list):
            for idx, diff_item in enumerate(storage_list):
                parsed_diffs.append(parse_state_diff_item(diff_item, idx))

    raw_logs = data["logs"]
    raw_findings = data["findings"]
    parsed_findings: List[ObservedFinding] = []
    for idx, f in enumerate(raw_findings):
        parsed_findings.append(parse_finding_item(f, idx))

    raw_errors = [str(e) for e in data["errors"]]

    return SimulationResult(
        scenario_id=scenario_id,
        chain_id=chain_id,
        simulation_mode=simulation_mode,
        success=success,
        trace_complete=trace_complete,
        state_diffs=parsed_diffs,
        logs=raw_logs,
        findings=parsed_findings,
        errors=raw_errors,
        schema_version=schema_version,
        raw_data=data,
    )


def load_simulation_result_from_json(json_str: str) -> SimulationResult:
    """Loads and validates a SimulationResult from JSON string."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise SimulationSchemaError(f"Invalid JSON syntax in simulation result: {exc}") from exc
    return load_simulation_result_from_dict(data)
