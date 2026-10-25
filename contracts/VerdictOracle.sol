// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title VerdictOracle
 * @notice Stores automated simulation verdicts, human reviews, and challenge states for governance proposals.
 *
 * Verdict & Review Pipeline:
 * 1. Automated Analyzer posts verdict: VERIFIED, MISMATCH, or NEEDS_REVIEW.
 * 2. Authorized human reviewers can review proposals (APPROVE, REJECT, ESCALATE).
 * 3. Human reviews append to review history without mutating or overwriting original automated records.
 * 4. Challenges can be raised during the challenge window. Unresolved or successful challenges block execution.
 */
contract VerdictOracle {
    enum AutomatedVerdictStatus {
        NONE,
        VERIFIED,
        MISMATCH,
        NEEDS_REVIEW
    }

    enum FinalizationState {
        UNFINALIZED,
        FINALIZED
    }

    enum ReviewDecision {
        NONE,
        APPROVE,
        REJECT,
        ESCALATE
    }

    struct AutomatedVerdict {
        AutomatedVerdictStatus status;
        bytes32 textHash;
        bytes32 calldataHash;
        bytes32 evidenceHash;
        uint256 timestamp;
        FinalizationState finalizationState;
    }

    struct HumanReview {
        address reviewer;
        ReviewDecision decision;
        bytes32 reasonHash;
        uint256 timestamp;
    }

    struct Challenge {
        address challenger;
        bytes32 reasonHash;
        uint256 timestamp;
        bool resolved;
        bool successful;
    }

    // Governance Roles
    address public owner;
    address public analyzer;

    // Reviewer allowlist: reviewer address => isAuthorized
    mapping(address => bool) public authorizedReviewers;

    // (proposalId => version => AutomatedVerdict)
    mapping(bytes32 => mapping(uint256 => AutomatedVerdict)) public automatedVerdicts;

    // (proposalId => version => HumanReview[]) complete immutable review log
    mapping(bytes32 => mapping(uint256 => HumanReview[])) private _reviewHistory;

    // (proposalId => version => latest HumanReview)
    mapping(bytes32 => mapping(uint256 => HumanReview)) public latestReviews;

    // Challenge tracking
    mapping(bytes32 => mapping(uint256 => Challenge[])) private _challenges;
    mapping(bytes32 => mapping(uint256 => bool)) public hasActiveChallenge;
    mapping(bytes32 => mapping(uint256 => bool)) public isDisqualified;

    // Events
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event AnalyzerUpdated(address indexed previousAnalyzer, address indexed newAnalyzer);
    event ReviewerAuthorizationSet(address indexed reviewer, bool authorized);

    event VerdictPosted(
        bytes32 indexed proposalId,
        uint256 indexed version,
        AutomatedVerdictStatus status,
        bytes32 textHash,
        bytes32 calldataHash,
        bytes32 evidenceHash,
        uint256 timestamp,
        FinalizationState finalizationState
    );

    event ReviewPosted(
        bytes32 indexed proposalId,
        uint256 indexed version,
        address indexed reviewer,
        ReviewDecision decision,
        bytes32 reasonHash,
        uint256 timestamp
    );

    event ChallengeRaised(
        bytes32 indexed proposalId,
        uint256 indexed version,
        address indexed challenger,
        bytes32 reasonHash,
        uint256 challengeIndex
    );

    event ChallengeResolved(
        bytes32 indexed proposalId,
        uint256 indexed version,
        uint256 challengeIndex,
        bool successful
    );

    // Custom Errors
    error UnauthorizedCaller(address caller);
    error UnauthorizedAnalyzer(address caller);
    error UnauthorizedReviewer(address caller);
    error InvalidZeroAddress();
    error EmptyProposalId();
    error InvalidVersion();
    error InvalidVerdictStatus();
    error EmptyHash();
    error VerdictAlreadyFinalized(bytes32 proposalId, uint256 version);
    error NoVerdictFound(bytes32 proposalId, uint256 version);
    error InvalidReviewDecision();
    error ReviewNotPermittedOnMismatch(bytes32 proposalId, uint256 version);
    error ChallengeAlreadyActive(bytes32 proposalId, uint256 version);
    error ChallengeNotFound(bytes32 proposalId, uint256 version, uint256 index);
    error ChallengeAlreadyResolved(bytes32 proposalId, uint256 version, uint256 index);

    modifier onlyOwner() {
        if (msg.sender != owner) revert UnauthorizedCaller(msg.sender);
        _;
    }

    modifier onlyAnalyzer() {
        if (msg.sender != analyzer) revert UnauthorizedAnalyzer(msg.sender);
        _;
    }

    constructor(address _analyzer) {
        if (_analyzer == address(0)) revert InvalidZeroAddress();
        owner = msg.sender;
        analyzer = _analyzer;
        emit OwnershipTransferred(address(0), msg.sender);
        emit AnalyzerUpdated(address(0), _analyzer);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert InvalidZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function setAnalyzer(address newAnalyzer) external onlyOwner {
        if (newAnalyzer == address(0)) revert InvalidZeroAddress();
        emit AnalyzerUpdated(analyzer, newAnalyzer);
        analyzer = newAnalyzer;
    }

    function setReviewer(address reviewer, bool authorized) external onlyOwner {
        if (reviewer == address(0)) revert InvalidZeroAddress();
        authorizedReviewers[reviewer] = authorized;
        emit ReviewerAuthorizationSet(reviewer, authorized);
    }

    /**
     * @notice Posts an automated verification verdict from the simulation engine.
     */
    function postVerdict(
        bytes32 proposalId,
        uint256 version,
        AutomatedVerdictStatus status,
        bytes32 textHash,
        bytes32 calldataHash,
        bytes32 evidenceHash,
        bool finalize
    ) external onlyAnalyzer {
        if (proposalId == bytes32(0)) revert EmptyProposalId();
        if (version == 0) revert InvalidVersion();
        if (status == AutomatedVerdictStatus.NONE) revert InvalidVerdictStatus();
        if (textHash == bytes32(0) || calldataHash == bytes32(0) || evidenceHash == bytes32(0)) {
            revert EmptyHash();
        }

        AutomatedVerdict storage current = automatedVerdicts[proposalId][version];
        if (current.finalizationState == FinalizationState.FINALIZED) {
            revert VerdictAlreadyFinalized(proposalId, version);
        }

        FinalizationState fin = finalize ? FinalizationState.FINALIZED : FinalizationState.UNFINALIZED;

        automatedVerdicts[proposalId][version] = AutomatedVerdict({
            status: status,
            textHash: textHash,
            calldataHash: calldataHash,
            evidenceHash: evidenceHash,
            timestamp: block.timestamp,
            finalizationState: fin
        });

        emit VerdictPosted(proposalId, version, status, textHash, calldataHash, evidenceHash, block.timestamp, fin);
    }

    /**
     * @notice Submits an authorized human review decision.
     * @dev Reviewer must call directly from their authorized address.
     * Appends to review history; prior automated verdict records are never overwritten.
     */
    function postReview(
        bytes32 proposalId,
        uint256 version,
        ReviewDecision decision,
        bytes32 reasonHash
    ) external {
        if (!authorizedReviewers[msg.sender]) revert UnauthorizedReviewer(msg.sender);
        if (decision == ReviewDecision.NONE) revert InvalidReviewDecision();
        if (reasonHash == bytes32(0)) revert EmptyHash();

        AutomatedVerdict storage verdict = automatedVerdicts[proposalId][version];
        if (verdict.status == AutomatedVerdictStatus.NONE) revert NoVerdictFound(proposalId, version);

        // MISMATCH cannot be overturned by standard review (requires proposal re-submission)
        if (verdict.status == AutomatedVerdictStatus.MISMATCH) {
            revert ReviewNotPermittedOnMismatch(proposalId, version);
        }

        HumanReview memory review = HumanReview({
            reviewer: msg.sender,
            decision: decision,
            reasonHash: reasonHash,
            timestamp: block.timestamp
        });

        _reviewHistory[proposalId][version].push(review);
        latestReviews[proposalId][version] = review;

        emit ReviewPosted(proposalId, version, msg.sender, decision, reasonHash, block.timestamp);
    }

    /**
     * @notice Raises a formal challenge against a proposal version.
     */
    function raiseChallenge(
        bytes32 proposalId,
        uint256 version,
        bytes32 reasonHash
    ) external returns (uint256 challengeIndex) {
        if (reasonHash == bytes32(0)) revert EmptyHash();
        if (automatedVerdicts[proposalId][version].status == AutomatedVerdictStatus.NONE) {
            revert NoVerdictFound(proposalId, version);
        }
        if (hasActiveChallenge[proposalId][version]) {
            revert ChallengeAlreadyActive(proposalId, version);
        }

        hasActiveChallenge[proposalId][version] = true;
        challengeIndex = _challenges[proposalId][version].length;

        _challenges[proposalId][version].push(Challenge({
            challenger: msg.sender,
            reasonHash: reasonHash,
            timestamp: block.timestamp,
            resolved: false,
            successful: false
        }));

        emit ChallengeRaised(proposalId, version, msg.sender, reasonHash, challengeIndex);
    }

    /**
     * @notice Resolves an active challenge.
     */
    function resolveChallenge(
        bytes32 proposalId,
        uint256 version,
        uint256 challengeIndex,
        bool successful
    ) external onlyOwner {
        if (challengeIndex >= _challenges[proposalId][version].length) {
            revert ChallengeNotFound(proposalId, version, challengeIndex);
        }

        Challenge storage c = _challenges[proposalId][version][challengeIndex];
        if (c.resolved) revert ChallengeAlreadyResolved(proposalId, version, challengeIndex);

        c.resolved = true;
        c.successful = successful;
        hasActiveChallenge[proposalId][version] = false;

        if (successful) {
            isDisqualified[proposalId][version] = true;
        }

        emit ChallengeResolved(proposalId, version, challengeIndex, successful);
    }

    function getVerdict(
        bytes32 proposalId,
        uint256 version
    ) external view returns (AutomatedVerdict memory) {
        return automatedVerdicts[proposalId][version];
    }

    function getLatestReview(
        bytes32 proposalId,
        uint256 version
    ) external view returns (HumanReview memory) {
        return latestReviews[proposalId][version];
    }

    function getReviewHistory(
        bytes32 proposalId,
        uint256 version
    ) external view returns (HumanReview[] memory) {
        return _reviewHistory[proposalId][version];
    }

    function getChallenges(
        bytes32 proposalId,
        uint256 version
    ) external view returns (Challenge[] memory) {
        return _challenges[proposalId][version];
    }

    /**
     * @notice Evaluates if a proposal version's verdict is currently eligible for execution.
     * @return eligible True if state is VERIFIED or explicitly APPROVED by human review, with no active/successful challenges.
     * @return reason Human-readable explanation of status.
     */
    function isEligibleForExecution(
        bytes32 proposalId,
        uint256 version
    ) public view returns (bool eligible, string memory reason) {
        if (isDisqualified[proposalId][version]) {
            return (false, "Proposal disqualified by successful challenge");
        }
        if (hasActiveChallenge[proposalId][version]) {
            return (false, "Proposal has an unresolved active challenge");
        }

        AutomatedVerdict storage verdict = automatedVerdicts[proposalId][version];
        if (verdict.status == AutomatedVerdictStatus.NONE) {
            return (false, "No verdict recorded for proposal version");
        }
        if (verdict.status == AutomatedVerdictStatus.MISMATCH) {
            return (false, "Automated verdict is MISMATCH; execution permanently blocked");
        }

        HumanReview storage review = latestReviews[proposalId][version];

        if (verdict.status == AutomatedVerdictStatus.NEEDS_REVIEW) {
            if (review.decision == ReviewDecision.APPROVE) {
                return (true, "NEEDS_REVIEW approved by authorized human reviewer");
            } else if (review.decision == ReviewDecision.REJECT) {
                return (false, "NEEDS_REVIEW rejected by human review");
            } else if (review.decision == ReviewDecision.ESCALATE) {
                return (false, "NEEDS_REVIEW escalated without final approval");
            } else {
                return (false, "NEEDS_REVIEW awaiting authorized human review");
            }
        }

        if (verdict.status == AutomatedVerdictStatus.VERIFIED) {
            if (review.decision == ReviewDecision.REJECT) {
                return (false, "VERIFIED proposal explicitly rejected by human review override");
            }
            if (review.decision == ReviewDecision.ESCALATE) {
                return (false, "VERIFIED proposal escalated by human review override");
            }
            return (true, "Automated verdict is VERIFIED");
        }

        return (false, "Ineligible verdict state");
    }
}
