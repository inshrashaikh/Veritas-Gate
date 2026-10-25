"""Shared schemas and data models for Veritas Gate Phase 2 Simulation & Security Engine.

Schema Version: veritas.simulation.v1
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

SCHEMA_VERSION: str = "veritas.simulation.v1"


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


@dataclass
class SimulationResult:
    schema_version: str
    scenario_id: str
    chain_id: int
    simulation_mode: str
    success: bool
    state_diffs: List[Dict[str, Any]]
    logs: List[Dict[str, Any]]
    trace_complete: bool
    findings: List[Dict[str, Any]]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "chain_id": self.chain_id,
            "simulation_mode": self.simulation_mode,
            "success": self.success,
            "state_diffs": self.state_diffs,
            "logs": self.logs,
            "trace_complete": self.trace_complete,
            "findings": self.findings,
            "errors": self.errors,
        }
