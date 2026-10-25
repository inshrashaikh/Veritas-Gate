# Veritas Gate: Simulation & Claims JSON Interface Specification

> **Phase 3 Specification Document**  
> **Schema Versions:**
> - Claims: `veritas-claims-v1.0`
> - Simulation Result: `veritas-simulation-v1.0`
> - Verdict Engine Output: `veritas-verdict-v1.0`

---

## 1. Executive Summary

This document defines the strict, versioned JSON interface between **Phase 2 (EVM Simulation Harness)** and **Phase 3 (Claims & Deterministic Verdict Engine)**.

The Verdict Engine operates under strict **fail-closed interface discipline**:
1. Missing, malformed, or ambiguous evidence **never** produces `VERIFIED`.
2. Absences of required fields are treated as incomplete evidence.
3. Precedence is strictly deterministic:
   - **Rule 1 (Proven Material Mismatch)**: Reliable evidence proves a violation or unclaimed material effect $\rightarrow$ `MISMATCH`.
   - **Rule 2 (Uncertainty or Risky Flags)**: Configured risky trace flags, incomplete trace, missing evidence, or ambiguous claims $\rightarrow$ `NEEDS_REVIEW`.
   - **Rule 3 (Full Verification)**: Every claim verified cleanly, zero unclaimed material effects, clean complete evidence, zero risky flags $\rightarrow$ `VERIFIED`.

---

## 2. Proposal Claims Schema (`veritas-claims-v1.0`)

Proposal claims define the expected execution effects declared by proposal authors.

### Top-Level Fields

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | `string` | **Yes** | Must be `"veritas-claims-v1.0"`. |
| `proposal_id` | `string` | **Yes** | Non-empty unique proposal identifier. |
| `title` | `string` | **Yes** | Human-readable title of the proposal. |
| `claims` | `array` | **Yes** | List of structured claim objects. |
| `target_treasury` | `string` | No | 20-byte EVM address (`0x...`) of the Treasury. |
| `description` | `string` | No | Proposal background description. |

### Claim Object Types

Every claim object **must** contain:
- `claim_id`: Unique non-empty string identifier (e.g., `"claim-001"`).
- `type`: One of the 5 supported claim types.
- `unit`: Explicit unit designation (e.g., `"raw_tokens"`, `"wei"`, `"address"`, `"none"`).

#### 1. `TOKEN_TRANSFER`
Asserts an ERC-20 token transfer from Treasury to a recipient.
- `token`: 20-byte EVM address of ERC-20 contract.
- `recipient`: 20-byte EVM address of grant recipient.
- `amount`: Raw integer (e.g., `"5000000000000000000000000"` for 5M tokens with 18 decimals).
- `sender`: Optional 20-byte address of token sender (defaults to `target_treasury`).
- `unit`: String, e.g., `"raw_tokens"` or `"wei"`.

#### 2. `NATIVE_TRANSFER`
Asserts native ETH transfer.
- `recipient`: 20-byte EVM address.
- `amount`: Raw integer in wei.
- `unit`: Must be `"wei"`.

#### 3. `OWNERSHIP_EXPECTATION`
Asserts ownership state post-execution.
- `contract`: 20-byte EVM address.
- `expected_state`: `"UNCHANGED"` or `"SET_TO"`.
- `expected_owner`: 20-byte EVM address (required if `expected_state == "SET_TO"`).
- `unit`: `"address"`.

#### 4. `ALLOWANCE_EXPECTATION`
Asserts ERC-20 approval/allowance.
- `token`: 20-byte EVM address.
- `owner`: 20-byte EVM address.
- `spender`: 20-byte EVM address.
- `expected_allowance`: Raw integer.
- `unit`: `"raw"`.

#### 5. `FORBIDDEN_EFFECT`
Explicitly forbids specified effects.
- `effect_type`: One of:
  - `"OWNERSHIP_CHANGE"` (forbids modifying Slot 0 of target)
  - `"UNAPPROVED_TRANSFER"` (forbids any transfer not claimed)
  - `"ALLOWANCE_MUTATION"` (forbids granting allowances)
  - `"ARBITRARY_STORAGE_WRITE"` (forbids modifying any storage slot of target)
- `target`: 20-byte EVM address.
- `unit`: `"none"`.

---

## 3. Simulation Result Schema (`veritas-simulation-v1.0`)

The simulation result format produced by the Phase 2 execution harness.

### Required Top-Level Fields

All 9 fields below are mandatory. Any absent field is treated as incomplete evidence and will fail closed to `NEEDS_REVIEW`.

```json
{
  "schema_version": "veritas-simulation-v1.0",
  "scenario_id": "scenario-honest-grant-5m",
  "chain_id": 31337,
  "simulation_mode": "local_evm",
  "success": true,
  "trace_complete": true,
  "state_diffs": [],
  "logs": [],
  "findings": [],
  "errors": []
}
```

### Detailed Field Specifications

| Field | Type | Description |
| :--- | :--- | :--- |
| `scenario_id` | `string` | Unique simulation test run ID. |
| `chain_id` | `integer` | EVM network ID (e.g. `1` or `31337`). |
| `simulation_mode` | `string` | Environment descriptor: `"local_evm"`, `"fork"`, `"anvil"`. |
| `success` | `boolean` | `true` if EVM execution completed without reverting; `false` if reverted. |
| `trace_complete` | `boolean` | `true` if full EVM trace was captured without truncation or depth limit caps. |
| `state_diffs` | `array` | List of storage and balance mutations observed during execution. |
| `logs` | `array` | List of EVM event logs emitted. |
| `findings` | `array` | Security findings or opcode detections (e.g. `DELEGATECALL_DETECTED`). |
| `errors` | `array of str` | Errors or revert messages recorded during simulation. |

### Representations & Units

#### Raw Integer Units
- All token amounts, wei values, and allowances **must** be expressed in base raw units (integer or exact numeric digit string).
- For an 18-decimal token, `5,000,000` tokens = `5000000000000000000000000` ($5 \times 10^{24}$ units).
- Floats (e.g. `5.0`), ranges (e.g. `"5-10"`), and abbreviations (e.g. `"5M"`) are strictly rejected.

#### Storage Slot Representation (`state_diffs`)
```json
{
  "address": "0x1111111111111111111111111111111111111111",
  "slot": "0x0000000000000000000000000000000000000000000000000000000000000000",
  "slot_name": "owner",
  "before": "0x0000000000000000000000002222222222222222222222222222222222222222",
  "after": "0x0000000000000000000000009999999999999999999999999999999999999999"
}
```
- `address`: Target contract address.
- `slot`: 32-byte hex string or `"0x0"`.
- `before` / `after`: 32-byte hex representations of slot contents.

#### Event Log Representation (`logs`)
```json
{
  "log_index": 0,
  "address": "0xmocktokenaddress00000000000000000000001",
  "topics": [
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    "0x0000000000000000000000001111111111111111111111111111111111111111",
    "0x0000000000000000000000003333333333333333333333333333333333333333"
  ],
  "data": "0x000000000000000000000000000000000000000000000000446c3b15f9926687",
  "event_name": "Transfer",
  "decoded": {
    "from": "0x1111111111111111111111111111111111111111",
    "to": "0x3333333333333333333333333333333333333333",
    "value": "5000000000000000000000000"
  }
}
```

#### Findings Representation (`findings`)
```json
{
  "code": "DELEGATECALL_DETECTED",
  "severity": "HIGH",
  "description": "Call trace executed DELEGATECALL to external address 0xHonestPayload",
  "target": "0x5555555555555555555555555555555555555555"
}
```

---

## 4. Verdicts and Stable Reason Codes

### Output Verdicts
- `VERIFIED`: Complete, unpolluted execution matching all claims.
- `MISMATCH`: Reliable evidence proves a claim violation or unclaimed material effect.
- `NEEDS_REVIEW`: Ambiguous claims, risky operation flags, incomplete trace, or execution failure.

### Reason Codes Reference
| Category | Reason Code | Description |
| :--- | :--- | :--- |
| **VERIFIED** | `VERIFIED_ALL_CLAIMS_MATCH` | All claims verified against complete clean simulation evidence. |
| **MISMATCH** | `MISMATCH_TOKEN_TRANSFER_AMOUNT` | Observed token transfer amount differed from claim. |
| **MISMATCH** | `MISMATCH_TOKEN_TRANSFER_RECIPIENT` | Observed token transfer recipient differed from claim. |
| **MISMATCH** | `MISMATCH_TOKEN_TRANSFER_MISSING` | Required token transfer was never observed in trace. |
| **MISMATCH** | `MISMATCH_UNCLAIMED_MATERIAL_TRANSFER` | Unclaimed extra token/native transfer observed. |
| **MISMATCH** | `MISMATCH_OWNERSHIP_COLLISION` | Contract ownership slot mutated violating claims. |
| **MISMATCH** | `MISMATCH_FORBIDDEN_EFFECT_OBSERVED` | An explicitly forbidden effect was observed. |
| **MISMATCH** | `MISMATCH_UNCLAIMED_STATE_MUTATION` | Unexpected storage mutation on Treasury. |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_RISKY_OPERATION_FLAG` | Trace contains risky opcode flag (e.g. `DELEGATECALL_DETECTED`). |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_TRACE_INCOMPLETE` | Trace was incomplete or truncated (`trace_complete: false`). |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_REQUIRED_EVIDENCE_MISSING`| Required field(s) absent in simulation result. |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_SIMULATION_FAILED` | Proposal execution reverted (`success: false`). |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_SIMULATION_ERRORS` | Execution errors reported in `errors` list. |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_CLAIMS_AMBIGUOUS` | Claims validation failed or ambiguous values. |
| **NEEDS_REVIEW** | `NEEDS_REVIEW_UNSUPPORTED_CLAIM_TYPE` | Proposal specifies unrecognized claim type. |
