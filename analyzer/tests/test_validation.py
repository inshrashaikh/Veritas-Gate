"""Unit tests for scenario input validation and schema enforcement."""

import pytest
from analyzer.schemas import ScenarioConfig, SimulationMode


def test_valid_scenario_config():
    data = {
        "scenario_id": "test-scenario-01",
        "chain_id": 31337,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "calldata": "0x12345678",
        "value": 1000000000000000000,
        "simulation_mode": "stateful_execution",
        "watched_tokens": ["0x9fE46736679d2D9a65F0992F2272dE9f3c7FA6e0"],
        "watched_addresses": ["0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"],
        "watched_allowances": [
            {
                "token": "0x9fE46736679d2D9a65F0992F2272dE9f3c7FA6e0",
                "owner": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
                "spender": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
            }
        ],
        "watched_storage": [
            {
                "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
                "slots": ["0x0", 1],
            }
        ],
        "rpc_url": "http://127.0.0.1:8545",
    }
    cfg = ScenarioConfig.from_dict(data)
    assert cfg.scenario_id == "test-scenario-01"
    assert cfg.chain_id == 31337
    assert cfg.sender == "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
    assert cfg.target == "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
    assert cfg.simulation_mode == SimulationMode.STATEFUL_EXECUTION
    assert cfg.value == 1000000000000000000
    assert cfg.watched_storage[0].slots == ["0x0", "0x1"]


def test_reject_missing_scenario_id():
    data = {
        "scenario_id": "",
        "chain_id": 31337,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    }
    with pytest.raises(ValueError, match="'scenario_id' must be a non-empty string"):
        ScenarioConfig.from_dict(data)


def test_reject_invalid_chain_id():
    data = {
        "scenario_id": "test-invalid-chain",
        "chain_id": 0,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    }
    with pytest.raises(ValueError, match="'chain_id' must be a positive integer"):
        ScenarioConfig.from_dict(data)


def test_reject_malformed_address():
    data = {
        "scenario_id": "test-bad-addr",
        "chain_id": 31337,
        "sender": "not-an-address",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
    }
    with pytest.raises(ValueError, match="must be a 20-byte 0x-prefixed hex address"):
        ScenarioConfig.from_dict(data)


def test_reject_invalid_calldata():
    data = {
        "scenario_id": "test-bad-calldata",
        "chain_id": 31337,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "calldata": "invalid_hex",
    }
    with pytest.raises(ValueError, match="'calldata' must be a 0x-prefixed hex string"):
        ScenarioConfig.from_dict(data)


def test_reject_non_local_rpc():
    data = {
        "scenario_id": "test-remote-rpc",
        "chain_id": 1,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "rpc_url": "https://eth-mainnet.alchemyapi.io/v2/demo",
    }
    with pytest.raises(ValueError, match="simulation can only connect to local RPCs"):
        ScenarioConfig.from_dict(data)


def test_reject_negative_value():
    data = {
        "scenario_id": "test-neg-val",
        "chain_id": 31337,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "value": -10,
    }
    with pytest.raises(ValueError, match="'value' must be a non-negative integer"):
        ScenarioConfig.from_dict(data)


def test_reject_unsupported_simulation_mode():
    data = {
        "scenario_id": "test-bad-mode",
        "chain_id": 31337,
        "sender": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "target": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "simulation_mode": "quantum_execution",
    }
    with pytest.raises(ValueError, match="Unsupported simulation_mode"):
        ScenarioConfig.from_dict(data)
