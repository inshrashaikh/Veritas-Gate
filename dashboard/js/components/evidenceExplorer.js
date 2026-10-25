/**
 * components/evidenceExplorer.js
 * ===============================
 * Evidence Explorer & Chronological Audit Timeline.
 * 
 * Rules:
 * - Proposal text, version hashes, source metadata, simulation parameters, and audit trail.
 * - Chronological event timeline.
 */

import { escapeHTML, truncateAddress } from '../security.js';

export function renderEvidenceExplorer(proposal) {
  if (!proposal) return '';

  const v = proposal.verdict || {};

  return `
    <div class="card evidence-explorer-card">
      <div class="card-header">
        <div>
          <h3 class="card-title">Evidence Explorer &amp; Chronological Audit Timeline</h3>
          <p class="card-desc">Complete immutable cryptographic fingerprints, simulation artifacts, and provenance trail.</p>
        </div>
        <span class="badge badge-neutral">Schema: veritas-simulation-v1.0</span>
      </div>

      <div class="evidence-meta-grid">
        <div class="meta-item">
          <span class="meta-label">Proposal Version Hash</span>
          <code class="code-hex" title="${escapeHTML(proposal.versionHash || 'N/A')}">
            ${escapeHTML(proposal.versionHash || '0x000...000')}
          </code>
        </div>

        <div class="meta-item">
          <span class="meta-label">Target Treasury Contract</span>
          <code title="${escapeHTML(proposal.targetTreasury || 'N/A')}">
            ${truncateAddress(proposal.targetTreasury || '0x0000000000000000000000000000000000000000')}
          </code>
        </div>

        <div class="meta-item">
          <span class="meta-label">Simulation Scenario ID</span>
          <code>${escapeHTML(proposal.id)}-scenario</code>
        </div>

        <div class="meta-item">
          <span class="meta-label">EVM Trace Integrity</span>
          <span class="badge ${v.traceComplete ? 'badge-success' : 'badge-danger'}">
            ${v.traceComplete ? 'Trace Complete (100% Depth)' : 'Truncated / Partial Trace'}
          </span>
        </div>
      </div>

      <div class="timeline-container">
        <h4 class="timeline-title">Chronological Lifecycle &amp; Audit Events</h4>
        
        <div class="timeline">
          <div class="timeline-step step-complete">
            <div class="timeline-marker">1</div>
            <div class="timeline-content">
              <div class="timeline-header">
                <strong>Proposal Submitted &amp; Pinned</strong>
                <span class="timeline-time">${proposal.submittedAt ? new Date(proposal.submittedAt).toLocaleString() : 'N/A'}</span>
              </div>
              <p class="timeline-desc">
                Author <code>${truncateAddress(proposal.proposer)}</code> submitted ${escapeHTML(proposal.version || 'v1.0')}.
                Cryptographic hash recorded on governance ledger.
              </p>
            </div>
          </div>

          <div class="timeline-step step-complete">
            <div class="timeline-marker">2</div>
            <div class="timeline-content">
              <div class="timeline-header">
                <strong>EVM Sandboxed Simulation Run</strong>
                <span class="timeline-time">Automated Trigger</span>
              </div>
              <p class="timeline-desc">
                Fork simulation executed on Anvil local harness.
                Opcode recorder captured CALL, DELEGATECALL, SLOAD, SSTORE, and LOG events.
              </p>
            </div>
          </div>

          <div class="timeline-step ${v.status === 'VERIFIED' ? 'step-success' : v.status === 'MISMATCH' ? 'step-danger' : 'step-warning'}">
            <div class="timeline-marker">3</div>
            <div class="timeline-content">
              <div class="timeline-header">
                <strong>Deterministic Verdict Rendered</strong>
                <span class="badge ${v.status === 'VERIFIED' ? 'badge-success' : v.status === 'MISMATCH' ? 'badge-danger' : 'badge-warning'}">
                  ${escapeHTML(v.status || 'PENDING')}
                </span>
              </div>
              <p class="timeline-desc">
                Precedence engine evaluated claims against state diffs.
                Result: <code>${escapeHTML(v.reasonCode || 'N/A')}</code>.
              </p>
            </div>
          </div>

          <div class="timeline-step ${proposal.status === 'CHALLENGED' ? 'step-danger' : proposal.status === 'PASSED' ? 'step-success' : 'step-pending'}">
            <div class="timeline-marker">4</div>
            <div class="timeline-content">
              <div class="timeline-header">
                <strong>Governance &amp; Guardian Action</strong>
                <span class="badge badge-outline">${escapeHTML(proposal.status || 'ACTIVE')}</span>
              </div>
              <p class="timeline-desc">
                ${proposal.status === 'CHALLENGED' ? 
                  'Active dispute opened. Second reviewer escalation or Guardian emergency freeze in effect.' : 
                  proposal.status === 'PASSED' ? 
                  'Proposal enacted and confirmed cleanly.' : 
                  'Awaiting token holder votes or manual reviewer clearance.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
