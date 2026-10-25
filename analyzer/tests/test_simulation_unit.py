"""Unit tests for Simulator execution flows using mock RPC clients."""

from unittest.mock import MagicMock
from analyzer.schemas import ScenarioConfig, SimulationMode
from analyzer.simulate import AnvilRPCClient, Simulator


def make_mock_client():
    client = MagicMock(spec=AnvilRPCClient)
    client.rpc_url = "http://127.0.0.1:8545"
    return client


def test_chain_id_mismatch_fails_cleanly():
    client = make_mock_client()
    # Node returns chain ID 1 (Mainnet)
    client.call.side_effect = lambda method, params=None: "0x1" if method == "eth_chainId" else None

    scenario = ScenarioConfig(
        scenario_id="chain-mismatch-test",
        chain_id=31337,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    )
    sim = Simulator(scenario, client=client)
    res = sim.run()

    assert res.success is False
    assert res.schema_version == "veritas.simulation.v1"
    assert any("Chain ID mismatch" in e for e in res.errors)


def test_read_only_simulation_success():
    client = make_mock_client()

    def mock_call(method, params=None):
        if method == "eth_chainId":
            return "0x7a69"  # 31337
        if method == "eth_getBalance":
            return "0x1000"
        if method == "eth_call":
            return "0x0000000000000000000000000000000000000000000000000000000000000001"
        return None

    client.call.side_effect = mock_call

    scenario = ScenarioConfig(
        scenario_id="read-only-test",
        chain_id=31337,
        simulation_mode=SimulationMode.READ_ONLY,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
        calldata="0x12345678",
    )
    sim = Simulator(scenario, client=client)
    res = sim.run()

    assert res.success is True
    assert res.simulation_mode == "read_only"
    assert res.trace_complete is False
    assert any(f["rule_id"] == "R000_INCONCLUSIVE_TRACE" for f in res.findings)


def test_stateful_execution_with_snapshot_and_revert():
    client = make_mock_client()
    call_log = []

    def mock_call(method, params=None):
        call_log.append(method)
        if method == "eth_chainId":
            return hex(31337)
        if method == "evm_snapshot":
            return "0x1"
        if method == "eth_sendTransaction":
            return "0xtxhash123"
        if method == "eth_getTransactionReceipt":
            return {"status": "0x1", "logs": []}
        if method == "debug_traceTransaction":
            return {
                "type": "CALL",
                "from": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
                "to": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",
                "calls": [],
            }
        if method == "eth_getBalance":
            return "0x100"
        if method == "evm_revert":
            return True
        return None

    client.call.side_effect = mock_call

    scenario = ScenarioConfig(
        scenario_id="stateful-test",
        chain_id=31337,
        simulation_mode=SimulationMode.STATEFUL_EXECUTION,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    )
    sim = Simulator(scenario, client=client)
    res = sim.run()

    assert res.success is True
    assert res.trace_complete is True
    assert "evm_snapshot" in call_log
    assert "evm_revert" in call_log
    # Ensure evm_revert was called after execution
    assert call_log.index("evm_revert") > call_log.index("eth_sendTransaction")


def test_snapshot_revert_called_on_execution_exception():
    client = make_mock_client()
    call_log = []

    def mock_call(method, params=None):
        call_log.append(method)
        if method == "eth_chainId":
            return hex(31337)
        if method == "evm_snapshot":
            return "0x1"
        if method == "eth_sendTransaction":
            raise RuntimeError("RPC Connection Dropped during sendTransaction")
        if method == "evm_revert":
            return True
        return None

    client.call.side_effect = mock_call

    scenario = ScenarioConfig(
        scenario_id="error-recovery-test",
        chain_id=31337,
        simulation_mode=SimulationMode.STATEFUL_EXECUTION,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    )
    sim = Simulator(scenario, client=client)
    res = sim.run()

    assert res.success is False
    assert "evm_snapshot" in call_log
    # CRITICAL: evm_revert MUST have been called even though eth_sendTransaction raised!
    assert "evm_revert" in call_log
    assert any("RPC Connection Dropped" in e for e in res.errors)


def test_output_schema_complete_fields():
    client = make_mock_client()
    client.call.side_effect = lambda method, params=None: hex(31337) if method == "eth_chainId" else None

    scenario = ScenarioConfig(
        scenario_id="schema-fields-test",
        chain_id=31337,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    )
    sim = Simulator(scenario, client=client)
    res = sim.run()
    d = res.to_dict()

    # Shared JSON contract with Phase 3 requires these 10 fields:
    expected_fields = [
        "schema_version",
        "scenario_id",
        "chain_id",
        "simulation_mode",
        "success",
        "state_diffs",
        "logs",
        "trace_complete",
        "findings",
        "errors",
    ]
    for field_name in expected_fields:
        assert field_name in d, f"Missing required top-level field '{field_name}' in simulation output"

    assert d["schema_version"] == "veritas.simulation.v1"
