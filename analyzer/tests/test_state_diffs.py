"""Unit tests for state-diff generation, raw integer precision, and missing value handling."""

from analyzer.schemas import EffectType, ScenarioConfig
from analyzer.simulate import Simulator


def test_compute_diffs_token_and_native_balances():
    scenario = ScenarioConfig(
        scenario_id="diff-test",
        chain_id=31337,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
        watched_tokens=["0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"],
        watched_addresses=["0x70997970C51812dc3A010C7d01b50e0d17dc79C8"],
    )
    sim = Simulator(scenario)

    token = "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"
    treasury = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
    recipient = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"

    before_state = {
        "native_balances": {
            treasury: 10_000_000_000_000_000_000,
            recipient: 1_000_000_000_000_000_000,
        },
        "token_balances": {
            token: {
                treasury: 10_000_000 * 10**18,
                recipient: 0,
            }
        },
        "treasury_owner": {treasury: "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"},
        "allowances": {},
        "storage_slots": {},
    }

    # Simulate 5M grant transfer: Treasury -5M, Recipient +5M
    after_state = {
        "native_balances": {
            treasury: 10_000_000_000_000_000_000,  # Unchanged
            recipient: 1_000_000_000_000_000_000,  # Unchanged
        },
        "token_balances": {
            token: {
                treasury: 5_000_000 * 10**18,
                recipient: 5_000_000 * 10**18,
            }
        },
        "treasury_owner": {treasury: "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"},
        "allowances": {},
        "storage_slots": {},
    }

    diffs = sim._compute_diffs(before_state, after_state)

    # Only 2 token balances changed; native balances and owner are unchanged
    assert len(diffs) == 2

    treasury_diff = next(d for d in diffs if d.address == treasury)
    assert treasury_diff.effect_type == EffectType.TOKEN_BALANCE.value
    assert treasury_diff.token_address == token
    assert treasury_diff.before_value == 10_000_000 * 10**18
    assert treasury_diff.after_value == 5_000_000 * 10**18
    assert treasury_diff.delta == -5_000_000 * 10**18
    assert isinstance(treasury_diff.delta, int)

    recipient_diff = next(d for d in diffs if d.address == recipient)
    assert recipient_diff.before_value == 0
    assert recipient_diff.after_value == 5_000_000 * 10**18
    assert recipient_diff.delta == 5_000_000 * 10**18


def test_compute_diffs_treasury_ownership_hijack():
    scenario = ScenarioConfig(
        scenario_id="owner-diff-test",
        chain_id=31337,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    )
    sim = Simulator(scenario)
    treasury = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"
    original_owner = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
    attacker = "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc"

    before_state = {
        "native_balances": {},
        "token_balances": {},
        "treasury_owner": {treasury: original_owner},
        "allowances": {},
        "storage_slots": {treasury: {"0x0": original_owner}},
    }

    after_state = {
        "native_balances": {},
        "token_balances": {},
        "treasury_owner": {treasury: attacker},
        "allowances": {},
        "storage_slots": {treasury: {"0x0": attacker}},
    }

    diffs = sim._compute_diffs(before_state, after_state)
    assert len(diffs) == 2

    owner_diff = next(d for d in diffs if d.effect_type == EffectType.TREASURY_OWNER.value)
    assert owner_diff.before_value == original_owner
    assert owner_diff.after_value == attacker
    assert owner_diff.delta is None

    slot_diff = next(d for d in diffs if d.effect_type == EffectType.STORAGE_SLOT.value)
    assert slot_diff.before_value == original_owner
    assert slot_diff.after_value == attacker


def test_missing_values_distinguishable_from_zero():
    scenario = ScenarioConfig(
        scenario_id="null-distinction-test",
        chain_id=31337,
        sender="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        target="0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    )
    sim = Simulator(scenario)
    target = "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512"

    before_state = {
        "native_balances": {target: None},  # Account was non-existent before
        "token_balances": {},
        "treasury_owner": {},
        "allowances": {},
        "storage_slots": {},
    }
    after_state = {
        "native_balances": {target: 0},     # Exists with 0 balance
        "token_balances": {},
        "treasury_owner": {},
        "allowances": {},
        "storage_slots": {},
    }

    diffs = sim._compute_diffs(before_state, after_state)
    assert len(diffs) == 1
    assert diffs[0].before_value is None
    assert diffs[0].after_value == 0
    assert diffs[0].delta is None  # Delta cannot be computed against None
