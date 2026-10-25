/**
 * demoData.js
 * ===========
 * Strictly separated demo dataset adapter for Veritas Gate Phase 6 Dashboard.
 * 
 * NOTICE:
 * This data is clearly labelled DEMO DATA. It is DISABLED by default.
 * It is only used when the user explicitly toggles on Demo Mode.
 * All records correspond to educational harnesses and test fixtures from Phase 1 & 3.
 */

export const DEMO_DATA_TAG = 'DEMO DATA (SYNTHETIC)';
export const DEMO_DATA_NOTICE = 'DEMO DATA: Synthetic test fixtures for UI demonstration. NOT real on-chain evidence.';

export const DEMO_METRICS = {
  totalProposals: 6,
  verifiedCount: 1,
  mismatchCount: 2,
  needsReviewCount: 3,
  pendingReviews: 2,
  activeChallenges: 1,
  guardianPauses: 1,
  treasury: {
    tokenSymbol: 'MOCK',
    tokenDecimals: 18,
    totalBalance: '10000000000000000000000000', // 10M tokens
    requestedTotal: '15000000000000000000000000',
    nativeBalanceWei: '450000000000000000000', // 450 ETH
  },
  latestAuditEvents: [
    {
      id: 'evt-001',
      timestamp: '2026-10-25T16:15:00Z',
      type: 'SIMULATION_COMPLETED',
      proposalId: 'prop-002',
      verdict: 'MISMATCH',
      summary: 'Slot 0 collision detected: Treasury ownership hijacked under delegatecall',
      actor: 'VeritasEngine-v1.0'
    },
    {
      id: 'evt-002',
      timestamp: '2026-10-25T15:45:00Z',
      type: 'GUARDIAN_PAUSE_TRIGGERED',
      proposalId: 'prop-002',
      verdict: 'MISMATCH',
      summary: 'Guardian emergency pause activated due to Slot 0 hijack detection',
      actor: 'GuardianMultisig'
    },
    {
      id: 'evt-003',
      timestamp: '2026-10-25T14:30:00Z',
      type: 'SIMULATION_COMPLETED',
      proposalId: 'prop-001',
      verdict: 'VERIFIED',
      summary: 'Honest 5,000,000 MOCK grant verified cleanly against complete trace',
      actor: 'VeritasEngine-v1.0'
    },
    {
      id: 'evt-004',
      timestamp: '2026-10-25T13:20:00Z',
      type: 'CHALLENGE_FILED',
      proposalId: 'prop-005',
      verdict: 'MISMATCH',
      summary: 'Challenger staked 50,000 MOCK against unclaimed 1M token transfer',
      actor: '0x7777777777777777777777777777777777777777'
    }
  ]
};

export const DEMO_PROPOSALS = [
  {
    id: 'prop-001',
    version: 'v1.0',
    title: 'DAO Grant: 5,000,000 Token Ecosystem Distribution',
    description: 'Distributes an honest 5,000,000 MockToken grant to recipient 0x3333333333333333333333333333333333333333 for core development tooling. Preserves Treasury state variables intact.',
    proposer: '0x2222222222222222222222222222222222222222',
    targetTreasury: '0x1111111111111111111111111111111111111111',
    status: 'PASSED',
    submittedAt: '2026-10-25T12:00:00Z',
    versionHash: '0x4f8a92bc6d71e3a47890f5b128c704e8aa19ef47d2f9b168e309bb99105f2411',
    
    verdict: {
      status: 'VERIFIED',
      reasonCode: 'VERIFIED_ALL_CLAIMS_MATCH',
      explanation: 'All claimed proposal effects verified cleanly against complete simulation trace. Zero storage writes and zero unclaimed transfers observed.',
      traceComplete: true,
      simulationMode: 'local_evm',
      evidenceReferences: [
        {
          source: 'log',
          identifier: 'log[0]',
          details: {
            token: '0x4444444444444444444444444444444444444444',
            from: '0x1111111111111111111111111111111111111111',
            to: '0x3333333333333333333333333333333333333333',
            amount: '5000000000000000000000000'
          }
        }
      ],
      findings: []
    },

    claims: [
      {
        claim_id: 'claim-001-grant-distribution',
        type: 'TOKEN_TRANSFER',
        token: '0x4444444444444444444444444444444444444444',
        recipient: '0x3333333333333333333333333333333333333333',
        amount: '5000000000000000000000000',
        unit: 'raw_tokens',
        sender: '0x1111111111111111111111111111111111111111',
        description: '5,000,000 mock tokens transferred from Treasury to grant recipient'
      },
      {
        claim_id: 'claim-002-ownership-preserved',
        type: 'OWNERSHIP_EXPECTATION',
        contract: '0x1111111111111111111111111111111111111111',
        expected_state: 'UNCHANGED',
        unit: 'address',
        description: 'Treasury owner address must remain unchanged'
      },
      {
        claim_id: 'claim-003-forbid-ownership-hijack',
        type: 'FORBIDDEN_EFFECT',
        effect_type: 'OWNERSHIP_CHANGE',
        target: '0x1111111111111111111111111111111111111111',
        unit: 'none',
        description: 'Slot 0 ownership modification on Treasury is explicitly forbidden'
      }
    ],

    observedEffects: {
      transfers: [
        {
          token: '0x4444444444444444444444444444444444444444',
          from: '0x1111111111111111111111111111111111111111',
          to: '0x3333333333333333333333333333333333333333',
          amount: '5000000000000000000000000',
          logIndex: 0,
          matchedClaimId: 'claim-001-grant-distribution'
        }
      ],
      nativeTransfers: [],
      stateDiffs: [],
      ownership: {
        contract: '0x1111111111111111111111111111111111111111',
        before: '0x0000000000000000000000002222222222222222222222222222222222222222',
        after: '0x0000000000000000000000002222222222222222222222222222222222222222',
        hasMutated: false
      }
    },

    evalChain: {
      claimConfidence: {
        status: 'HIGH CONFIDENCE',
        level: 'good',
        evidence: 'EVM execution trace captures exact 5M MOCK transfer; no unstated side-effects recorded.',
        limitations: 'Simulation validated in local harness. Block reorgs or state drift at execution time remain potential risks.'
      },
      coiRisk: {
        status: 'LOW RISK',
        level: 'good',
        evidence: 'Beneficiary 0x3333...3333 has no common multi-sig signers with proposer 0x2222...2222 in recorded history.',
        limitations: 'Off-chain legal relationships or unindexed secondary wallets cannot be ruled out by ledger data.'
      },
      votingStatus: {
        status: 'READY FOR VOTE',
        level: 'good',
        evidence: 'Proposal passed deterministic verdict engine with VERIFIED status. Zero unverified findings.',
        limitations: 'Token holder turnout threshold and quorum required for ratification.'
      },
      executionDiscrepancy: {
        status: 'ZERO DISCREPANCY',
        level: 'good',
        evidence: 'Observed effects 100% aligned with promises. Zero slot mutations.',
        limitations: 'Contract assumes MockToken ERC-20 interface standard.'
      }
    },

    coiData: {
      proposer: '0x2222222222222222222222222222222222222222',
      beneficiary: '0x3333333333333333333333333333333333333333',
      provenance: 'Genesis DAO deployer list block #1',
      relationshipDepth: 'Unconnected (Distance > 3 hops)',
      uncertainty: 'LOW',
      connections: []
    }
  },

  {
    id: 'prop-002',
    version: 'v1.0',
    title: 'Treasury Optimization & Reward Dispatcher Module',
    description: 'Purports to distribute a 5M token grant while optimizing gas routes via delegatecall. In reality, overwrites Treasury Slot 0 to hijack contract ownership to attacker address 0x9999999999999999999999999999999999999999.',
    proposer: '0x8888888888888888888888888888888888888888',
    targetTreasury: '0x1111111111111111111111111111111111111111',
    status: 'CHALLENGED',
    submittedAt: '2026-10-25T14:00:00Z',
    versionHash: '0x99b12c3f0a519808d447a28e932b17042c4bca646960d7f99ee356411d51a23e',

    verdict: {
      status: 'MISMATCH',
      reasonCode: 'MISMATCH_OWNERSHIP_COLLISION',
      explanation: 'Treasury contract Slot 0 (owner) was mutated from 0x2222...2222 to attacker address 0x9999...9999, violating UNCHANGED ownership expectation and forbidden ownership change claim.',
      traceComplete: true,
      simulationMode: 'local_evm',
      evidenceReferences: [
        {
          source: 'state_diff',
          identifier: '0x1111111111111111111111111111111111111111:slot_0',
          details: {
            slot: '0x0000000000000000000000000000000000000000000000000000000000000000',
            slot_name: 'owner',
            before: '0x0000000000000000000000002222222222222222222222222222222222222222',
            after: '0x0000000000000000000000009999999999999999999999999999999999999999'
          }
        }
      ],
      findings: [
        {
          code: 'DELEGATECALL_DETECTED',
          severity: 'CRITICAL',
          description: 'Proposal invoked DELEGATECALL instruction targeting external unverified payload contract 0x6666...6666.'
        }
      ]
    },

    claims: [
      {
        claim_id: 'claim-grant-transfer',
        type: 'TOKEN_TRANSFER',
        token: '0x4444444444444444444444444444444444444444',
        recipient: '0x3333333333333333333333333333333333333333',
        amount: '5000000000000000000000000',
        unit: 'raw_tokens',
        sender: '0x1111111111111111111111111111111111111111'
      },
      {
        claim_id: 'claim-forbid-ownership-change',
        type: 'FORBIDDEN_EFFECT',
        effect_type: 'OWNERSHIP_CHANGE',
        target: '0x1111111111111111111111111111111111111111',
        unit: 'none'
      }
    ],

    observedEffects: {
      transfers: [
        {
          token: '0x4444444444444444444444444444444444444444',
          from: '0x1111111111111111111111111111111111111111',
          to: '0x3333333333333333333333333333333333333333',
          amount: '5000000000000000000000000',
          logIndex: 0,
          matchedClaimId: 'claim-grant-transfer'
        }
      ],
      nativeTransfers: [],
      stateDiffs: [
        {
          address: '0x1111111111111111111111111111111111111111',
          slot: '0x0000000000000000000000000000000000000000000000000000000000000000',
          slotName: 'owner',
          before: '0x0000000000000000000000002222222222222222222222222222222222222222',
          after: '0x0000000000000000000000009999999999999999999999999999999999999999',
          hasMutated: true
        }
      ],
      ownership: {
        contract: '0x1111111111111111111111111111111111111111',
        before: '0x0000000000000000000000002222222222222222222222222222222222222222',
        after: '0x0000000000000000000000009999999999999999999999999999999999999999',
        hasMutated: true,
        mutatedTo: '0x9999999999999999999999999999999999999999'
      }
    },

    evalChain: {
      claimConfidence: {
        status: 'CRITICAL MISMATCH',
        level: 'danger',
        evidence: 'Slot 0 write detected in EVM state diffs. Overwrites Treasury owner.',
        limitations: 'Diff is definitive for tested execution input.'
      },
      coiRisk: {
        status: 'HIGH RISK',
        level: 'danger',
        evidence: 'Proposer wallet 0x8888...8888 received funding from attacker wallet 0x9999...9999 2 days prior to submission.',
        limitations: 'Fund flow indicates adjacency; does not prove criminal collusion under law.'
      },
      votingStatus: {
        status: 'REJECT / DO NOT VOTE',
        level: 'danger',
        evidence: 'Proposal triggers verified Treasury ownership takeover. Guardian has filed emergency freeze.',
        limitations: 'None; state collision is mathematically provable.'
      },
      executionDiscrepancy: {
        status: 'UNCLAIMED STATE HIJACK',
        level: 'danger',
        evidence: 'Treasury.owner changed to 0x9999...9999 without proposal disclosure.',
        limitations: 'None.'
      }
    },

    coiData: {
      proposer: '0x8888888888888888888888888888888888888888',
      beneficiary: '0x3333333333333333333333333333333333333333',
      provenance: 'TornadoCash interaction + Anvil trace',
      relationshipDepth: '1-Hop Direct Funding (50 ETH from attacker)',
      uncertainty: 'LOW (Direct Tx on-chain)',
      connections: [
        {
          from: '0x9999999999999999999999999999999999999999',
          to: '0x8888888888888888888888888888888888888888',
          txHash: '0x3f5b...9a12',
          amount: '50.0 ETH',
          timestamp: '2026-10-23T10:00:00Z',
          label: 'Pre-Proposal Funding Flow'
        }
      ]
    }
  },

  {
    id: 'prop-003',
    version: 'v1.1',
    title: 'Helper Library Grant via Delegatecall Routing',
    description: 'Distributes 5M MOCK grant using a stateless library executed via delegatecall. Effects match claimed transfers, but execution opcode contains delegatecall risk flag.',
    proposer: '0x5555555555555555555555555555555555555555',
    targetTreasury: '0x1111111111111111111111111111111111111111',
    status: 'ACTIVE',
    submittedAt: '2026-10-25T11:30:00Z',
    versionHash: '0x71a238de45bc0981273948572109348572349085723498572394857239485723',

    verdict: {
      status: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_RISKY_OPERATION_FLAG',
      explanation: 'Simulation trace contains configured risky operation flag(s): DELEGATECALL_DETECTED. No storage collision was proven, but manual reviewer approval is mandatory.',
      traceComplete: true,
      simulationMode: 'local_evm',
      evidenceReferences: [
        {
          source: 'finding',
          identifier: 'DELEGATECALL_DETECTED',
          details: {
            target: '0x5555555555555555555555555555555555555555',
            severity: 'HIGH'
          }
        }
      ],
      findings: [
        {
          code: 'DELEGATECALL_DETECTED',
          severity: 'HIGH',
          description: 'DELEGATECALL instruction executed to external address 0x5555555555555555555555555555555555555555'
        }
      ]
    },

    claims: [
      {
        claim_id: 'claim-transfer-003',
        type: 'TOKEN_TRANSFER',
        token: '0x4444444444444444444444444444444444444444',
        recipient: '0x3333333333333333333333333333333333333333',
        amount: '5000000000000000000000000',
        unit: 'raw_tokens'
      }
    ],

    observedEffects: {
      transfers: [
        {
          token: '0x4444444444444444444444444444444444444444',
          from: '0x1111111111111111111111111111111111111111',
          to: '0x3333333333333333333333333333333333333333',
          amount: '5000000000000000000000000',
          logIndex: 0,
          matchedClaimId: 'claim-transfer-003'
        }
      ],
      nativeTransfers: [],
      stateDiffs: [],
      ownership: {
        contract: '0x1111111111111111111111111111111111111111',
        before: '0x0000000000000000000000002222222222222222222222222222222222222222',
        after: '0x0000000000000000000000002222222222222222222222222222222222222222',
        hasMutated: false
      }
    },

    evalChain: {
      claimConfidence: {
        status: 'UNVERIFIED OPCODES',
        level: 'warning',
        evidence: 'Trace exhibits delegatecall opcode. Target contract claims to be stateless.',
        limitations: 'Static trace verified no slot writes in current run; contract upgradeability risk exists.'
      },
      coiRisk: {
        status: 'MODERATE RISK',
        level: 'warning',
        evidence: 'Proposer is a known ecosystem contributor, but contract source is unverified on Etherscan.',
        limitations: 'Bytecode disassembly required for full validation.'
      },
      votingStatus: {
        status: 'AWAITING REVIEWER',
        level: 'warning',
        evidence: 'Must be approved by 2 designated security reviewers before voting opens.',
        limitations: 'Reviewer approval does not replace formal code audit.'
      },
      executionDiscrepancy: {
        status: 'POTENTIAL HAZARD',
        level: 'warning',
        evidence: 'Transfers match, but delegatecall pattern violates Treasury security best practices.',
        limitations: 'Educational test harness pattern.'
      }
    },

    coiData: {
      proposer: '0x5555555555555555555555555555555555555555',
      beneficiary: '0x3333333333333333333333333333333333333333',
      provenance: 'Gitcoin grant participant block #18200000',
      relationshipDepth: '2-Hops Common Grantee Pool',
      uncertainty: 'MODERATE',
      connections: []
    }
  },

  {
    id: 'prop-004',
    version: 'v1.0',
    title: 'Community Incentive Reward Wave 3',
    description: 'Proposes multi-address reward distribution. Execution tracer memory buffer exhausted, producing an incomplete trace.',
    proposer: '0x4444444444444444444444444444444444444444',
    targetTreasury: '0x1111111111111111111111111111111111111111',
    status: 'ACTIVE',
    submittedAt: '2026-10-25T10:15:00Z',
    versionHash: '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',

    verdict: {
      status: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_TRACE_INCOMPLETE',
      explanation: 'Simulation execution trace is incomplete or was truncated; safety cannot be verified. Fail-closed discipline prohibits VERIFIED verdict.',
      traceComplete: false,
      simulationMode: 'local_evm',
      evidenceReferences: [
        {
          source: 'schema',
          identifier: 'trace_complete',
          details: { trace_complete: false }
        }
      ],
      findings: []
    },

    claims: [
      {
        claim_id: 'claim-transfer-004',
        type: 'TOKEN_TRANSFER',
        token: '0x4444444444444444444444444444444444444444',
        recipient: '0x3333333333333333333333333333333333333333',
        amount: '5000000000000000000000000',
        unit: 'raw_tokens'
      }
    ],

    observedEffects: {
      transfers: [
        {
          token: '0x4444444444444444444444444444444444444444',
          from: '0x1111111111111111111111111111111111111111',
          to: '0x3333333333333333333333333333333333333333',
          amount: '5000000000000000000000000',
          logIndex: 0,
          matchedClaimId: 'claim-transfer-004'
        }
      ],
      nativeTransfers: [],
      stateDiffs: [], // Missing / truncated!
      ownership: {
        contract: '0x1111111111111111111111111111111111111111',
        before: '0x0000000000000000000000002222222222222222222222222222222222222222',
        after: 'Absent / Unrecorded',
        isMissing: true
      }
    },

    evalChain: {
      claimConfidence: {
        status: 'INCOMPLETE TRACE EVIDENCE',
        level: 'warning',
        evidence: 'Tracer output buffer exceeded memory limit at step 420; trace truncated.',
        limitations: 'Fail-closed: absence of recorded exploit does NOT imply absence of risk.'
      },
      coiRisk: {
        status: 'UNKNOWN',
        level: 'neutral',
        evidence: 'Trace did not record recipient ledger depth.',
        limitations: 'Incomplete transaction history.'
      },
      votingStatus: {
        status: 'BLOCKED',
        level: 'warning',
        evidence: 'Proposal trace must be re-run with expanded tracer buffer.',
        limitations: 'Infrastructure limitation.'
      },
      executionDiscrepancy: {
        status: 'UNVERIFIABLE',
        level: 'warning',
        evidence: 'Subsequent calls not logged.',
        limitations: 'Tracer truncated.'
      }
    },

    coiData: {
      proposer: '0x4444444444444444444444444444444444444444',
      beneficiary: '0x3333333333333333333333333333333333333333',
      provenance: 'None (Data missing)',
      relationshipDepth: 'Uncalculated',
      uncertainty: 'HIGH (Incomplete trace)',
      connections: []
    }
  },

  {
    id: 'prop-005',
    version: 'v1.0',
    title: 'Research Fellowship Endowment Grant',
    description: 'Claims a 5,000,000 MOCK grant to researcher. Execution trace reveals an unclaimed second transfer sending 1,000,000 MOCK to attacker address.',
    proposer: '0x9999999999999999999999999999999999999999',
    targetTreasury: '0x1111111111111111111111111111111111111111',
    status: 'CHALLENGED',
    submittedAt: '2026-10-25T09:00:00Z',
    versionHash: '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',

    verdict: {
      status: 'MISMATCH',
      reasonCode: 'MISMATCH_UNCLAIMED_MATERIAL_TRANSFER',
      explanation: 'Observed unclaimed material transfer of 1,000,000 tokens (0x4444...4444) from Treasury to attacker 0x9999...9999 (Log #1).',
      traceComplete: true,
      simulationMode: 'local_evm',
      evidenceReferences: [
        {
          source: 'log',
          identifier: 'log[1]',
          details: {
            token: '0x4444444444444444444444444444444444444444',
            from: '0x1111111111111111111111111111111111111111',
            to: '0x9999999999999999999999999999999999999999',
            amount: '1000000000000000000000000'
          }
        }
      ],
      findings: []
    },

    claims: [
      {
        claim_id: 'claim-transfer-005',
        type: 'TOKEN_TRANSFER',
        token: '0x4444444444444444444444444444444444444444',
        recipient: '0x3333333333333333333333333333333333333333',
        amount: '5000000000000000000000000',
        unit: 'raw_tokens'
      }
    ],

    observedEffects: {
      transfers: [
        {
          token: '0x4444444444444444444444444444444444444444',
          from: '0x1111111111111111111111111111111111111111',
          to: '0x3333333333333333333333333333333333333333',
          amount: '5000000000000000000000000',
          logIndex: 0,
          matchedClaimId: 'claim-transfer-005'
        },
        {
          token: '0x4444444444444444444444444444444444444444',
          from: '0x1111111111111111111111111111111111111111',
          to: '0x9999999999999999999999999999999999999999',
          amount: '1000000000000000000000000',
          logIndex: 1,
          matchedClaimId: null,
          isUnclaimedMaterial: true
        }
      ],
      nativeTransfers: [],
      stateDiffs: [],
      ownership: {
        contract: '0x1111111111111111111111111111111111111111',
        before: '0x0000000000000000000000002222222222222222222222222222222222222222',
        after: '0x0000000000000000000000002222222222222222222222222222222222222222',
        hasMutated: false
      }
    },

    evalChain: {
      claimConfidence: {
        status: 'UNCLAIMED TRANSFER VIOLATION',
        level: 'danger',
        evidence: 'EVM log #1 recorded unauthorized 1,000,000 MOCK transfer to proposer.',
        limitations: 'Deterministic log evidence.'
      },
      coiRisk: {
        status: 'SELF-DEALING PROVEN',
        level: 'danger',
        evidence: 'Unclaimed funds sent directly to proposer address 0x9999...9999.',
        limitations: 'Proposer and receiver are identical address.'
      },
      votingStatus: {
        status: 'DO NOT VOTE / FRAUDULENT',
        level: 'danger',
        evidence: 'Challenger staked 50,000 MOCK. Slashing vote active.',
        limitations: 'None.'
      },
      executionDiscrepancy: {
        status: 'EXTRA TRANSFER DRAIN',
        level: 'danger',
        evidence: '1M tokens diverted without disclosure.',
        limitations: 'None.'
      }
    },

    coiData: {
      proposer: '0x9999999999999999999999999999999999999999',
      beneficiary: '0x3333333333333333333333333333333333333333',
      provenance: 'On-chain execution trace Log #1',
      relationshipDepth: 'Direct Self-Transfer (0-Hops to Proposer)',
      uncertainty: 'ZERO (Identical Address)',
      connections: [
        {
          from: '0x1111111111111111111111111111111111111111',
          to: '0x9999999999999999999999999999999999999999',
          txHash: '0xsimulation_log_1',
          amount: '1,000,000 MOCK',
          timestamp: '2026-10-25T09:00:00Z',
          label: 'Unclaimed Diverted Transfer'
        }
      ]
    }
  },

  {
    id: 'prop-006',
    version: 'v1.0',
    title: 'Cross-Chain Relayer Subsidies',
    description: 'Relayer reimbursement transaction that encounters an access-control revert inside the callee.',
    proposer: '0x3333333333333333333333333333333333333333',
    targetTreasury: '0x1111111111111111111111111111111111111111',
    status: 'ACTIVE',
    submittedAt: '2026-10-25T08:00:00Z',
    versionHash: '0x5555555555555555555555555555555555555555555555555555555555555555',

    verdict: {
      status: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_SIMULATION_FAILED',
      explanation: 'Simulation reverted or failed: Execution reverted with custom error: Unauthorized(0x3333...3333). Never verified.',
      traceComplete: true,
      simulationMode: 'local_evm',
      evidenceReferences: [
        {
          source: 'schema',
          identifier: 'success',
          details: { errors: ['Unauthorized(0x3333...3333)'] }
        }
      ],
      findings: []
    },

    claims: [
      {
        claim_id: 'claim-transfer-006',
        type: 'TOKEN_TRANSFER',
        token: '0x4444444444444444444444444444444444444444',
        recipient: '0x3333333333333333333333333333333333333333',
        amount: '200000000000000000000000',
        unit: 'raw_tokens'
      }
    ],

    observedEffects: {
      transfers: [],
      nativeTransfers: [],
      stateDiffs: [],
      ownership: {
        contract: '0x1111111111111111111111111111111111111111',
        before: '0x0000000000000000000000002222222222222222222222222222222222222222',
        after: '0x0000000000000000000000002222222222222222222222222222222222222222',
        hasMutated: false
      }
    },

    evalChain: {
      claimConfidence: {
        status: 'EXECUTION REVERTED',
        level: 'warning',
        evidence: 'EVM call returned false; custom error Unauthorized() bubbled up.',
        limitations: 'Simulation failed to execute.'
      },
      coiRisk: {
        status: 'LOW RISK',
        level: 'good',
        evidence: 'Standard relayer registry.',
        limitations: 'Relayer node key unverified.'
      },
      votingStatus: {
        status: 'INVALID PROPOSAL',
        level: 'warning',
        evidence: 'Execution will revert if enacted on-chain.',
        limitations: 'Requires payload revision.'
      },
      executionDiscrepancy: {
        status: 'REVERTED',
        level: 'warning',
        evidence: '0 tokens transferred due to revert.',
        limitations: 'None.'
      }
    },

    coiData: {
      proposer: '0x3333333333333333333333333333333333333333',
      beneficiary: '0x3333333333333333333333333333333333333333',
      provenance: 'Relayer multisig',
      relationshipDepth: 'Self (Relayer)',
      uncertainty: 'LOW',
      connections: []
    }
  }
];

export const DEMO_RED_TEAM_ARENA = {
  testSuite: 'Foundry Step1.t.sol + Phase 3 Deterministic Engine',
  totalPayloadsTested: 6,
  caughtCount: 2,
  escalatedCount: 4,
  missedCount: 0,
  detectionRate: '100% (6/6)',
  falseVerifiedRate: '0.0% (Fail-Closed Validated)',
  scenarios: [
    {
      id: 'RT-01',
      name: 'Slot 0 Storage Collision (Ownership Hijack)',
      category: 'Storage Collision',
      payloadContract: 'MaliciousPayload.sol (Phase 1)',
      targetSlot: 'Slot 0 (Treasury.owner)',
      observedResult: 'CAUGHT',
      verdictAssigned: 'MISMATCH',
      reasonCode: 'MISMATCH_OWNERSHIP_COLLISION',
      evidenceDetails: 'State diff confirmed Slot 0 overwritten with attacker address under delegatecall.'
    },
    {
      id: 'RT-02',
      name: 'Unclaimed Secondary Token Drain',
      category: 'Unauthorized Transfer',
      payloadContract: 'simulation_unexpected_transfer.json (Phase 3)',
      targetSlot: 'MockToken balance of attacker',
      observedResult: 'CAUGHT',
      verdictAssigned: 'MISMATCH',
      reasonCode: 'MISMATCH_UNCLAIMED_MATERIAL_TRANSFER',
      evidenceDetails: 'Unclaimed 1,000,000 MOCK transfer detected in EVM event Log #1.'
    },
    {
      id: 'RT-03',
      name: 'Benign Delegatecall Execution Flag',
      category: 'Opcode Hazard',
      payloadContract: 'HonestPayload.sol via delegatecall',
      targetSlot: 'None (Stateless)',
      observedResult: 'ESCALATED',
      verdictAssigned: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_RISKY_OPERATION_FLAG',
      evidenceDetails: 'DELEGATECALL opcode flagged in findings; required reviewer authorization.'
    },
    {
      id: 'RT-04',
      name: 'Truncated Execution Trace Exhaustion',
      category: 'Trace Truncation',
      payloadContract: 'simulation_incomplete_trace.json',
      targetSlot: 'N/A',
      observedResult: 'ESCALATED',
      verdictAssigned: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_TRACE_INCOMPLETE',
      evidenceDetails: 'trace_complete: false triggered fail-closed review. Never inferred safety from missing logs.'
    },
    {
      id: 'RT-05',
      name: 'Pre-Execution Callee Revert Attack',
      category: 'Execution Failure',
      payloadContract: 'Unauthorized callee caller',
      targetSlot: 'N/A',
      observedResult: 'ESCALATED',
      verdictAssigned: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_SIMULATION_FAILED',
      evidenceDetails: 'Execution reverted; blocked voting on failed proposal.'
    },
    {
      id: 'RT-06',
      name: 'Ambiguous Range Parameter Injection',
      category: 'Claims Schema Exploitation',
      payloadContract: 'claims_ambiguous.json',
      targetSlot: 'N/A',
      observedResult: 'ESCALATED',
      verdictAssigned: 'NEEDS_REVIEW',
      reasonCode: 'NEEDS_REVIEW_CLAIMS_AMBIGUOUS',
      evidenceDetails: 'Ambiguous amount string "5M to 10M" and missing unit rejected by claims validator.'
    }
  ]
};

export const DEMO_CHALLENGES = [
  {
    id: 'chal-001',
    proposalId: 'prop-002',
    challenger: '0x7777777777777777777777777777777777777777',
    stakeAmount: '50,000 MOCK',
    status: 'ACTIVE_CONFIRMED',
    claimedViolation: 'Slot 0 Storage Collision & Malicious Delegatecall',
    filedAt: '2026-10-25T14:30:00Z',
    secondReviewerStatus: 'ESCALATED_CONFIRMED_MALICIOUS',
    guardianAction: 'EMERGENCY_PAUSE_EXECUTED'
  }
];

export const DEMO_GUARDIAN_EVENTS = [
  {
    id: 'guard-001',
    proposalId: 'prop-002',
    timestamp: '2026-10-25T15:45:00Z',
    status: 'ACTIVE_PAUSE',
    reason: 'Emergency pause executed on Proposal #prop-002: Veritas Gate detected Slot 0 ownership collision attempt.',
    authorizedBy: '0x1111111111111111111111111111111111111111 (Treasury Guardian Multi-Sig)',
    txHash: '0x9812470123847120394871209384712093847120394871209384712039847120'
  }
];
