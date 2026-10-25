// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title Treasury
 * @notice Educational harness contract demonstrating standard call vs delegatecall semantics.
 *
 * STORAGE LAYOUT SPECIFICATION:
 * In EVM, state variables are allocated fixed storage slots sequentially:
 * - Slot 0: address public owner (20 bytes)
 * - Slot 1: address public token (20 bytes)
 *
 * CRITICAL SECURITY NOTICE / DELEGATECALL HAZARD:
 * `delegatecall` preserves the caller's context (`address(this)`, `msg.sender`, `msg.value`,
 * and storage space). When a target is executed via `delegatecall`, any storage writes performed
 * by the target contract modify the storage slots of THIS contract (Treasury), NOT the target!
 * Exposing arbitrary `delegatecall` allows an attacker-controlled or misconfigured payload to
 * overwrite Slot 0 (`owner`), hijacking contract ownership.
 */
contract Treasury {
    // Storage Slot 0: Contract owner authorized to trigger calls
    address public owner;

    // Storage Slot 1: Primary ERC-20 token address held in Treasury
    address public token;

    // Execution Events
    event CallExecuted(address indexed target, uint256 value, bytes data, bytes returnData);
    event DelegateCallExecuted(address indexed target, bytes data, bytes returnData);

    // Custom Errors
    error Unauthorized(address caller);
    error TargetZeroAddress();
    error CallExecutionFailed(bytes revertData);
    error DelegateCallExecutionFailed(bytes revertData);

    modifier onlyOwner() {
        if (msg.sender != owner) {
            revert Unauthorized(msg.sender);
        }
        _;
    }

    /**
     * @param _token The ERC-20 token managed by this Treasury.
     */
    constructor(address _token) {
        owner = msg.sender;
        token = _token;
    }

    /**
     * @notice Allows Treasury to receive native ETH.
     */
    receive() external payable {}

    /**
     * @notice Executes an arbitrary normal call from the Treasury context.
     * @dev Context of the callee:
     * - `msg.sender` inside `target` is `address(this)` (the Treasury).
     * - Target's own storage is modified; Treasury storage is completely isolated and safe.
     *
     * If the target reverts, the full revert payload is bubbled up.
     *
     * @param target The target contract or external address to invoke.
     * @param value Native wei value sent along with the call.
     * @param data Calldata payload for the invocation.
     * @return returnData Bytes returned by the invoked target.
     */
    function executeCall(
        address target,
        uint256 value,
        bytes calldata data
    ) external payable onlyOwner returns (bytes memory returnData) {
        if (target == address(0)) revert TargetZeroAddress();

        bool success;
        (success, returnData) = target.call{value: value}(data);

        if (!success) {
            _bubbleRevert(returnData);
        }

        emit CallExecuted(target, value, data, returnData);
    }

    /**
     * @notice DEMONSTRATION ONLY: Executes an arbitrary delegatecall in Treasury context.
     * @dev WARNING: Extremely dangerous in production architectures.
     *
     * Context of the delegatecall:
     * - Code executed is from `target`.
     * - Execution runs within Treasury storage, with Treasury balance and caller context.
     * - Any state variable mutations inside `target` directly alter Treasury storage slots.
     *
     * If the target reverts, the full revert payload is bubbled up.
     *
     * @param target The payload contract containing code to execute.
     * @param data Calldata passed to the target contract.
     * @return returnData Bytes returned by the executed delegatecall.
     */
    function executeDelegateCall(
        address target,
        bytes calldata data
    ) external onlyOwner returns (bytes memory returnData) {
        if (target == address(0)) revert TargetZeroAddress();

        bool success;
        (success, returnData) = target.delegatecall(data);

        if (!success) {
            _bubbleRevert(returnData);
        }

        emit DelegateCallExecuted(target, data, returnData);
    }

    /**
     * @dev Bubbles up revert reason from low-level calls, preserving custom errors and revert strings.
     * @param returnData Return bytes from failed low-level call.
     */
    function _bubbleRevert(bytes memory returnData) internal pure {
        if (returnData.length > 0) {
            assembly {
                let returndata_size := mload(returnData)
                revert(add(32, returnData), returndata_size)
            }
        } else {
            revert CallExecutionFailed(returnData);
        }
    }
}
