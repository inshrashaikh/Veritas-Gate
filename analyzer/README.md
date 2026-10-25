# Veritas Gate — Phase 2: Simulation & Security Engine

> [!NOTE]
> Phase 2 provides a deterministic Python simulation and security trace analyzer for evaluating governance proposals and contract interactions against a local Anvil EVM.
> This engine collects **observable evidence** (state diffs, receipt logs, and opcode/call trace findings). It does **NOT** determine final governance verdicts.

---

## 1. Overview & Architecture

The Phase 2 engine executes proposal scenarios against a local Anvil node, records state mutations, inspects low-level execution traces, and produces machine-readable JSON adhering to the `veritas.simulation.v1` schema.

```
analyzer/
├── __init__.py
├── schemas.py              # Data models, scenario validation, and schema constants
├── simulate.py             # Local Anvil simulator, snapshot sandbox, and CLI runner
├── trace_rules.py          # Security rule evaluators (DELEGATECALL, SELFDESTRUCT, Proxy, etc.)
├── requirements.txt        # Pinned Python dependencies (web3, pytest, etc.)
├── examples/
│   ├── honest_grant.json            # 5M token grant proposal scenario
│   ├── malicious_delegatecall.json  # 5M grant with delegatecall ownership takeover
│   └── incomplete_trace.json        # Read-only / incomplete trace demonstration
└── tests/
    ├── test_validation.py      # Input validation & security constraint tests
    ├── test_state_diffs.py     # State-diff generation & raw integer precision tests
    ├── test_trace_rules.py     # Rule detection (R000-R004) & incomplete trace tests
    ├── test_simulation_unit.py # Unit tests with mock RPC & snapshot recovery
    └── test_integration.py     # End-to-end tests against live Anvil & Phase 1 contracts
```

---

## 2. Shared JSON Contract (`veritas.simulation.v1`)

The output schema is frozen and shared with Phase 3 consumers. Every simulation run emits the following 10 top-level fields:

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `schema_version` | `string` | Always `"veritas.simulation.v1"`. |
| `scenario_id` | `string` | Unique identifier matching the input scenario. |
| `chain_id` | `integer` | Chain ID of the simulation network (e.g. `31337`). |
| `simulation_mode` | `string` | `"read_only"` (via `eth_call`) or `"stateful_execution"` (via snapshot sandbox). |
| `success` | `boolean` | `true` if the transaction executed without revert, `false` otherwise. |
| `state_diffs` | `array` | List of observed state changes (`EffectDiff` objects). |
| `logs` | `array` | Raw event logs emitted by the transaction. |
| `trace_complete` | `boolean` | `true` if opcode/call traces were successfully collected, `false` if incomplete/unsupported. |
| `findings` | `array` | List of detected security findings (`TraceFinding` objects). |
| `errors` | `array` | List of error strings (empty list if no errors). |

### Structure of `state_diffs` Items
```json
{
  "effect_id": "token_balance:0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0:0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
  "effect_type": "token_balance",
  "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
  "token_address": "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0",
  "before_value": 0,
  "after_value": 5000000000000000000,
  "delta": 5000000000000000000,
  "evidence": "ERC20.balanceOf"
}
```

- **Raw Integer Precision**: All token amounts, native balances, and allowances are stored as unrounded integers (e.g. `5000000000000000000` for 5M tokens with 18 decimals).
- **Missing Value Distinction**: `None` / `null` indicates non-existent state or unavailable query, strictly distinguished from numeric `0`.

---

## 3. Security Trace Rules

Trace analysis detects security-sensitive operations across opcode traces (`structLogs`), call trees (`callTracer`), transaction logs, and storage diffs:

| Rule ID | Severity | Title | Description |
| :--- | :--- | :--- | :--- |
| **`R001_DELEGATECALL`** | `HIGH` | Dangerous DELEGATECALL Execution | Detected invocation of `DELEGATECALL`. The target executes within caller storage, risking storage collisions or ownership hijacking. |
| **`R002_SELFDESTRUCT`** | `HIGH` | Contract SELFDESTRUCT Detected | Detected `SELFDESTRUCT` instruction that destroys bytecode and forces native token transfer. |
| **`R003_PROXY_UPGRADE`** | `HIGH` | Proxy Storage Slot Modified | Detected write to EIP-1967 implementation slot (`0x36089...`), admin slot, or emission of `Upgraded(address)` event. |
| **`R004_UNLIMITED_APPROVAL`** | `MEDIUM` | Unlimited Token Approval Granted | Detected token approval with amount $\ge 2^{255}$ (e.g. `type(uint256).max`). |
| **`R000_INCONCLUSIVE_TRACE`** | `WARNING` | Inconclusive Trace Evidence | Generated when opcode/call tracing is unavailable or incomplete from the RPC endpoint. Trace-dependent checks cannot be verified clean. |

---

## 4. Trace Limitations & Safety Guardrails

- **Tracing Endpoint Dependency**: Transaction receipts contain status, gas used, and emitted logs, but **never** contain opcode traces. Full trace analysis requires node support for `debug_traceTransaction` (Geth callTracer/structLogger) or `trace_transaction` (Parity).
- **Never Treat Missing Trace as Clean**: If tracing fails or is unsupported, `trace_complete` is set to `false`, the exact reason is recorded, and `R000_INCONCLUSIVE_TRACE` is added to findings.
- **Local-Only RPC Constraint**: The simulator strictly forbids connecting to external or non-local networks. Any RPC URL not resolving to `127.0.0.1`, `localhost`, or `::1` is rejected immediately.
- **Atomic Snapshot Restoration**: In `stateful_execution` mode, an `evm_snapshot` is taken prior to execution. The snapshot is reverted (`evm_revert`) unconditionally in a `finally` block, ensuring no residual state changes remain on the test node.

---

## 5. Prerequisites & Setup

### Prerequisites
- Python 3.10+
- Foundry / Anvil (`anvil` binary)

### Installation
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r analyzer/requirements.txt
```

---

## 6. Running Tests & Scenarios

### Run Pytest Suite
```bash
.venv/bin/pytest -q
```
Expected output:
```text
25 passed in ...s
```

### Run Scenario via CLI
```bash
# Start local anvil in another terminal if not running:
# anvil

# Run honest grant simulation:
.venv/bin/python -m analyzer.simulate analyzer/examples/honest_grant.json
```
