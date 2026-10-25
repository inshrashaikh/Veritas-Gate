/**
 * components/guardianPanel.js
 * ============================
 * Challenge and Guardian Emergency Response Panel.
 * 
 * Rules:
 * - Shows challenge status, staked bond amounts, and dispute resolution.
 * - Displays second-reviewer decisions and Guardian pause events with reasons.
 */

import { escapeHTML, truncateAddress } from '../security.js';

export function renderGuardianPanel(state) {
  const challenges = state.challenges || [];
  const guardianEvents = state.guardianEvents || [];
  const isDemo = state.isDemoData;

  return `
    <section class="guardian-section" aria-labelledby="guardian-heading">
      <div class="section-header">
        <div>
          <h2 id="guardian-heading" class="section-title">Challenge &amp; Guardian Emergency Response</h2>
          <p class="section-desc">
            Bonded adversarial challenges, second-reviewer adjudications, and multisig Guardian pause triggers.
          </p>
        </div>
        ${isDemo ? '<span class="badge badge-warning">DEMO MODE</span>' : ''}
      </div>

      <div class="guardian-grid">
        <!-- Active Challenges -->
        <div class="card challenge-card">
          <div class="card-header">
            <div>
              <h3 class="card-title">Bonded Challenges &amp; Slashing Queue</h3>
              <p class="card-desc">Challengers stake token bonds to freeze disputed proposals for re-audit.</p>
            </div>
            <span class="badge badge-neutral">${challenges.length} Active Challenges</span>
          </div>

          ${challenges.length === 0 ? `
            <div class="p-3 text-muted text-center">
              No active proposal challenges filed.
            </div>
          ` : `
            <div class="challenge-list">
              ${challenges.map(c => `
                <div class="challenge-item">
                  <div class="challenge-item-header">
                    <div>
                      <span class="badge badge-danger">CHALLENGE #${escapeHTML(c.id)}</span>
                      <strong>Target: ${escapeHTML(c.proposalId)}</strong>
                    </div>
                    <span class="badge badge-warning font-bold">Bond: ${escapeHTML(c.stakeAmount)}</span>
                  </div>

                  <div class="challenge-body">
                    <p><strong>Claimed Violation:</strong> ${escapeHTML(c.claimedViolation)}</p>
                    <div class="meta-row text-xs text-muted">
                      <span>Challenger: <code>${truncateAddress(c.challenger)}</code></span>
                      <span>Filed: ${new Date(c.filedAt).toLocaleString()}</span>
                    </div>
                  </div>

                  <div class="challenge-status-row">
                    <span class="sub-label">Second Reviewer Status:</span>
                    <span class="badge badge-outline">${escapeHTML(c.secondReviewerStatus || 'PENDING')}</span>
                  </div>
                </div>
              `).join('')}
            </div>
          `}
        </div>

        <!-- Guardian Pause Events -->
        <div class="card guardian-events-card">
          <div class="card-header">
            <div>
              <h3 class="card-title">Guardian Emergency Pause Events</h3>
              <p class="card-desc">Safety circuit-breaker executions enacted by multi-sig guardians.</p>
            </div>
            <span class="badge badge-danger">${guardianEvents.length} Recorded Pauses</span>
          </div>

          ${guardianEvents.length === 0 ? `
            <div class="p-3 text-muted text-center">
              Circuit-breakers normal. Zero emergency pause events recorded.
            </div>
          ` : `
            <div class="guardian-events-list">
              ${guardianEvents.map(g => `
                <div class="guardian-event-item">
                  <div class="guardian-event-header">
                    <span class="badge badge-danger">${escapeHTML(g.status || 'PAUSED')}</span>
                    <span class="event-time text-xs text-muted">${new Date(g.timestamp).toLocaleString()}</span>
                  </div>
                  <div class="guardian-event-reason">
                    <strong>Trigger Rationale:</strong> ${escapeHTML(g.reason)}
                  </div>
                  <div class="guardian-event-meta text-xs text-muted">
                    <div>Authorized by: <code>${escapeHTML(g.authorizedBy)}</code></div>
                    <div>Tx Hash: <code>${truncateAddress(g.txHash, 10, 8)}</code></div>
                  </div>
                </div>
              `).join('')}
            </div>
          `}
        </div>
      </div>
    </section>
  `;
}
