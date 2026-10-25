// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockToken} from "../MockToken.sol";
import {Treasury} from "../Treasury.sol";
import {HonestPayload} from "../payloads/Honest.sol";
import {MaliciousPayload} from "../payloads/Malicious.sol";

/**
 * @title Step1Test
 * @notice Phase 1 verification suite for Veritas Gate.
 *
 * Verifies:
 * 1. Honest grant distribution via Treasury execution preserves Treasury ownership and updates balances.
 * 2. Malicious payload via `delegatecall` demonstrates storage collision (hijacking Treasury ownership).
 * 3. Malicious payload via normal `call` cannot alter Treasury storage (ownership remains intact).
 * 4. Normal call execution fails safely when callee lacks authorization/balance without altering caller state.
 * 5. Access control restrictions on unauthorized callers.
 */
contract Step1Test is Test {
    MockToken public mockToken;
    Treasury public treasury;
    HonestPayload public honestPayload;
    MaliciousPayload public maliciousPayload;

    // Default test accounts (Anvil/Foundry standard)
    address public treasuryOwner;
    address public recipient;
    address public attacker;
    address public unprivilegedUser;

    uint256 public constant INITIAL_TREASURY_BALANCE = 10_000_000 * 10**18; // 10M tokens
    uint256 public constant GRANT_AMOUNT = 5_000_000 * 10**18;             // 5M tokens

    function setUp() public {
        treasuryOwner = makeAddr("treasuryOwner");
        recipient = makeAddr("recipient");
        attacker = makeAddr("attacker");
        unprivilegedUser = makeAddr("unprivilegedUser");

        // Deploy MockToken with 18 decimals and 0 initial supply to deployer
        mockToken = new MockToken("Veritas Mock Token", "MOCK", 0);

        // Deploy Treasury with treasuryOwner as initial owner
        vm.prank(treasuryOwner);
        treasury = new Treasury(address(mockToken));

        // Fund Treasury with initial balance
        mockToken.mint(address(treasury), INITIAL_TREASURY_BALANCE);

        // Deploy payload contracts
        honestPayload = new HonestPayload();
        maliciousPayload = new MaliciousPayload();
    }

    /* =========================================================================
     * 1. HONEST GRANT TESTS
     * ========================================================================= */

    /**
     * @notice Demonstrates that executing an honest grant via delegatecall:
     * - Transfers exactly 5M tokens from Treasury to recipient.
     * - Decreases Treasury balance by 5M tokens.
     * - Leaves Treasury ownership completely unchanged (honest payload has no storage variables).
     */
    function test_HonestDelegateCall_GrantDistributed_OwnershipPreserved() public {
        // --- PRE-EXECUTION STATE ---
        uint256 treasuryBalBefore = mockToken.balanceOf(address(treasury));
        uint256 recipientBalBefore = mockToken.balanceOf(recipient);
        address ownerBefore = treasury.owner();

        assertEq(treasuryBalBefore, INITIAL_TREASURY_BALANCE, "Treasury should start with 10M tokens");
        assertEq(recipientBalBefore, 0, "Recipient should start with 0 tokens");
        assertEq(ownerBefore, treasuryOwner, "Treasury owner should be treasuryOwner");

        // --- EXECUTION ---
        bytes memory data = abi.encodeWithSelector(
            HonestPayload.execute.selector,
            address(mockToken),
            recipient
        );

        vm.prank(treasuryOwner);
        treasury.executeDelegateCall(address(honestPayload), data);

        // --- POST-EXECUTION STATE ---
        uint256 treasuryBalAfter = mockToken.balanceOf(address(treasury));
        uint256 recipientBalAfter = mockToken.balanceOf(recipient);
        address ownerAfter = treasury.owner();

        assertEq(treasuryBalAfter, INITIAL_TREASURY_BALANCE - GRANT_AMOUNT, "Treasury balance should decrease by 5M");
        assertEq(recipientBalAfter, GRANT_AMOUNT, "Recipient should receive 5M tokens");
        assertEq(ownerAfter, treasuryOwner, "Treasury owner must NOT be modified by honest payload");
    }

    /**
     * @notice Demonstrates that an honest grant can also be distributed via normal call directly to token.
     */
    function test_HonestNormalCall_DirectTransfer() public {
        // --- PRE-EXECUTION STATE ---
        assertEq(mockToken.balanceOf(address(treasury)), INITIAL_TREASURY_BALANCE);
        assertEq(mockToken.balanceOf(recipient), 0);
        assertEq(treasury.owner(), treasuryOwner);

        // --- EXECUTION ---
        bytes memory transferData = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        vm.prank(treasuryOwner);
        treasury.executeCall(address(mockToken), 0, transferData);

        // --- POST-EXECUTION STATE ---
        assertEq(mockToken.balanceOf(address(treasury)), INITIAL_TREASURY_BALANCE - GRANT_AMOUNT);
        assertEq(mockToken.balanceOf(recipient), GRANT_AMOUNT);
        assertEq(treasury.owner(), treasuryOwner);
    }

    /* =========================================================================
     * 2. MALICIOUS DELEGATECALL TESTS (EXPLOIT DEMONSTRATION)
     * ========================================================================= */

    /**
     * @notice Demonstrates the delegatecall storage collision vulnerability:
     * - The malicious payload transfers 5M tokens to recipient.
     * - BUT ALSO overwrites Slot 0 of Treasury storage with attacker's address.
     * - Result: Treasury ownership is hijacked!
     */
    function test_MaliciousDelegateCall_GrantDistributed_OwnershipHijacked() public {
        // --- PRE-EXECUTION STATE ---
        uint256 treasuryBalBefore = mockToken.balanceOf(address(treasury));
        uint256 recipientBalBefore = mockToken.balanceOf(recipient);
        address ownerBefore = treasury.owner();

        assertEq(treasuryBalBefore, INITIAL_TREASURY_BALANCE, "Treasury should start with 10M tokens");
        assertEq(recipientBalBefore, 0, "Recipient should start with 0 tokens");
        assertEq(ownerBefore, treasuryOwner, "Treasury owner should initially be treasuryOwner");

        // --- EXECUTION ---
        bytes memory exploitData = abi.encodeWithSelector(
            MaliciousPayload.execute.selector,
            address(mockToken),
            recipient,
            attacker
        );

        vm.prank(treasuryOwner);
        treasury.executeDelegateCall(address(maliciousPayload), exploitData);

        // --- POST-EXECUTION STATE ---
        uint256 treasuryBalAfter = mockToken.balanceOf(address(treasury));
        uint256 recipientBalAfter = mockToken.balanceOf(recipient);
        address ownerAfter = treasury.owner();

        // 1. Funds were distributed
        assertEq(treasuryBalAfter, INITIAL_TREASURY_BALANCE - GRANT_AMOUNT, "Treasury balance decreased by 5M");
        assertEq(recipientBalAfter, GRANT_AMOUNT, "Recipient received 5M tokens");

        // 2. CRITICAL EXPLOIT: Treasury ownership was seized by attacker!
        assertEq(ownerAfter, attacker, "VULNERABILITY: Attacker successfully seized Treasury ownership via slot 0 collision!");
        assertTrue(ownerAfter != treasuryOwner, "Original owner should have been displaced");
    }

    /* =========================================================================
     * 3. MALICIOUS NORMAL CALL ISOLATION TESTS
     * ========================================================================= */

    /**
     * @notice Demonstrates EVM storage isolation during normal `call`:
     * When Treasury executes the malicious payload via normal `call`, the payload's
     * code runs in MaliciousPayload's own context.
     * - Treasury's storage (Slot 0) CANNOT be touched by the callee.
     * - The token transfer fails because MaliciousPayload has no tokens.
     * - The revert is bubbled up, and Treasury state remains 100% pristine.
     */
    function test_MaliciousNormalCall_CannotChangeTreasuryStorage_RevertsSafely() public {
        // --- PRE-EXECUTION STATE ---
        uint256 treasuryBalBefore = mockToken.balanceOf(address(treasury));
        uint256 recipientBalBefore = mockToken.balanceOf(recipient);
        address ownerBefore = treasury.owner();

        assertEq(treasuryBalBefore, INITIAL_TREASURY_BALANCE);
        assertEq(recipientBalBefore, 0);
        assertEq(ownerBefore, treasuryOwner);

        // --- EXECUTION ---
        bytes memory exploitData = abi.encodeWithSelector(
            MaliciousPayload.execute.selector,
            address(mockToken),
            recipient,
            attacker
        );

        // In normal call: MaliciousPayload attempts mockToken.transfer, but MaliciousPayload has 0 tokens.
        // It reverts with InsufficientBalance, bubbled by Treasury.executeCall.
        vm.expectRevert(
            abi.encodeWithSelector(
                MockToken.InsufficientBalance.selector,
                address(maliciousPayload),
                0,
                GRANT_AMOUNT
            )
        );
        vm.prank(treasuryOwner);
        treasury.executeCall(address(maliciousPayload), 0, exploitData);

        // --- POST-EXECUTION STATE ---
        uint256 treasuryBalAfter = mockToken.balanceOf(address(treasury));
        uint256 recipientBalAfter = mockToken.balanceOf(recipient);
        address ownerAfter = treasury.owner();

        assertEq(treasuryBalAfter, INITIAL_TREASURY_BALANCE, "Treasury balance must remain untouched");
        assertEq(recipientBalAfter, 0, "Recipient should have received nothing");
        assertEq(ownerAfter, treasuryOwner, "Treasury owner MUST NOT be altered by normal call");
    }

    /**
     * @notice Demonstrates that even if the malicious payload is independently funded and
     * successfully executes via normal `call`, only MaliciousPayload's own storage is modified.
     * Treasury storage remains completely unaffected.
     */
    function test_MaliciousNormalCall_EvenIfFunded_CannotModifyTreasuryOwner() public {
        // Fund the malicious payload contract directly with 5M tokens
        mockToken.mint(address(maliciousPayload), GRANT_AMOUNT);

        // Assert pre-conditions
        assertEq(treasury.owner(), treasuryOwner);
        assertEq(maliciousPayload.hijackedOwner(), address(0));

        bytes memory exploitData = abi.encodeWithSelector(
            MaliciousPayload.execute.selector,
            address(mockToken),
            recipient,
            attacker
        );

        // Execute via normal call from Treasury
        vm.prank(treasuryOwner);
        treasury.executeCall(address(maliciousPayload), 0, exploitData);

        // Assert post-conditions
        // 1. Treasury owner was NOT touched
        assertEq(treasury.owner(), treasuryOwner, "Treasury owner must NOT change on normal call");
        // 2. Only MaliciousPayload's internal slot 0 was updated
        assertEq(maliciousPayload.hijackedOwner(), attacker, "Only MaliciousPayload's own slot 0 updated");
        // 3. Treasury's own balance was NOT spent
        assertEq(mockToken.balanceOf(address(treasury)), INITIAL_TREASURY_BALANCE);
        // 4. Recipient received tokens from malicious payload's balance
        assertEq(mockToken.balanceOf(recipient), GRANT_AMOUNT);
    }

    /* =========================================================================
     * 4. ACCESS CONTROL AND EDGE CASES
     * ========================================================================= */

    function test_UnauthorizedCaller_RevertsOnExecuteCall() public {
        bytes memory data = abi.encodeWithSelector(mockToken.transfer.selector, recipient, 100);

        vm.prank(unprivilegedUser);
        vm.expectRevert(abi.encodeWithSelector(Treasury.Unauthorized.selector, unprivilegedUser));
        treasury.executeCall(address(mockToken), 0, data);
    }

    function test_UnauthorizedCaller_RevertsOnExecuteDelegateCall() public {
        bytes memory data = abi.encodeWithSelector(
            HonestPayload.execute.selector,
            address(mockToken),
            recipient
        );

        vm.prank(unprivilegedUser);
        vm.expectRevert(abi.encodeWithSelector(Treasury.Unauthorized.selector, unprivilegedUser));
        treasury.executeDelegateCall(address(honestPayload), data);
    }
}
