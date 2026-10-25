"""End-to-end integration tests executing real scenarios against a local Anvil EVM instance."""

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
import pytest
from web3 import Web3

from analyzer.schemas import ScenarioConfig, SimulationMode
from analyzer.simulate import Simulator

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def find_anvil_bin() -> str:
    path = shutil.which("anvil")
    if path:
        return path
    home_anvil = os.path.expanduser("~/.foundry/bin/anvil")
    if os.path.isfile(home_anvil) and os.access(home_anvil, os.X_OK):
        return home_anvil
    pytest.skip("anvil binary not found on system")


@pytest.fixture(scope="module")
def anvil_node():
    anvil_bin = find_anvil_bin()
    port = get_free_port()
    rpc_url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [anvil_bin, "--port", str(port), "--silent"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for node to be responsive
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    connected = False
    for _ in range(50):
        try:
            if w3.is_connected():
                connected = True
                break
        except Exception:
            pass
        time.sleep(0.1)

    if not connected:
        proc.kill()
        pytest.fail(f"Failed to start Anvil node on {rpc_url}")

    yield {"proc": proc, "rpc_url": rpc_url, "w3": w3}

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def deployed_contracts(anvil_node):
    w3: Web3 = anvil_node["w3"]
    accounts = w3.eth.accounts
    deployer = accounts[0]
    treasury_owner = deployer
    recipient = accounts[1]
    attacker = accounts[2]

    # Load compiled artifacts from out/
    def load_artifact(filename, contract_name):
        p = PROJECT_ROOT / "out" / filename / f"{contract_name}.json"
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["abi"], data["bytecode"]["object"]

    mock_abi, mock_bin = load_artifact("MockToken.sol", "MockToken")
    treasury_abi, treasury_bin = load_artifact("Treasury.sol", "Treasury")
    honest_abi, honest_bin = load_artifact("Honest.sol", "HonestPayload")
    malicious_abi, malicious_bin = load_artifact("Malicious.sol", "MaliciousPayload")

    # 1. Deploy MockToken
    MockToken = w3.eth.contract(abi=mock_abi, bytecode=mock_bin)
    tx_hash = MockToken.constructor("Veritas Mock Token", "MOCK", 0).transact({"from": deployer})
    mock_token_addr = w3.eth.wait_for_transaction_receipt(tx_hash).contractAddress
    mock_token = w3.eth.contract(address=mock_token_addr, abi=mock_abi)

    # 2. Deploy Treasury
    Treasury = w3.eth.contract(abi=treasury_abi, bytecode=treasury_bin)
    tx_hash = Treasury.constructor(mock_token_addr).transact({"from": treasury_owner})
    treasury_addr = w3.eth.wait_for_transaction_receipt(tx_hash).contractAddress
    treasury = w3.eth.contract(address=treasury_addr, abi=treasury_abi)

    # 3. Fund Treasury with 10M tokens (18 decimals)
    initial_balance = 10_000_000 * 10**18
    tx_hash = mock_token.functions.mint(treasury_addr, initial_balance).transact({"from": deployer})
    w3.eth.wait_for_transaction_receipt(tx_hash)

    # 4. Deploy HonestPayload
    HonestPayload = w3.eth.contract(abi=honest_abi, bytecode=honest_bin)
    tx_hash = HonestPayload.constructor().transact({"from": deployer})
    honest_addr = w3.eth.wait_for_transaction_receipt(tx_hash).contractAddress
    honest_payload = w3.eth.contract(address=honest_addr, abi=honest_abi)

    # 5. Deploy MaliciousPayload
    MaliciousPayload = w3.eth.contract(abi=malicious_abi, bytecode=malicious_bin)
    tx_hash = MaliciousPayload.constructor().transact({"from": deployer})
    malicious_addr = w3.eth.wait_for_transaction_receipt(tx_hash).contractAddress
    malicious_payload = w3.eth.contract(address=malicious_addr, abi=malicious_abi)

    return {
        "deployer": deployer,
        "treasury_owner": treasury_owner,
        "recipient": recipient,
        "attacker": attacker,
        "mock_token": mock_token,
        "treasury": treasury,
        "honest_payload": honest_payload,
        "malicious_payload": malicious_payload,
    }


def test_anvil_honest_grant_scenario(anvil_node, deployed_contracts):
    w3: Web3 = anvil_node["w3"]
    rpc_url = anvil_node["rpc_url"]
    treasury = deployed_contracts["treasury"]
    mock_token = deployed_contracts["mock_token"]
    honest_payload = deployed_contracts["honest_payload"]
    treasury_owner = deployed_contracts["treasury_owner"]
    recipient = deployed_contracts["recipient"]

    # Calldata: honestPayload.execute(mock_token, recipient)
    payload_calldata = honest_payload.encode_abi(
        abi_element_identifier="execute",
        args=[mock_token.address, recipient],
    )
    # Calldata: treasury.executeDelegateCall(honest_payload.address, payload_calldata)
    treasury_calldata = treasury.encode_abi(
        abi_element_identifier="executeDelegateCall",
        args=[honest_payload.address, bytes.fromhex(payload_calldata[2:])],
    )

    scenario = ScenarioConfig(
        scenario_id="integration-honest-grant",
        chain_id=w3.eth.chain_id,
        simulation_mode=SimulationMode.STATEFUL_EXECUTION,
        sender=treasury_owner,
        target=treasury.address,
        calldata=treasury_calldata,
        value=0,
        watched_tokens=[mock_token.address],
        watched_addresses=[treasury.address, recipient],
        watched_storage=[{"address": treasury.address, "slots": ["0x0"]}],
        rpc_url=rpc_url,
    )

    sim = Simulator(scenario)
    res = sim.run()

    assert res.success is True, f"Simulation failed with errors: {res.errors}"
    assert res.schema_version == "veritas.simulation.v1"
    assert res.trace_complete is True

    # Check state diffs
    diff_map = {d["effect_id"]: d for d in res.state_diffs}
    treasury_token_key = f"token_balance:{mock_token.address.lower()}:{treasury.address.lower()}"
    recipient_token_key = f"token_balance:{mock_token.address.lower()}:{recipient.lower()}"

    assert treasury_token_key in diff_map
    assert diff_map[treasury_token_key]["delta"] == -5_000_000 * 10**18
    assert recipient_token_key in diff_map
    assert diff_map[recipient_token_key]["delta"] == 5_000_000 * 10**18

    # Verify Treasury owner is UNCHANGED (no treasury_owner diff emitted)
    owner_diffs = [d for d in res.state_diffs if d["effect_type"] == "treasury_owner"]
    assert len(owner_diffs) == 0

    # Verify DELEGATECALL finding is detected
    delegate_findings = [f for f in res.findings if f["rule_id"] == "R001_DELEGATECALL"]
    assert len(delegate_findings) >= 1

    # VERIFY STATE RESTORATION: Treasury balance in Anvil is STILL 10M tokens!
    current_treasury_bal = mock_token.functions.balanceOf(treasury.address).call()
    assert current_treasury_bal == 10_000_000 * 10**18, "Snapshot revert failed to restore baseline state"


def test_anvil_malicious_delegatecall_scenario(anvil_node, deployed_contracts):
    w3: Web3 = anvil_node["w3"]
    rpc_url = anvil_node["rpc_url"]
    treasury = deployed_contracts["treasury"]
    mock_token = deployed_contracts["mock_token"]
    malicious_payload = deployed_contracts["malicious_payload"]
    treasury_owner = deployed_contracts["treasury_owner"]
    recipient = deployed_contracts["recipient"]
    attacker = deployed_contracts["attacker"]

    # Calldata: maliciousPayload.execute(mock_token, recipient, attacker)
    payload_calldata = malicious_payload.encode_abi(
        abi_element_identifier="execute",
        args=[mock_token.address, recipient, attacker],
    )
    # Calldata: treasury.executeDelegateCall(malicious_payload.address, payload_calldata)
    treasury_calldata = treasury.encode_abi(
        abi_element_identifier="executeDelegateCall",
        args=[malicious_payload.address, bytes.fromhex(payload_calldata[2:])],
    )

    scenario = ScenarioConfig(
        scenario_id="integration-malicious-delegatecall",
        chain_id=w3.eth.chain_id,
        simulation_mode=SimulationMode.STATEFUL_EXECUTION,
        sender=treasury_owner,
        target=treasury.address,
        calldata=treasury_calldata,
        value=0,
        watched_tokens=[mock_token.address],
        watched_addresses=[treasury.address, recipient, attacker],
        watched_storage=[{"address": treasury.address, "slots": ["0x0"]}],
        rpc_url=rpc_url,
    )

    sim = Simulator(scenario)
    res = sim.run()

    assert res.success is True, f"Simulation failed with errors: {res.errors}"
    assert res.trace_complete is True

    # 1. Verify token balance diffs
    diff_map = {d["effect_id"]: d for d in res.state_diffs}
    treasury_token_key = f"token_balance:{mock_token.address.lower()}:{treasury.address.lower()}"
    recipient_token_key = f"token_balance:{mock_token.address.lower()}:{recipient.lower()}"
    assert diff_map[treasury_token_key]["delta"] == -5_000_000 * 10**18
    assert diff_map[recipient_token_key]["delta"] == 5_000_000 * 10**18

    # 2. CRITICAL EXPLOIT EVIDENCE: Treasury owner was hijacked!
    owner_diff = next(d for d in res.state_diffs if d["effect_type"] == "treasury_owner")
    assert owner_diff["before_value"].lower() == treasury_owner.lower()
    assert owner_diff["after_value"].lower() == attacker.lower()

    # 3. Security Findings: DELEGATECALL reported with HIGH severity
    delegate_finding = next(f for f in res.findings if f["rule_id"] == "R001_DELEGATECALL")
    assert delegate_finding["severity"] == "HIGH"

    # 4. Verify Anvil snapshot restored cleanly: owner in Anvil is STILL original owner!
    actual_owner = treasury.functions.owner().call()
    assert actual_owner.lower() == treasury_owner.lower(), "Snapshot revert did not restore owner"


def test_anvil_reverted_execution(anvil_node, deployed_contracts):
    w3: Web3 = anvil_node["w3"]
    rpc_url = anvil_node["rpc_url"]
    treasury = deployed_contracts["treasury"]
    unauthorized_sender = deployed_contracts["recipient"]

    # Unauthorized caller tries to call executeCall
    calldata = treasury.encode_abi(
        abi_element_identifier="executeCall",
        args=[deployed_contracts["mock_token"].address, 0, b""],
    )

    scenario = ScenarioConfig(
        scenario_id="integration-revert",
        chain_id=w3.eth.chain_id,
        simulation_mode=SimulationMode.STATEFUL_EXECUTION,
        sender=unauthorized_sender,
        target=treasury.address,
        calldata=calldata,
        rpc_url=rpc_url,
    )

    sim = Simulator(scenario)
    res = sim.run()

    # Transaction reverted
    assert res.success is False
    assert len(res.errors) >= 1
    assert any("revert" in e.lower() for e in res.errors)
