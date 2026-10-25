# Veritas Gate — Governance Contracts & Treasury Guard

> [!WARNING]
> **LOCAL EDUCATIONAL HARNESS ONLY — NOT PRODUCTION READY**
> This repository is a modular educational test harness designed to demonstrate:
> 1. EVM execution dynamics (`call` vs `delegatecall` storage collisions).
> 2. Automated simulation & security trace analysis.
> 3. Proposal commitment registries, verdict oracles, and guarded treasury execution with 2-of-3 guardian emergency pause.
> **Never deploy these contracts to a live public network or mainnet environment.**

---

## 1. Overview & Architecture

Veritas Gate enforces proposal integrity, human-review gates, and challenge-window rules before governance proposals can execute against a guarded Treasury:

```
contracts/
├── MockToken.sol           # Minimal ERC-20 token (balances, transfer, approve, transferFrom, mint)
├── Treasury.sol            # Phase 1 educational demonstration treasury (call vs delegatecall)
├── ProposalRegistry.sol    # Phase 4 immutable versioned proposal commitment registry
├── VerdictOracle.sol       # Phase 4 simulation verdict, human review history & challenge oracle
├── GuardedTreasury.sol     # Phase 4 guarded treasury with 2-of-3 guardian pause & verification guards
├── payloads/
│   ├── Honest.sol          # 5M token grant without storage mutations
│   └── Malicious.sol       # 5M token grant with deliberate Slot 0 collision (unsafe)
└── test/
    ├── Step1.t.sol         # Phase 1 call vs delegatecall test suite
    └── Phase4.t.sol        # Phase 4 governance, oracle, guard, & multisig test suite
```

---

## 2. Core Governance Contracts (Phase 4)

### 1. `ProposalRegistry.sol`
- **Immutable Versioning**: Submitting a proposal creates version 1. Updates append sequential, immutable versions without modifying past history.
- **Commitments**: Binds proposal text hash (`keccak256`), calldata hash (`keccak256`), and disclosed participant addresses.
- **Integrity Verification**: `verifyLatestHashes(...)` allows callers to verify execution calldata and text against the latest registered proposal version.
- **Validation**: Rejects empty fields, duplicate version content, and unauthorized authors.

### 2. `VerdictOracle.sol`
- **Automated Verdicts**: The simulation analyzer posts automated verification verdicts:
  - `VERIFIED`: Proposal matches simulation invariants.
  - `MISMATCH`: Proposal effects deviate from claims; permanently blocks execution.
  - `NEEDS_REVIEW`: High-risk or complex proposal requiring authorized human review.
- **Human Review History**: Authorized reviewers from an allowlist can post reviews (`APPROVE`, `REJECT`, `ESCALATE`) along with a reason hash. All reviews are appended immutably to history and never overwrite the original automated verdict records.
- **Challenge System**: Challenges can be raised during the challenge window. Unresolved or successfully upheld challenges immediately block execution.

### 3. `GuardedTreasury.sol`
- **Removed Unrestricted Delegatecall**: Only standard, isolated EVM `call` is permitted. Any unrestricted delegatecall path is permanently removed.
- **Proposal Guard Invariants**: Before executing any proposal, the contract verifies:
  1. **Replay Protection**: Proposal version has not been executed previously.
  2. **Governance Authorization**: Proposal version was explicitly authorized.
  3. **Target & Value Binding**: Execution target and native value match authorization.
  4. **Calldata Commitment**: `keccak256(data)` matches the registered `calldataHash`.
  5. **Oracle Commitment**: Text hash and calldata hash match oracle commitments.
  6. **Verdict Eligibility**: Status is `VERIFIED` or `NEEDS_REVIEW` with an authorized `APPROVE` review.
  7. **Challenge Window**: Configured challenge window (default: 2 days / 172,800s) has elapsed.
  8. **No Challenges**: No active unresolved challenge and no disqualification.
  9. **Emergency Pause**: Contract is not paused.
- **2-of-3 Guardian Emergency Pause**:
  - Three distinct guardian addresses configured.
  - Pausing requires 2 distinct guardians to approve the same `reasonHash`. No single guardian can pause alone.
  - Unpausing requires 2 guardian approvals or governance owner intervention.

---

## 3. Token Denomination

- **Token**: `MockToken` (ERC-20 compatible)
- **Decimals**: `18` (matches WETH, DAI, and standard DAO governance tokens)
- **Base Unit**: `1 token = 1 * 10^18` wei (`1e18`)
- **Grant Amount**: `$5,000,000` equivalent = `5,000,000 * 10^18` (`5_000_000e18`) tokens
- **Initial Treasury Balance**: `10,000,000 * 10^18` (`10_000_000e18`) tokens

---

## 4. Quick Start & Setup Guide

### 🚀 Running Local Demo (No Blockchain Node or Wallets Required)

Veritas Gate runs in **Demo Mode by default** for local development and review. You can inspect bytecode diffs, evaluate simulation traces, explore conflict-of-interest graphs, submit auditor reviews, and cast informed votes immediately.

#### Prerequisites
- Python 3.10+
- Node.js 18+ (for frontend tests, optional)
- [Foundry](https://getfoundry.sh/) (`forge`, `anvil` — only required for running smart contract tests)

---

### Step 1: Environment Setup

#### Option A: macOS & Linux (bash / zsh)
```bash
# 1. Create a virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

#### Option B: Windows (PowerShell)
```powershell
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate the virtual environment
.venv\Scripts\Activate.ps1

# 3. Install Python dependencies
pip install -r requirements.txt
```

---

### Step 2: Start Veritas Gate

Run the unified launcher (auto-detects project virtual environment):
```bash
python run.py
```

Expected startup output:
```text
=================================================================
        VERITAS GATE — DETERMINISTIC GOVERNANCE ENGINE
=================================================================
[*] Starting Analyzer API Server on http://127.0.0.1:5000 (Demo Mode: true) ...
    -> API Ready: http://127.0.0.1:5000
    -> Health:    http://127.0.0.1:5000/health
[*] Starting Governance Dashboard on http://localhost:3000 ...
    -> Dashboard UI: http://localhost:3000
=================================================================
 Veritas Gate Application is RUNNING (DEMO MODE — SIMULATED DATA).
 • Web Dashboard: http://localhost:3000
 • Analyzer API:  http://127.0.0.1:5000
 • Mode:          Demo (Offline local development, zero RPC needed)
 Press Ctrl+C to terminate all services.
=================================================================
```

- **Governance Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Analyzer API & Health**: [http://127.0.0.1:5000/health](http://127.0.0.1:5000/health)

---

### Step 3: Running Test Suites

#### 1. Python Analyzer & Demo Test Suite
```bash
.venv/bin/pytest -v
```
*(Runs all 97 tests across claims, comparison, determinism, provenance, review queue, trace rules, and demo mode)*

#### 2. Native Frontend Component Test Suite
```bash
node --test tests/frontend/test_dashboard_logic.test.mjs
```
*(Runs 16 tests covering XSS sanitization, token formatting, demo labels, and simulation separation)*

#### 3. Foundry Smart Contract Test Suite
```bash
forge test -vv
```
*(Runs 26 contract tests verifying call vs delegatecall, ProposalRegistry, VerdictOracle, and 2-of-3 GuardedTreasury)*

---

## 5. Security Invariants Tested

- **Unauthorized Roles**: Unauthorized callers cannot post oracle verdicts, submit human reviews, or trigger guardian pause.
- **Rejection of Unsafe Proposals**: Execution is blocked by `MISMATCH`, unapproved `NEEDS_REVIEW`, `REJECT` reviews, active challenges, and disqualified proposals.
- **Integrity Protections**: Replay attacks, calldata substitution after authorization, and early execution before the challenge window elapses are strictly blocked.
- **Multisig Resilience**: Single guardians cannot pause alone; exact 2-of-3 consensus is required.
