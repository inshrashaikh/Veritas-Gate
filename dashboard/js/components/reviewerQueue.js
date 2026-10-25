/**
 * components/reviewerQueue.js
 * ============================
 * Reviewer Queue for proposals flagged with NEEDS_REVIEW.
 * 
 * Rules:
 * - Shows claims, actual effects, risks, and evidence for manual auditor review.
 * - STRICT: APPROVE, REJECT, and ESCALATE actions require a mandatory written reason (min 10 chars).
 * - Displays reviewer identity and signature verification status.
 * - In demo mode, records simulated decisions with clear [SIMULATED LOCAL] badges.
 */

import { escapeHTML, truncateAddress } from '../security.js';

export function renderReviewerQueue(state) {
  const needsReviewProposals = state.proposals.filter(p => p.verdict?.status === 'NEEDS_REVIEW');
  const isDemo = state.isDemoData;

  return `
    <section class="reviewer-queue-section" aria-labelledby="reviewer-heading">
      <div class="section-header">
        <div>
          <h2 id="reviewer-heading" class="section-title">Designated Reviewer Queue</h2>
          <p class="section-desc">
            Manual security auditor clearance for proposals containing risky opcodes, incomplete execution traces, or reverted simulations.
          </p>
        </div>
        <div class="header-tags">
          <span class="badge badge-warning">${needsReviewProposals.length} Proposals Awaiting Action</span>
          ${isDemo ? '<span class="badge badge-warning">DEMO MODE — SIMULATED DATA</span>' : ''}
        </div>
      </div>

      ${needsReviewProposals.length === 0 ? `
        <div class="card empty-state-card">
          <div class="empty-icon">🛡️</div>
          <h3>Queue Clear</h3>
          <p class="text-muted">No proposals currently require manual reviewer clearance. All active proposals have either passed cleanly (VERIFIED) or failed definitively (MISMATCH).</p>
        </div>
      ` : `
        <div class="reviewer-cards-grid">
          ${needsReviewProposals.map(p => {
            const v = p.verdict || {};
            const findings = v.findings || [];
            const reviews = p.reviews || [];

            return `
              <div class="card reviewer-item-card" data-proposal-id="${escapeHTML(p.id)}">
                <div class="reviewer-item-header">
                  <div>
                    <span class="badge badge-warning">${escapeHTML(p.id)}</span>
                    <h3 class="reviewer-item-title">${escapeHTML(p.title)}</h3>
                  </div>
                  <span class="badge badge-danger">${escapeHTML(v.reasonCode || 'NEEDS_REVIEW')}</span>
                </div>

                <div class="reviewer-item-desc text-muted">
                  ${escapeHTML(p.description)}
                </div>

                <div class="reviewer-risk-box">
                  <div class="box-label text-warning font-bold">
                    Reason for Manual Hold:
                  </div>
                  <p class="box-text">${escapeHTML(v.explanation)}</p>
                </div>

                ${findings.length > 0 ? `
                  <div class="reviewer-findings-box">
                    <span class="sub-label">Observed Risk Flags:</span>
                    <div class="tags-row">
                      ${findings.map(f => `
                        <span class="badge badge-sm badge-danger" title="${escapeHTML(f.description)}">
                          ${escapeHTML(f.code)}
                        </span>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}

                <div class="reviewer-meta-row">
                  <span>Proposer: <code>${truncateAddress(p.proposer)}</code></span>
                  <span>Trace Integrity: <strong>${v.traceComplete ? '✓ Complete' : '⚠ Truncated'}</strong></span>
                </div>

                ${reviews.length > 0 ? `
                  <div class="reviewer-history-box" style="margin-top: 12px; padding: 10px; background: rgba(59, 130, 246, 0.08); border-radius: var(--radius-sm); border: 1px solid var(--border-color);">
                    <span class="sub-label font-bold">Recorded Auditor Attestations:</span>
                    ${reviews.map(r => `
                      <div class="review-entry text-xs" style="margin-top: 4px;">
                        <span class="badge badge-sm ${r.action === 'APPROVE' ? 'badge-success' : r.action === 'REJECT' ? 'badge-danger' : 'badge-warning'}">
                          ${escapeHTML(r.action)}
                        </span>
                        <span>${r.simulated ? ' [SIMULATED LOCAL]' : ''}: <em>"${escapeHTML(r.reason)}"</em></span>
                        <span class="text-muted"> — by <code>${truncateAddress(r.reviewer)}</code></span>
                      </div>
                    `).join('')}
                  </div>
                ` : ''}

                <!-- Reviewer Action Form -->
                <form class="reviewer-action-form" onsubmit="return false;" data-id="${escapeHTML(p.id)}">
                  <div class="form-group">
                    <label for="reviewer-reason-${escapeHTML(p.id)}" class="form-label font-bold">
                      Mandatory Auditor Rationale <span class="text-danger">*</span>
                    </label>
                    <textarea id="reviewer-reason-${escapeHTML(p.id)}" 
                              class="textarea reviewer-reason-input" 
                              rows="3" 
                              placeholder="Provide detailed written technical rationale for your decision (minimum 10 characters)..." 
                              data-id="${escapeHTML(p.id)}" 
                              required></textarea>
                    <span class="text-muted text-xs char-counter" id="counter-${escapeHTML(p.id)}">0 / 10 chars min</span>
                  </div>

                  <div class="reviewer-actions-row">
                    <button type="button" class="btn btn-sm btn-success reviewer-btn" 
                            data-action="APPROVE" data-id="${escapeHTML(p.id)}" disabled>
                      ✓ Approve Proposal
                    </button>
                    <button type="button" class="btn btn-sm btn-danger reviewer-btn" 
                            data-action="REJECT" data-id="${escapeHTML(p.id)}" disabled>
                      ✕ Reject Proposal
                    </button>
                    <button type="button" class="btn btn-sm btn-warning reviewer-btn" 
                            data-action="ESCALATE" data-id="${escapeHTML(p.id)}" disabled>
                      ⚡ Escalate to Multi-Sig
                    </button>
                  </div>

                  <div class="action-feedback" id="feedback-${escapeHTML(p.id)}"></div>
                </form>
              </div>
            `;
          }).join('')}
        </div>
      `}
    </section>
  `;
}
