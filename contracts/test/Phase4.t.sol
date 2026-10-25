// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {ProposalRegistry} from "../ProposalRegistry.sol";
import {VerdictOracle} from "../VerdictOracle.sol";
import {GuardedTreasury} from "../GuardedTreasury.sol";
import {MockToken} from "../MockToken.sol";
import {HonestPayload} from "../payloads/Honest.sol";
import {MaliciousPayload} from "../payloads/Malicious.sol";

/**
 * @title Phase4Test
 * @notice Comprehensive security test suite for Veritas Gate Phase 4 governance contracts & Treasury guard.
 */
contract Phase4Test is Test {
    ProposalRegistry public registry;
    VerdictOracle public oracle;
    GuardedTreasury public treasury;
    MockToken public mockToken;
    HonestPayload public honestPayload;
    MaliciousPayload public maliciousPayload;

    // Accounts
    address public governanceOwner;
    address public analyzer;
    address public reviewer1;
    address public reviewer2;
    address public challenger;
    address public recipient;
    address public attacker;

    address public guardianA;
    address public guardianB;
    address public guardianC;
    address public unauthorizedUser;

    uint256 public constant CHALLENGE_WINDOW = 2 days;
    uint256 public constant INITIAL_TREASURY_BALANCE = 10_000_000 * 10**18;
    uint256 public constant GRANT_AMOUNT = 5_000_000 * 10**18;

    bytes32 public constant PROPOSAL_1 = bytes32("PROPOSAL-1");
    bytes32 public constant TEXT_HASH_1 = keccak256("Grant $5M to honest recipient for protocol research");
    bytes32 public constant EVIDENCE_HASH_1 = keccak256("simulation-evidence-run-001");

    function setUp() public {
        governanceOwner = makeAddr("governanceOwner");
        analyzer = makeAddr("analyzer");
        reviewer1 = makeAddr("reviewer1");
        reviewer2 = makeAddr("reviewer2");
        challenger = makeAddr("challenger");
        recipient = makeAddr("recipient");
        attacker = makeAddr("attacker");
        unauthorizedUser = makeAddr("unauthorizedUser");

        guardianA = makeAddr("guardianA");
        guardianB = makeAddr("guardianB");
        guardianC = makeAddr("guardianC");

        // 1. Deploy Tokens & Payloads
        mockToken = new MockToken("Veritas Mock Token", "MOCK", 0);
        honestPayload = new HonestPayload();
        maliciousPayload = new MaliciousPayload();

        // 2. Deploy Governance Contracts
        registry = new ProposalRegistry();

        vm.prank(governanceOwner);
        oracle = new VerdictOracle(analyzer);

        address[3] memory guardiansList = [guardianA, guardianB, guardianC];
        vm.prank(governanceOwner);
        treasury = new GuardedTreasury(
            address(registry),
            address(oracle),
            guardiansList,
            CHALLENGE_WINDOW
        );

        // 3. Fund GuardedTreasury
        mockToken.mint(address(treasury), INITIAL_TREASURY_BALANCE);

        // 4. Register Reviewer
        vm.prank(governanceOwner);
        oracle.setReviewer(reviewer1, true);
    }

    // =========================================================================
    // 1. PROPOSAL REGISTRY TESTS
    // =========================================================================

    function test_SubmitProposal_Success() public {
        bytes32 calldataHash = keccak256("calldata-1");
        address[] memory wallets = new address[](1);
        wallets[0] = recipient;

        vm.prank(governanceOwner);
        uint256 ver = registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        assertEq(ver, 1);
        assertEq(registry.latestVersion(PROPOSAL_1), 1);
        assertEq(registry.proposalAuthor(PROPOSAL_1), governanceOwner);

        ProposalRegistry.ProposalVersion memory pv = registry.getProposalVersion(PROPOSAL_1, 1);
        assertEq(pv.version, 1);
        assertEq(pv.textHash, TEXT_HASH_1);
        assertEq(pv.calldataHash, calldataHash);
        assertEq(pv.author, governanceOwner);
        assertEq(pv.disclosedWallets[0], recipient);
    }

    function test_UpdateProposal_PreservesHistory() public {
        bytes32 calldataHash1 = keccak256("calldata-1");
        bytes32 calldataHash2 = keccak256("calldata-2");
        bytes32 textHash2 = keccak256("revised proposal text");
        address[] memory wallets = new address[](0);

        vm.startPrank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash1, wallets);

        // Update creates version 2
        uint256 ver2 = registry.updateProposal(PROPOSAL_1, textHash2, calldataHash2, wallets);
        vm.stopPrank();

        assertEq(ver2, 2);
        assertEq(registry.latestVersion(PROPOSAL_1), 2);

        // Version 1 remains accessible and immutable
        ProposalRegistry.ProposalVersion memory pv1 = registry.getProposalVersion(PROPOSAL_1, 1);
        assertEq(pv1.version, 1);
        assertEq(pv1.textHash, TEXT_HASH_1);
        assertEq(pv1.calldataHash, calldataHash1);

        // Version 2 has new data
        ProposalRegistry.ProposalVersion memory pv2 = registry.getProposalVersion(PROPOSAL_1, 2);
        assertEq(pv2.version, 2);
        assertEq(pv2.textHash, textHash2);
        assertEq(pv2.calldataHash, calldataHash2);
    }

    function test_VerifyLatestHashes() public {
        bytes32 calldataHash = keccak256("calldata-1");
        address[] memory wallets = new address[](0);

        vm.prank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        (bool valid, uint256 currentVer) = registry.verifyLatestHashes(PROPOSAL_1, TEXT_HASH_1, calldataHash);
        assertTrue(valid);
        assertEq(currentVer, 1);

        (bool invalidText, ) = registry.verifyLatestHashes(PROPOSAL_1, keccak256("wrong text"), calldataHash);
        assertFalse(invalidText);

        (bool invalidCall, ) = registry.verifyLatestHashes(PROPOSAL_1, TEXT_HASH_1, keccak256("wrong calldata"));
        assertFalse(invalidCall);
    }

    function test_ProposalRegistry_Rejections() public {
        address[] memory wallets = new address[](0);
        bytes32 calldataHash = keccak256("calldata-1");

        // Reject empty proposal ID
        vm.expectRevert(abi.encodeWithSelector(ProposalRegistry.EmptyProposalId.selector));
        registry.submitProposal(bytes32(0), TEXT_HASH_1, calldataHash, wallets);

        // Reject empty text hash
        vm.expectRevert(abi.encodeWithSelector(ProposalRegistry.EmptyTextHash.selector));
        registry.submitProposal(PROPOSAL_1, bytes32(0), calldataHash, wallets);

        // Reject duplicate proposal ID on submitProposal
        vm.prank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        vm.prank(governanceOwner);
        vm.expectRevert(abi.encodeWithSelector(ProposalRegistry.ProposalAlreadyExists.selector, PROPOSAL_1));
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        // Reject unauthorized author updating proposal
        vm.prank(unauthorizedUser);
        vm.expectRevert(
            abi.encodeWithSelector(ProposalRegistry.UnauthorizedAuthor.selector, PROPOSAL_1, unauthorizedUser, governanceOwner)
        );
        registry.updateProposal(PROPOSAL_1, keccak256("new text"), calldataHash, wallets);

        // Reject duplicate identical content update
        vm.prank(governanceOwner);
        vm.expectRevert(abi.encodeWithSelector(ProposalRegistry.DuplicateVersionContent.selector, PROPOSAL_1, 1));
        registry.updateProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);
    }

    // =========================================================================
    // 2. VERDICT ORACLE TESTS
    // =========================================================================

    function test_UnauthorizedOracleVerdictPosting_Reverts() public {
        vm.prank(unauthorizedUser);
        vm.expectRevert(abi.encodeWithSelector(VerdictOracle.UnauthorizedAnalyzer.selector, unauthorizedUser));
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED,
            TEXT_HASH_1,
            keccak256("calldata-1"),
            EVIDENCE_HASH_1,
            true
        );
    }

    function test_UnauthorizedReviewPosting_Reverts() public {
        // Post a valid verdict first
        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW,
            TEXT_HASH_1,
            keccak256("calldata-1"),
            EVIDENCE_HASH_1,
            false
        );

        // Unauthorized reviewer attempts review
        vm.prank(unauthorizedUser);
        vm.expectRevert(abi.encodeWithSelector(VerdictOracle.UnauthorizedReviewer.selector, unauthorizedUser));
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.APPROVE, keccak256("reason"));
    }

    function test_PostReview_Success_PreservesHistory() public {
        bytes32 calldataHash = keccak256("calldata-1");
        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW,
            TEXT_HASH_1,
            calldataHash,
            EVIDENCE_HASH_1,
            false
        );

        // Review 1: Escalate
        bytes32 reason1 = keccak256("Needs economic security review");
        vm.prank(reviewer1);
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.ESCALATE, reason1);

        // Check latest review
        VerdictOracle.HumanReview memory lr1 = oracle.getLatestReview(PROPOSAL_1, 1);
        assertEq(uint8(lr1.decision), uint8(VerdictOracle.ReviewDecision.ESCALATE));
        assertEq(lr1.reviewer, reviewer1);
        assertEq(lr1.reasonHash, reason1);

        // Review 2: Authorize reviewer2 and post Approve
        vm.prank(governanceOwner);
        oracle.setReviewer(reviewer2, true);

        bytes32 reason2 = keccak256("Economic review satisfied, approved");
        vm.prank(reviewer2);
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.APPROVE, reason2);

        // Check latest review is updated
        VerdictOracle.HumanReview memory lr2 = oracle.getLatestReview(PROPOSAL_1, 1);
        assertEq(uint8(lr2.decision), uint8(VerdictOracle.ReviewDecision.APPROVE));
        assertEq(lr2.reviewer, reviewer2);

        // Check entire review history is preserved (length 2)
        VerdictOracle.HumanReview[] memory history = oracle.getReviewHistory(PROPOSAL_1, 1);
        assertEq(history.length, 2);
        assertEq(history[0].reviewer, reviewer1);
        assertEq(history[1].reviewer, reviewer2);

        // Automated verdict remains untouched
        VerdictOracle.AutomatedVerdict memory v = oracle.getVerdict(PROPOSAL_1, 1);
        assertEq(uint8(v.status), uint8(VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW));
    }

    function test_RejectReviewOnMismatchVerdict() public {
        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.MISMATCH,
            TEXT_HASH_1,
            keccak256("calldata-1"),
            EVIDENCE_HASH_1,
            true
        );

        vm.prank(reviewer1);
        vm.expectRevert(abi.encodeWithSelector(VerdictOracle.ReviewNotPermittedOnMismatch.selector, PROPOSAL_1, 1));
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.APPROVE, keccak256("approve"));
    }

    function test_ChallengeLifecycle_RaiseAndResolve() public {
        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED,
            TEXT_HASH_1,
            keccak256("calldata-1"),
            EVIDENCE_HASH_1,
            true
        );

        // Raise challenge
        bytes32 challengeReason = keccak256("Disputed simulation assumptions");
        vm.prank(challenger);
        uint256 idx = oracle.raiseChallenge(PROPOSAL_1, 1, challengeReason);
        assertEq(idx, 0);
        assertTrue(oracle.hasActiveChallenge(PROPOSAL_1, 1));

        // Attempting another challenge while active reverts
        vm.prank(challenger);
        vm.expectRevert(abi.encodeWithSelector(VerdictOracle.ChallengeAlreadyActive.selector, PROPOSAL_1, 1));
        oracle.raiseChallenge(PROPOSAL_1, 1, challengeReason);

        // Resolve challenge successfully (disqualifying proposal)
        vm.prank(governanceOwner);
        oracle.resolveChallenge(PROPOSAL_1, 1, idx, true);

        assertFalse(oracle.hasActiveChallenge(PROPOSAL_1, 1));
        assertTrue(oracle.isDisqualified(PROPOSAL_1, 1));

        (bool eligible, string memory reason) = oracle.isEligibleForExecution(PROPOSAL_1, 1);
        assertFalse(eligible);
        assertEq(reason, "Proposal disqualified by successful challenge");
    }

    // =========================================================================
    // 3. GUARDED TREASURY EXECUTION TESTS
    // =========================================================================

    function _setupProposalAndVerdict(
        address targetContract,
        bytes memory executionData,
        VerdictOracle.AutomatedVerdictStatus verdictStatus
    ) internal returns (bytes32 calldataHash) {
        calldataHash = keccak256(executionData);

        // 1. Submit proposal to registry
        address[] memory wallets = new address[](1);
        wallets[0] = recipient;
        vm.prank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        // 2. Post verdict to oracle
        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            verdictStatus,
            TEXT_HASH_1,
            calldataHash,
            EVIDENCE_HASH_1,
            true
        );

        // 3. Authorize proposal in GuardedTreasury
        vm.prank(governanceOwner);
        treasury.authorizeProposal(PROPOSAL_1, 1, targetContract, 0);
    }

    function test_ExecuteProposal_Verified_Success() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        // Pre-execution balances
        assertEq(mockToken.balanceOf(address(treasury)), INITIAL_TREASURY_BALANCE);
        assertEq(mockToken.balanceOf(recipient), 0);

        // Fast forward past challenge window
        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // Execute proposal
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);

        // Post-execution balances
        assertEq(mockToken.balanceOf(address(treasury)), INITIAL_TREASURY_BALANCE - GRANT_AMOUNT);
        assertEq(mockToken.balanceOf(recipient), GRANT_AMOUNT);
        assertTrue(treasury.executed(PROPOSAL_1, 1));
    }

    function test_ExecuteProposal_NeedsReview_Approved_Success() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW
        );

        // Authorized reviewer approves
        vm.prank(reviewer1);
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.APPROVE, keccak256("Human approval granted"));

        // Warp past challenge window
        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // Execution succeeds
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);

        assertEq(mockToken.balanceOf(recipient), GRANT_AMOUNT);
        assertTrue(treasury.executed(PROPOSAL_1, 1));
    }

    function test_ExecutionBlocked_ByMismatch() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.MISMATCH
        );

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.IneligibleVerdict.selector,
                "Automated verdict is MISMATCH; execution permanently blocked"
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByNeedsReview_WithoutApproval() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW
        );

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // Fails because no human review approval was posted
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.IneligibleVerdict.selector,
                "NEEDS_REVIEW awaiting authorized human review"
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByRejectReview() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW
        );

        // Reviewer rejects
        vm.prank(reviewer1);
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.REJECT, keccak256("Rejected: unsafe pattern"));

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.IneligibleVerdict.selector,
                "NEEDS_REVIEW rejected by human review"
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByChallengeWindowNotElapsed() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        // Advance only 1 day (less than 2-day challenge window)
        vm.warp(block.timestamp + 1 days);

        uint256 executableAt = block.timestamp - 1 days + CHALLENGE_WINDOW;
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.ChallengeWindowActive.selector,
                executableAt,
                block.timestamp
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByActiveChallenge() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        // Raise active challenge
        vm.prank(challenger);
        oracle.raiseChallenge(PROPOSAL_1, 1, keccak256("Unresolved challenge"));

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(abi.encodeWithSelector(GuardedTreasury.ActiveChallengePending.selector));
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByCalldataHashMismatch() public {
        bytes memory honestCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        bytes32 registeredHash = _setupProposalAndVerdict(
            address(mockToken),
            honestCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // Attacker substitutes unapproved calldata (e.g. transfer to attacker)
        bytes memory substitutedCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            attacker,
            GRANT_AMOUNT
        );

        bytes32 actualHash = keccak256(substitutedCalldata);
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.CalldataHashMismatch.selector,
                registeredHash,
                actualHash
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, substitutedCalldata);
    }

    function test_ExecutionBlocked_ByReplayAttempt() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // First execution succeeds
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);

        // Second execution attempt reverts due to replay protection
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.ProposalAlreadyExecuted.selector,
                PROPOSAL_1,
                1
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    // =========================================================================
    // 4. 2-OF-3 GUARDIAN EMERGENCY PAUSE TESTS
    // =========================================================================

    function test_GuardianEmergencyPause_TwoOfThreeRequirement() public {
        bytes32 reasonHash = keccak256("Detected suspicious mempool front-running activity");

        // 1. Non-guardian cannot propose pause
        vm.prank(unauthorizedUser);
        vm.expectRevert(abi.encodeWithSelector(GuardedTreasury.UnauthorizedCaller.selector, unauthorizedUser));
        treasury.proposeEmergencyPause(reasonHash);

        // 2. Guardian A alone proposes pause: NOT paused yet (only 1 of 3)
        vm.prank(guardianA);
        treasury.proposeEmergencyPause(reasonHash);

        assertFalse(treasury.isPaused());
        assertEq(treasury.pauseApprovalCounts(reasonHash), 1);

        // Duplicate call from Guardian A reverts
        vm.prank(guardianA);
        vm.expectRevert(abi.encodeWithSelector(GuardedTreasury.GuardianAlreadyApproved.selector));
        treasury.proposeEmergencyPause(reasonHash);

        // 3. Guardian B confirms with same reasonHash: 2 of 3 reached -> PAUSED!
        vm.prank(guardianB);
        treasury.proposeEmergencyPause(reasonHash);

        assertTrue(treasury.isPaused());
        assertEq(treasury.pauseReasonHash(), reasonHash);

        // 4. When paused, proposal execution is blocked
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );
        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );
        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(abi.encodeWithSelector(GuardedTreasury.TreasuryPaused.selector, reasonHash));
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);

        // 5. Unpausing requires 2 guardians (or owner)
        // Guardian A votes to unpause (1 approval, still paused)
        vm.prank(guardianA);
        treasury.proposeUnpause();
        assertTrue(treasury.isPaused());

        // Guardian C votes to unpause (2 approvals reached -> UNPAUSED!)
        vm.prank(guardianC);
        treasury.proposeUnpause();
        assertFalse(treasury.isPaused());

        // Now proposal can execute!
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
        assertEq(mockToken.balanceOf(recipient), GRANT_AMOUNT);
    }

    // =========================================================================
    // 5. ADDITIONAL FOCUSED PHASE 4 TESTS
    // =========================================================================

    function test_ExecutionBlocked_ByTextHashCommitmentMismatch() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );
        bytes32 calldataHash = keccak256(transferCalldata);

        // 1. Submit proposal with TEXT_HASH_1 to registry
        address[] memory wallets = new address[](1);
        wallets[0] = recipient;
        vm.prank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        // 2. Post verdict to oracle with a DIFFERENT text hash (e.g. altered specification)
        bytes32 alteredTextHash = keccak256("Altered specification text");
        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED,
            alteredTextHash,
            calldataHash,
            EVIDENCE_HASH_1,
            true
        );

        // 3. Authorize proposal
        vm.prank(governanceOwner);
        treasury.authorizeProposal(PROPOSAL_1, 1, address(mockToken), 0);

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // Treasury rejects execution because oracle textHash != registry textHash
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.RegistryOracleCommitmentMismatch.selector,
                PROPOSAL_1,
                1
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByUnauthorizedProposal() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );
        bytes32 calldataHash = keccak256(transferCalldata);

        address[] memory wallets = new address[](1);
        wallets[0] = recipient;
        vm.prank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        vm.prank(analyzer);
        oracle.postVerdict(
            PROPOSAL_1,
            1,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED,
            TEXT_HASH_1,
            calldataHash,
            EVIDENCE_HASH_1,
            true
        );

        // DO NOT authorize proposal in GuardedTreasury
        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.ProposalNotAuthorized.selector,
                PROPOSAL_1,
                1
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByTargetOrValueMismatch() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        // Target mismatch
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.TargetMismatch.selector,
                address(mockToken),
                attacker
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, attacker, 0, transferCalldata);

        // Value mismatch
        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.ValueMismatch.selector,
                0,
                1 ether
            )
        );
        treasury.executeProposal{value: 1 ether}(PROPOSAL_1, 1, address(mockToken), 1 ether, transferCalldata);
    }

    function test_ExecutionBlocked_ByDisqualification() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        // Raise and uphold challenge as successful
        vm.prank(challenger);
        uint256 idx = oracle.raiseChallenge(PROPOSAL_1, 1, keccak256("Critical vulnerability found"));

        vm.prank(governanceOwner);
        oracle.resolveChallenge(PROPOSAL_1, 1, idx, true);

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(abi.encodeWithSelector(GuardedTreasury.ProposalDisqualified.selector));
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_ExecutionBlocked_ByVerifiedProposalEscalated() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.VERIFIED
        );

        // Human reviewer escalates a VERIFIED proposal for additional scrutiny
        vm.prank(reviewer1);
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.ESCALATE, keccak256("Flagged for governance audit"));

        vm.warp(block.timestamp + CHALLENGE_WINDOW + 1);

        vm.expectRevert(
            abi.encodeWithSelector(
                GuardedTreasury.IneligibleVerdict.selector,
                "VERIFIED proposal escalated by human review override"
            )
        );
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
    }

    function test_GuardianEmergencyPause_DifferentReasonHashesDoNotPause() public {
        bytes32 reasonA = keccak256("Reason A: front-running");
        bytes32 reasonB = keccak256("Reason B: oracle delay");

        // Guardian A votes reason A
        vm.prank(guardianA);
        treasury.proposeEmergencyPause(reasonA);
        assertFalse(treasury.isPaused());
        assertEq(treasury.pauseApprovalCounts(reasonA), 1);

        // Guardian B votes DIFFERENT reason B (does NOT reach 2 on either reason)
        vm.prank(guardianB);
        treasury.proposeEmergencyPause(reasonB);
        assertFalse(treasury.isPaused());
        assertEq(treasury.pauseApprovalCounts(reasonA), 1);
        assertEq(treasury.pauseApprovalCounts(reasonB), 1);

        // Guardian C confirms reason A (now reason A reaches 2-of-3 threshold -> PAUSED)
        vm.prank(guardianC);
        treasury.proposeEmergencyPause(reasonA);
        assertTrue(treasury.isPaused());
        assertEq(treasury.pauseReasonHash(), reasonA);
    }

    function test_GuardianEmergencyPause_RejectsEmptyReasonHash() public {
        vm.prank(guardianA);
        vm.expectRevert(abi.encodeWithSelector(GuardedTreasury.EmptyHash.selector));
        treasury.proposeEmergencyPause(bytes32(0));
    }

    function test_ChallengeWindow_EnforcedFromHumanApprovalTime() public {
        bytes memory transferCalldata = abi.encodeWithSelector(
            mockToken.transfer.selector,
            recipient,
            GRANT_AMOUNT
        );

        _setupProposalAndVerdict(
            address(mockToken),
            transferCalldata,
            VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW
        );

        // Advance 5 days past initial automated verdict
        vm.warp(block.timestamp + 5 days);

        // Human review approves at day 5
        vm.prank(reviewer1);
        oracle.postReview(PROPOSAL_1, 1, VerdictOracle.ReviewDecision.APPROVE, keccak256("Approved at day 5"));

        // Advance only 1 day from approval (less than 2-day challenge window)
        vm.warp(block.timestamp + 1 days);

        // Execution is blocked because challenge window has not elapsed since human approval
        vm.expectRevert();
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);

        // Advance 2 more days (3 days total since approval, exceeding 2-day window)
        vm.warp(block.timestamp + 2 days);

        // Execution succeeds
        treasury.executeProposal(PROPOSAL_1, 1, address(mockToken), 0, transferCalldata);
        assertEq(mockToken.balanceOf(recipient), GRANT_AMOUNT);
    }

    function test_ProposalRegistry_VersionQueryHelpers() public {
        bytes32 calldataHash = keccak256("calldata-v1");
        address[] memory wallets = new address[](1);
        wallets[0] = recipient;

        vm.prank(governanceOwner);
        registry.submitProposal(PROPOSAL_1, TEXT_HASH_1, calldataHash, wallets);

        // test getLatestProposalVersion
        ProposalRegistry.ProposalVersion memory latest = registry.getLatestProposalVersion(PROPOSAL_1);
        assertEq(latest.version, 1);
        assertEq(latest.textHash, TEXT_HASH_1);
        assertEq(latest.calldataHash, calldataHash);

        // test verifyVersionHashes
        assertTrue(registry.verifyVersionHashes(PROPOSAL_1, 1, TEXT_HASH_1, calldataHash));
        assertFalse(registry.verifyVersionHashes(PROPOSAL_1, 1, keccak256("wrong"), calldataHash));
        assertFalse(registry.verifyVersionHashes(PROPOSAL_1, 2, TEXT_HASH_1, calldataHash));
    }
}
