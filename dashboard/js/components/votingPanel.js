/**
 * components/votingPanel.js
 * =========================
 * Informed-Voting Panel with Mandatory Comprehension Acknowledgement.
 * 
 * Rules:
 * - Requires voter to tick "I have seen the real effects" before enabling vote actions.
 * - STRICT: Clearly states that this is an acknowledgement, not proof of comprehension.
 * - Submits votes only through a real configured voting integration; otherwise displays explicit unavailable state.
 * - Vote button remains disabled until acknowledgement and respects backend availability.
 */

import { escapeHTML } from '../security.js';

export function renderVotingPanel(proposal, isDemoMode) {
  if (!proposal) return '';

  const verdict = proposal.verdict?.status || 'UNKNOWN';
  const isMismatch = verdict === 'MISMATCH';

  return `
    <div class="card voting-panel-card ${isMismatch ? 'voting-danger-border' : ''}">
      <div class="card-header">
        <div>
          <h3 class="card-title">Informed Voting Gateway</h3>
          <p class="card-desc">Cast your token-weighted vote after verifying the simulated execution diffs above.</p>
        </div>
        <span class="badge ${isMismatch ? 'badge-danger' : 'badge-neutral'}">
          ${isMismatch ? '⚠ CRITICAL HAZARD DETECTED' : 'STANDARD VOTING'}
        </span>
      </div>

      ${isMismatch ? `
        <div class="hazard-callout">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <div>
            <strong>Warning to Voters:</strong> This proposal has a proven <code>MISMATCH</code> verdict.
            Simulations proved contract state collision or unauthorized fund diversion. Voting FOR will compromise Treasury funds or governance ownership.
          </div>
        </div>
      ` : ''}

      <div class="voting-ack-box">
        <label class="checkbox-label" for="voting-ack-checkbox">
          <input type="checkbox" id="voting-ack-checkbox" class="checkbox">
          <span class="checkbox-text font-bold">
            I have seen the real effects of this proposal in the bytecode simulation above.
          </span>
        </label>
        <p class="ack-disclaimer text-muted text-xs">
          <strong>Mandatory Notice:</strong> Ticking this box is an acknowledgement of having viewed the EVM execution diff. It does NOT constitute proof of comprehension, technical warranty, or legal certification of safety.
        </p>
      </div>

      <div class="voting-actions-grid">
        <button id="vote-for-btn" class="btn btn-success vote-btn" data-choice="FOR" disabled>
          <span class="vote-icon">👍</span> Vote FOR
        </button>
        <button id="vote-against-btn" class="btn btn-danger vote-btn" data-choice="AGAINST" disabled>
          <span class="vote-icon">👎</span> Vote AGAINST
        </button>
        <button id="vote-abstain-btn" class="btn btn-outline vote-btn" data-choice="ABSTAIN" disabled>
          <span class="vote-icon">⚪</span> Abstain
        </button>
      </div>

      <div id="voting-feedback" class="voting-feedback-area">
        ${isDemoMode ? `
          <div class="info-pill text-muted">
            ℹ️ <strong>Demo Environment:</strong> Voting contract RPC integration is in offline test mode. Real vote broadcasting requires an active on-chain Governor integration.
          </div>
        ` : ''}
      </div>
    </div>
  `;
}
