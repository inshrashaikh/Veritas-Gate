# Veritas Gate — Phase 1: Smart Contract Foundation

> [!WARNING]
> **EDUCATIONAL HARNESS ONLY — NOT PRODUCTION SECURE**
> This repository is a minimal educational test harness designed to demonstrate EVM storage collision risks and execution boundaries between `call` and `delegatecall`.
> Exposing arbitrary `delegatecall` functionality in a treasury or governance contract allows arbitrary code execution and contract takeover. **Never deploy this architecture to a live network or production environment.**

---

## 1. Overview & Objective

Phase 1 establishes the smart contract foundation for Veritas Gate. The goal is to demonstrate in a clean, reproducible Foundry environment:
1. How an **honest DAO grant proposal** distributes funds without side effects.
2. How a **malicious payload** leverages `delegatecall` storage collisions to overwrite Treasury state (ownership hijacking).
3. How the EVM execution boundary under standard `call` protects Treasury storage from callee state mutations.

---

## 2. Token Denomination

All contracts in this harness use a consistent, standard EVM token denomination:
- **Token**: `MockToken` (ERC-20 compatible)
- **Decimals**: `18` (matches WETH, DAI, and standard DAO governance tokens)
- **Base Unit**: `1 token = 1 * 10^18` wei (`1e18`)
- **Grant Amount**: `$5,000,000` equivalent = `5,000,000 * 10^18` (`5_000_000e18`) tokens
- **Initial Treasury Balance**: `10,000,000 * 10^18` (`10_000_000e18`) tokens

---

## 3. Storage Layout & The `delegatecall` Mechanism

### EVM Execution Context
- **Standard `call`**: Executes the callee contract's bytecode in the **callee's** context. `msg.sender` inside the callee is the caller (`Treasury`), and any state variable writes affect only the callee's own storage.
- **`delegatecall`**: Executes the target contract's bytecode in the **caller's** context. `address(this)`, `msg.sender`, `msg.value`, and the **storage trie** belong to the caller (`Treasury`).

### Storage Layout Alignment

In Solidity, contract state variables are assigned sequentially to 32-byte storage slots starting at slot 0:

| Storage Slot | `Treasury.sol` Variable | `MaliciousPayload.sol` Variable | Effect under `delegatecall` |
| :--- | :--- | :--- | :--- |
| **Slot 0** | `address public owner;` | `address public hijackedOwner;` | **Collision**: Writing `hijackedOwner = attacker` overwrites `Treasury.owner`. |
| **Slot 1** | `address public token;` | `address public preservedToken;` | Aligned with token address slot. |

`HonestPayload.sol` declares **zero storage variables** (only constants). When executed via `delegatecall`, it reads no storage and writes no storage, ensuring `Treasury` state remains intact.

---

## 4. Contract Architecture

```
contracts/
├── MockToken.sol           # Minimal ERC-20 token (balances, transfer, approve, transferFrom, mint)
├── Treasury.sol            # Owner-controlled treasury with call & delegatecall executors
├── payloads/
│   ├── Honest.sol          # 5M token grant without storage mutations
│   └── Malicious.sol       # 5M token grant with deliberate Slot 0 collision (unsafe)
└── test/
    └── Step1.t.sol         # Comprehensive Foundry test suite
```

### Core Contracts:
1. **`MockToken.sol`**: Standalone ERC-20 token implementation supporting balances, allowances, transfers, approvals, and testing mints.
2. **`Treasury.sol`**:
   - `executeCall(address target, uint256 value, bytes calldata data)`: Standard call execution. Isolates storage and bubbles up revert data.
   - `executeDelegateCall(address target, bytes calldata data)`: Demonstration delegatecall execution path. Bubbles up revert data and emits execution events.
3. **`payloads/Honest.sol`**:
   - Dispatches a 5,000,000 token grant to a specified recipient.
   - No state variables; touches zero storage slots.
4. **`payloads/Malicious.sol`**:
   - Dispatches a 5,000,000 token grant to a recipient.
   - Modifies slot 0 (`hijackedOwner = attacker`), seizing Treasury ownership when executed via `delegatecall`.

---

## 5. Prerequisites & Setup

### Prerequisites
- [Foundry](https://getfoundry.sh/) (`forge`, `cast`, `anvil`)
- Operating System: Linux / macOS / WSL

### Installation

If Foundry is not yet installed:
```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

Clone the repository and install `forge-std` (if missing):
```bash
# If lib/forge-std is not present:
mkdir -p lib/forge-std
curl -L https://github.com/foundry-rs/forge-std/archive/refs/tags/v1.9.4.tar.gz | tar -xz --strip-components=1 -C lib/forge-std
```

---

## 6. Running Tests & Expected Results

Run the Foundry test suite with double verbosity:
```bash
forge test -vv
```

### Expected Results
```text
[PASS] test_HonestDelegateCall_GrantDistributed_OwnershipPreserved() (gas: ...)
[PASS] test_HonestNormalCall_DirectTransfer() (gas: ...)
[PASS] test_MaliciousDelegateCall_GrantDistributed_OwnershipHijacked() (gas: ...)
[PASS] test_MaliciousNormalCall_CannotChangeTreasuryStorage_RevertsSafely() (gas: ...)
[PASS] test_MaliciousNormalCall_EvenIfFunded_CannotModifyTreasuryOwner() (gas: ...)
[PASS] test_UnauthorizedCaller_RevertsOnExecuteCall() (gas: ...)
[PASS] test_UnauthorizedCaller_RevertsOnExecuteDelegateCall() (gas: ...)
Suite result: ok. 7 passed; 0 failed; 0 skipped
```

### Verified Properties
- **Honest Payload (`delegatecall`)**: Recipient balance increases by 5M tokens; Treasury balance decreases by 5M tokens; `Treasury.owner` is unchanged.
- **Malicious Payload (`delegatecall`)**: Recipient balance increases by 5M tokens; Treasury balance decreases by 5M tokens; `Treasury.owner` is hijacked by the attacker address.
- **Malicious Payload (`call`)**: Callee storage writes cannot escape into Treasury storage; Treasury ownership remains 100% unchanged; unbacked transfer reverts safely.
- **Access Control**: Non-owner addresses cannot invoke `executeCall` or `executeDelegateCall`.

---

## 7. Known Limitations

- **Educational Scope**: Built strictly to illustrate EVM call vs delegatecall execution dynamics.
- **No Governance Mechanics**: Does not implement timelocks, quorum thresholds, voting tokens, or multi-signature controls.
- **Single Token Treasury**: Assumes a primary ERC-20 token.
