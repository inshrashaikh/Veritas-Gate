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

---

## 7. Phase 5: API, Human Review Queue & Evidence Provenance

Phase 5 builds an HTTP REST API and state management layer that links simulation evidence, deterministic verdicts, proposal records, evidence provenance manifests, and human review decisions.

```
analyzer/
├── server.py              # Flask REST API endpoints and error handlers
├── review_queue.py        # Off-chain review queue state machine with atomic JSON persistence
├── provenance.py          # Evidence provenance manifest & SHA-256 integrity verification
├── contract_adapter.py    # Local Web3 adapter for Phase 4 ProposalRegistry & VerdictOracle
└── tests/
    ├── test_provenance.py        # Evidence hash verification and tamper detection tests
    ├── test_review_queue_unit.py # State machine transitions, authorization & persistence tests
    └── test_api.py               # Flask endpoints, payload limits, audit trail & error handling tests
```

---

### REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check returning API status and local RPC connectivity. |
| `POST` | `/proposals` | Register a new proposal version, compute text/calldata hashes, and record evidence manifests. |
| `GET` | `/proposals/<id>` | Retrieve complete version history and latest state of a proposal. |
| `POST` | `/analyze` | Execute deterministic EVM simulation. If high-risk patterns are detected, auto-enqueues proposal in `NEEDS_REVIEW` review queue. |
| `GET` | `/reviews` | List items in review queue, optionally filtered by `?status=PENDING\|APPROVED\|REJECTED\|ESCALATED`. |
| `POST` | `/reviews/<id>/<version>` | Submit human reviewer decision (`APPROVE`, `REJECT`, `ESCALATE`) with mandatory non-empty reason. |
| `GET` | `/audit/<proposal_id>` | Chronological audit trail aggregating proposal registrations, automated verdicts, and review records. |

---

### Evidence Provenance & Cryptographic Integrity

The evidence provenance subsystem (`analyzer/provenance.py`) tracks supporting artifacts (proposal PDFs, research specs, simulation output):
- **Cryptographic Integrity**: Computes SHA-256 digests (`0x...`) for submitted content and validates against expected hashes. Raises `TamperedContentError` if bytes do not match.
- **Distinction from Factual Truth**: Cryptographic hash matching guarantees that bytes have not been altered in transit or storage since retrieval. It **never** attests that factual claims or statements within the text are objectively true.
- **Immutable Audit Records**: Version-bound manifests prevent retroactive substitution of evidence.

---

### Human Review Queue State Machine

Proposals evaluated as `NEEDS_REVIEW` enter the review queue (`analyzer/review_queue.py`):
```
                 [ Enqueue ]
                      │
                      ▼
               ┌──────────────┐
       ┌───────│   PENDING    │───────┐
       │       └──────────────┘       │
       ▼              │               ▼
┌──────────────┐      │        ┌──────────────┐
│  ESCALATED   │◄─────┘        │   REJECTED   │ (Terminal)
└──────────────┘               └──────────────┘
       │                              
       ├──────────────┬───────────────┐
       ▼              ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  ESCALATED   │ │   APPROVED   │ │   REJECTED   │
└──────────────┘ └──────────────┘ └──────────────┘
                    (Terminal)       (Terminal)
```
- **Authorized Reviewers**: Reviews are rejected unless submitted by an explicitly authorized address.
- **Mandatory Reason**: Non-empty rationale required for all decisions.
- **Terminal States**: `APPROVED` and `REJECTED` are final; subsequent review attempts return HTTP 409 Conflict.
- **Preserved History**: Previous automated verdicts and intermediate triage decisions (e.g. `ESCALATE`) are appended to an immutable review list and never overwritten.

---

### Contract Interface & Adapter Notes

`analyzer/contract_adapter.py` interfaces with Phase 4 contracts (`ProposalRegistry`, `VerdictOracle`):
- **Local Anvil Only**: Uses `anvil_impersonateAccount` for test transactions. No private keys are generated, stored, or accepted over the API.
- **Decoupled Confirmation**: Off-chain queue state is updated immediately, while on-chain transaction hash and confirmation receipt status are tracked separately.
- **Interface Mismatch Handling**: `VerdictOracle.sol` defines on-chain review decisions as `APPROVE (1)` and `REJECT (2)`. The off-chain queue's `ESCALATE` state is an internal triage milestone and is **not** broadcast as an on-chain review decision, avoiding contract authorization bypass.

---

### Persistence Approach

Data is stored locally under `analyzer/data/` (or a configured test directory) in structured JSON files:
- `review_queue.json`: Queue items, state, and review history.
- `provenance.json`: Evidence manifests and verification status.
- `proposals.json`: Proposal versions, text hashes, and disclosed wallets.

**Atomic File Writes**: All writes write to a temporary file (`tempfile.NamedTemporaryFile`) in the same directory followed by an atomic `os.replace`. This prevents corruption in the event of an unexpected termination during write.

---

### Security & Hackathon Disclaimer

> [!WARNING]
> This server is a **local hackathon prototype** intended for pair testing with local Foundry/Anvil nodes.
> - It does not implement production TLS or public authentication middleware.
> - Reviewer authorization relies on trusted local configuration (`authorized_reviewers` set).
> - Payload sizes are strictly capped at 2MB (`MAX_CONTENT_LENGTH = 2 * 1024 * 1024`).
> - The API enforces that client inputs cannot override automated deterministic verdicts.

---

### Running the API & Tests

#### Start API Server
```bash
.venv/bin/python -m analyzer.server
```
Runs at `http://127.0.0.1:5000`.

#### Run All Python Tests
```bash
export PATH="$HOME/.foundry/bin:$PATH"
.venv/bin/pytest -q
```

#### Run Foundry Contract Tests
```bash
export PATH="$HOME/.foundry/bin:$PATH"
forge test -vv
```

