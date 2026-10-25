// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title ProposalRegistry
 * @notice Versioned registry for governance proposal metadata, text hashes, and calldata commitments.
 *
 * Immutability & Versioning:
 * - Submissions are indexed by proposalId and sequential 1-based version numbers.
 * - Once submitted, a version's fields (textHash, calldataHash, disclosedWallets) are immutable.
 * - Updates append a new version with incremented version ID; historical versions remain queryable.
 */
contract ProposalRegistry {
    struct ProposalVersion {
        uint256 version;
        bytes32 textHash;
        bytes32 calldataHash;
        address[] disclosedWallets;
        uint256 timestamp;
        address author;
    }

    // proposalId => latest version counter (0 means unsubmitted)
    mapping(bytes32 => uint256) public latestVersion;

    // proposalId => version => ProposalVersion
    mapping(bytes32 => mapping(uint256 => ProposalVersion)) private _proposalVersions;

    // proposalId => original author
    mapping(bytes32 => address) public proposalAuthor;

    // Events
    event ProposalSubmitted(
        bytes32 indexed proposalId,
        uint256 indexed version,
        bytes32 textHash,
        bytes32 calldataHash,
        address indexed author,
        uint256 timestamp
    );

    event ProposalUpdated(
        bytes32 indexed proposalId,
        uint256 indexed version,
        bytes32 textHash,
        bytes32 calldataHash,
        address indexed author,
        uint256 timestamp
    );

    // Custom Errors
    error EmptyProposalId();
    error EmptyTextHash();
    error EmptyCalldataHash();
    error ProposalAlreadyExists(bytes32 proposalId);
    error ProposalDoesNotExist(bytes32 proposalId);
    error UnauthorizedAuthor(bytes32 proposalId, address caller, address expectedAuthor);
    error DuplicateVersionContent(bytes32 proposalId, uint256 currentVersion);
    error VersionNotFound(bytes32 proposalId, uint256 requestedVersion);

    /**
     * @notice Submits a new proposal with initial version 1.
     * @param proposalId Unique identifier for the proposal.
     * @param textHash Cryptographic hash (keccak256) of proposal text/specification.
     * @param calldataHash Cryptographic hash (keccak256) of target transaction calldata.
     * @param disclosedWallets Array of disclosed addresses (authors, benefactors, etc.).
     * @return newVersion The created version index (always 1 for new proposals).
     */
    function submitProposal(
        bytes32 proposalId,
        bytes32 textHash,
        bytes32 calldataHash,
        address[] calldata disclosedWallets
    ) external returns (uint256 newVersion) {
        if (proposalId == bytes32(0)) revert EmptyProposalId();
        if (textHash == bytes32(0)) revert EmptyTextHash();
        if (calldataHash == bytes32(0)) revert EmptyCalldataHash();
        if (latestVersion[proposalId] != 0) revert ProposalAlreadyExists(proposalId);

        newVersion = 1;
        latestVersion[proposalId] = newVersion;
        proposalAuthor[proposalId] = msg.sender;

        _proposalVersions[proposalId][newVersion] = ProposalVersion({
            version: newVersion,
            textHash: textHash,
            calldataHash: calldataHash,
            disclosedWallets: disclosedWallets,
            timestamp: block.timestamp,
            author: msg.sender
        });

        emit ProposalSubmitted(proposalId, newVersion, textHash, calldataHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Submits an updated version for an existing proposal.
     * @param proposalId Unique identifier for the existing proposal.
     * @param textHash New cryptographic hash of proposal text.
     * @param calldataHash New cryptographic hash of target transaction calldata.
     * @param disclosedWallets Updated array of disclosed addresses.
     * @return newVersion The newly incremented version index.
     */
    function updateProposal(
        bytes32 proposalId,
        bytes32 textHash,
        bytes32 calldataHash,
        address[] calldata disclosedWallets
    ) external returns (uint256 newVersion) {
        uint256 currentVer = latestVersion[proposalId];
        if (currentVer == 0) revert ProposalDoesNotExist(proposalId);
        if (msg.sender != proposalAuthor[proposalId]) {
            revert UnauthorizedAuthor(proposalId, msg.sender, proposalAuthor[proposalId]);
        }
        if (textHash == bytes32(0)) revert EmptyTextHash();
        if (calldataHash == bytes32(0)) revert EmptyCalldataHash();

        ProposalVersion storage prev = _proposalVersions[proposalId][currentVer];
        if (prev.textHash == textHash && prev.calldataHash == calldataHash) {
            revert DuplicateVersionContent(proposalId, currentVer);
        }

        newVersion = currentVer + 1;
        latestVersion[proposalId] = newVersion;

        _proposalVersions[proposalId][newVersion] = ProposalVersion({
            version: newVersion,
            textHash: textHash,
            calldataHash: calldataHash,
            disclosedWallets: disclosedWallets,
            timestamp: block.timestamp,
            author: msg.sender
        });

        emit ProposalUpdated(proposalId, newVersion, textHash, calldataHash, msg.sender, block.timestamp);
    }

    /**
     * @notice Retrieves specific version details for a proposal.
     */
    function getProposalVersion(
        bytes32 proposalId,
        uint256 version
    ) external view returns (ProposalVersion memory) {
        if (version == 0 || version > latestVersion[proposalId]) {
            revert VersionNotFound(proposalId, version);
        }
        return _proposalVersions[proposalId][version];
    }

    /**
     * @notice Verifies if supplied hashes match the latest version of a proposal.
     * @param proposalId Unique proposal identifier.
     * @param expectedTextHash Expected text hash commitment.
     * @param expectedCalldataHash Expected calldata hash commitment.
     * @return isValid True if proposal exists and both hashes match latest version.
     * @return currentVersion The latest version number (or 0 if proposal does not exist).
     */
    function verifyLatestHashes(
        bytes32 proposalId,
        bytes32 expectedTextHash,
        bytes32 expectedCalldataHash
    ) external view returns (bool isValid, uint256 currentVersion) {
        currentVersion = latestVersion[proposalId];
        if (currentVersion == 0) return (false, 0);

        ProposalVersion storage v = _proposalVersions[proposalId][currentVersion];
        isValid = (v.textHash == expectedTextHash && v.calldataHash == expectedCalldataHash);
    }
}
