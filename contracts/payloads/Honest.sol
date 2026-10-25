// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MockToken} from "../MockToken.sol";

/**
 * @title HonestPayload
 * @notice Honest DAO grant proposal payload.
 *
 * Denomination Specification:
 * - Decimals: 18 (MockToken standard).
 * - GRANT_AMOUNT: 5,000,000 * 10^18 (representing $5,000,000 in 18-decimal token units).
 *
 * Storage Safety:
 * - This contract declares NO storage variables.
 * - When executed via delegatecall, it touches 0 storage slots in Treasury.
 * - Treasury owner (slot 0) and token (slot 1) remain completely unaffected.
 */
contract HonestPayload {
    uint256 public constant GRANT_AMOUNT = 5_000_000 * 10**18;

    event HonestGrantDistributed(address indexed token, address indexed recipient, uint256 amount);

    error InvalidRecipientAddress();
    error InvalidTokenAddress();
    error TransferFailed();

    /**
     * @notice Distributes the 5,000,000 token grant to `recipient`.
     * @dev Designed to be executed in Treasury context (e.g. via delegatecall):
     * - `address(this)` is the Treasury holding the MockTokens.
     * - `MockToken.transfer` sends tokens from Treasury balance to recipient.
     * - No storage writes occur.
     *
     * @param tokenAddress The MockToken contract address.
     * @param recipient The grant beneficiary.
     */
    function execute(address tokenAddress, address recipient) external {
        if (recipient == address(0)) revert InvalidRecipientAddress();
        if (tokenAddress == address(0)) revert InvalidTokenAddress();

        bool success = MockToken(tokenAddress).transfer(recipient, GRANT_AMOUNT);
        if (!success) revert TransferFailed();

        emit HonestGrantDistributed(tokenAddress, recipient, GRANT_AMOUNT);
    }
}
