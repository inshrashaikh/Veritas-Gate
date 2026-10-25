// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ProposalRegistry} from "./ProposalRegistry.sol";
import {VerdictOracle} from "./VerdictOracle.sol";

/**
 * @title GuardedTreasury
 * @notice Production-intent, guard-enforced Treasury for Veritas Gate governance execution.
 *
 * Security & Guard Architecture:
 * 1. Safe Normal-Call Execution ONLY: The unrestricted delegatecall path from Phase 1 is removed.
 * 2. Immutable Hash Binding: Calldata executed must match ProposalRegistry and VerdictOracle commitments.
 * 3. Oracle Verification Guard: Executes only if VERIFIED or explicitly human-APPROVED (NEEDS_REVIEW).
 * 4. Challenge Window Guard: Rejects execution before the challenge window elapses or if an active challenge exists.
 * 5. Replay Protection: A proposal version can execute at most once.
 * 6. 2-of-3 Guardian Emergency Pause: Requires agreement of at least 2 distinct guardians to pause; no single guardian can pause alone.
 */
contract GuardedTreasury {
    // Registry and Oracle contracts
    ProposalRegistry public immutable proposalRegistry;
    VerdictOracle public immutable verdictOracle;

    // Governance owner
    address public owner;

    // Default challenge window: 2 days (172,800 seconds)
    uint256 public constant DEFAULT_CHALLENGE_WINDOW = 172800;
    uint256 public challengeWindow;

    // Replay Protection: (proposalId => version => isExecuted)
    mapping(bytes32 => mapping(uint256 => bool)) public executed;

    // Governance Authorization: (proposalId => version => isAuthorized)
    mapping(bytes32 => mapping(uint256 => bool)) public authorizedProposals;
    mapping(bytes32 => mapping(uint256 => address)) public authorizedTargets;
    mapping(bytes32 => mapping(uint256 => uint256)) public authorizedValues;

    // 2-of-3 Guardian Emergency Multisig
    address[3] public guardians;
    mapping(address => bool) public isGuardian;

    bool public isPaused;
    bytes32 public pauseReasonHash;

    // Guardian approvals for pause: (reasonHash => guardian => hasApproved)
    mapping(bytes32 => mapping(address => bool)) public pauseApprovals;
    mapping(bytes32 => uint256) public pauseApprovalCounts;

    // Guardian approvals for unpause: (guardian => hasApproved)
    mapping(address => bool) public unpauseApprovals;
    uint256 public unpauseApprovalCount;

    // Events
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event ChallengeWindowUpdated(uint256 previousWindow, uint256 newWindow);

    event ProposalAuthorized(
        bytes32 indexed proposalId,
        uint256 indexed version,
        address indexed target,
        uint256 value
    );

    event ProposalExecuted(
        bytes32 indexed proposalId,
        uint256 indexed version,
        address indexed target,
        uint256 value,
        bytes data,
        bytes returnData
    );

    event ExecutionRejected(
        bytes32 indexed proposalId,
        uint256 indexed version,
        string reason
    );

    event PauseApprovalRecorded(bytes32 indexed reasonHash, address indexed guardian, uint256 currentApprovals);
    event EmergencyPaused(bytes32 indexed reasonHash, address indexed triggeringGuardian, uint256 totalApprovals);
    event UnpauseApprovalRecorded(address indexed guardian, uint256 currentApprovals);
    event EmergencyUnpaused(address indexed triggeringCaller);

    // Custom Errors
    error UnauthorizedCaller(address caller);
    error InvalidZeroAddress();
    error DuplicateGuardians();
    error TreasuryPaused(bytes32 reasonHash);
    error ProposalAlreadyExecuted(bytes32 proposalId, uint256 version);
    error ProposalNotAuthorized(bytes32 proposalId, uint256 version);
    error TargetMismatch(address expectedTarget, address actualTarget);
    error ValueMismatch(uint256 expectedValue, uint256 actualValue);
    error CalldataHashMismatch(bytes32 expectedCalldataHash, bytes32 actualCalldataHash);
    error RegistryOracleCommitmentMismatch(bytes32 proposalId, uint256 version);
    error IneligibleVerdict(string reason);
    error ChallengeWindowActive(uint256 executableAt, uint256 currentTimestamp);
    error ActiveChallengePending();
    error ProposalDisqualified();
    error ExecutionCallFailed(bytes revertData);
    error GuardianAlreadyApproved();
    error TreasuryNotPaused();
    error TreasuryAlreadyPaused();
    error EmptyHash();

    modifier onlyOwner() {
        if (msg.sender != owner) revert UnauthorizedCaller(msg.sender);
        _;
    }

    modifier onlyGuardian() {
        if (!isGuardian[msg.sender]) revert UnauthorizedCaller(msg.sender);
        _;
    }

    modifier whenNotPaused() {
        if (isPaused) revert TreasuryPaused(pauseReasonHash);
        _;
    }

    /**
     * @param _proposalRegistry ProposalRegistry address.
     * @param _verdictOracle VerdictOracle address.
     * @param _guardians Three distinct guardian addresses for 2-of-3 emergency pause.
     * @param _challengeWindow Challenge window duration in seconds (0 defaults to 172,800s).
     */
    constructor(
        address _proposalRegistry,
        address _verdictOracle,
        address[3] memory _guardians,
        uint256 _challengeWindow
    ) {
        if (_proposalRegistry == address(0) || _verdictOracle == address(0)) {
            revert InvalidZeroAddress();
        }

        // Verify 3 distinct valid guardian addresses
        for (uint256 i = 0; i < 3; i++) {
            address g = _guardians[i];
            if (g == address(0)) revert InvalidZeroAddress();
            for (uint256 j = 0; j < i; j++) {
                if (g == _guardians[j]) revert DuplicateGuardians();
            }
            guardians[i] = g;
            isGuardian[g] = true;
        }

        owner = msg.sender;
        proposalRegistry = ProposalRegistry(_proposalRegistry);
        verdictOracle = VerdictOracle(_verdictOracle);
        challengeWindow = _challengeWindow == 0 ? DEFAULT_CHALLENGE_WINDOW : _challengeWindow;

        emit OwnershipTransferred(address(0), msg.sender);
        emit ChallengeWindowUpdated(0, challengeWindow);
    }

    receive() external payable {}

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setChallengeWindow(uint256 newWindow) external onlyOwner {
        emit ChallengeWindowUpdated(challengeWindow, newWindow);
        challengeWindow = newWindow;
    }

    /**
     * @notice Authorizes a proposal version for execution following successful governance voting.
     */
    function authorizeProposal(
        bytes32 proposalId,
        uint256 version,
        address target,
        uint256 value
    ) external onlyOwner {
        if (target == address(0)) revert InvalidZeroAddress();

        authorizedProposals[proposalId][version] = true;
        authorizedTargets[proposalId][version] = target;
        authorizedValues[proposalId][version] = value;

        emit ProposalAuthorized(proposalId, version, target, value);
    }

    /**
     * @notice Executes a guarded proposal that satisfies all validation, oracle, and challenge constraints.
     * @dev Uses standard EVM CALL; delegatecall is strictly excluded.
     */
    function executeProposal(
        bytes32 proposalId,
        uint256 version,
        address target,
        uint256 value,
        bytes calldata data
    ) external payable whenNotPaused returns (bytes memory returnData) {
        _validateAuthorizationAndCommitments(proposalId, version, target, value, data);
        _validateOracleAndWindow(proposalId, version);

        // Mark executed prior to external call (Checks-Effects-Interactions)
        executed[proposalId][version] = true;

        // Standard EVM Call (Unrestricted delegatecall permanently removed)
        bool success;
        (success, returnData) = target.call{value: value}(data);

        if (!success) {
            if (returnData.length > 0) {
                assembly {
                    let returndata_size := mload(returnData)
                    revert(add(32, returnData), returndata_size)
                }
            } else {
                revert ExecutionCallFailed(returnData);
            }
        }

        emit ProposalExecuted(proposalId, version, target, value, data, returnData);
    }

    function _validateAuthorizationAndCommitments(
        bytes32 proposalId,
        uint256 version,
        address target,
        uint256 value,
        bytes calldata data
    ) internal view {
        if (executed[proposalId][version]) {
            revert ProposalAlreadyExecuted(proposalId, version);
        }
        if (!authorizedProposals[proposalId][version]) {
            revert ProposalNotAuthorized(proposalId, version);
        }
        if (target != authorizedTargets[proposalId][version]) {
            revert TargetMismatch(authorizedTargets[proposalId][version], target);
        }
        if (value != authorizedValues[proposalId][version]) {
            revert ValueMismatch(authorizedValues[proposalId][version], value);
        }

        ProposalRegistry.ProposalVersion memory pv = proposalRegistry.getProposalVersion(proposalId, version);
        bytes32 actualCalldataHash = keccak256(data);
        if (actualCalldataHash != pv.calldataHash) {
            revert CalldataHashMismatch(pv.calldataHash, actualCalldataHash);
        }

        VerdictOracle.AutomatedVerdict memory verdict = verdictOracle.getVerdict(proposalId, version);
        if (verdict.textHash != pv.textHash || verdict.calldataHash != pv.calldataHash) {
            revert RegistryOracleCommitmentMismatch(proposalId, version);
        }
    }

    function _validateOracleAndWindow(
        bytes32 proposalId,
        uint256 version
    ) internal view {
        if (verdictOracle.hasActiveChallenge(proposalId, version)) {
            revert ActiveChallengePending();
        }
        if (verdictOracle.isDisqualified(proposalId, version)) {
            revert ProposalDisqualified();
        }

        (bool eligible, string memory reason) = verdictOracle.isEligibleForExecution(proposalId, version);
        if (!eligible) {
            revert IneligibleVerdict(reason);
        }

        VerdictOracle.AutomatedVerdict memory verdict = verdictOracle.getVerdict(proposalId, version);
        uint256 baseTimestamp = verdict.timestamp;
        VerdictOracle.HumanReview memory review = verdictOracle.getLatestReview(proposalId, version);
        if (verdict.status == VerdictOracle.AutomatedVerdictStatus.NEEDS_REVIEW && review.timestamp > baseTimestamp) {
            baseTimestamp = review.timestamp;
        }

        uint256 executableAt = baseTimestamp + challengeWindow;
        if (block.timestamp < executableAt) {
            revert ChallengeWindowActive(executableAt, block.timestamp);
        }
    }

    // =========================================================================
    // 2-OF-3 GUARDIAN EMERGENCY MULTISIG
    // =========================================================================

    /**
     * @notice Proposes or votes to trigger an emergency pause for a specified reason.
     * @dev Requires 2 distinct guardian approvals before the Treasury enters paused state.
     */
    function proposeEmergencyPause(bytes32 reasonHash) external onlyGuardian {
        if (isPaused) revert TreasuryAlreadyPaused();
        if (reasonHash == bytes32(0)) revert EmptyHash();
        if (pauseApprovals[reasonHash][msg.sender]) revert GuardianAlreadyApproved();

        pauseApprovals[reasonHash][msg.sender] = true;
        pauseApprovalCounts[reasonHash] += 1;

        emit PauseApprovalRecorded(reasonHash, msg.sender, pauseApprovalCounts[reasonHash]);

        // 2-of-3 threshold reached
        if (pauseApprovalCounts[reasonHash] >= 2) {
            isPaused = true;
            pauseReasonHash = reasonHash;
            emit EmergencyPaused(reasonHash, msg.sender, pauseApprovalCounts[reasonHash]);
        }
    }

    /**
     * @notice Proposes or votes to unpause the Treasury.
     * @dev Unpauses upon receiving 2 guardian approvals or immediate owner intervention.
     */
    function proposeUnpause() external {
        if (!isPaused) revert TreasuryNotPaused();
        if (!isGuardian[msg.sender] && msg.sender != owner) revert UnauthorizedCaller(msg.sender);

        if (msg.sender == owner) {
            _executeUnpause();
            return;
        }

        if (unpauseApprovals[msg.sender]) revert GuardianAlreadyApproved();

        unpauseApprovals[msg.sender] = true;
        unpauseApprovalCount += 1;

        emit UnpauseApprovalRecorded(msg.sender, unpauseApprovalCount);

        if (unpauseApprovalCount >= 2) {
            _executeUnpause();
        }
    }

    function _executeUnpause() internal {
        bytes32 prevReason = pauseReasonHash;
        isPaused = false;
        pauseReasonHash = bytes32(0);
        unpauseApprovalCount = 0;

        for (uint256 i = 0; i < 3; i++) {
            unpauseApprovals[guardians[i]] = false;
            if (prevReason != bytes32(0)) {
                pauseApprovals[prevReason][guardians[i]] = false;
            }
        }
        if (prevReason != bytes32(0)) {
            pauseApprovalCounts[prevReason] = 0;
        }

        emit EmergencyUnpaused(msg.sender);
    }
}
