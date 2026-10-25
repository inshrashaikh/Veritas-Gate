/**
 * components/overview.js
 * ======================
 * Overview metrics cards, verdict distribution, treasury impact, and latest audit events.
 */

import { escapeHTML, formatTokenAmount } from '../security.js';

export function renderOverview(state) {
  const metrics = state.metrics;
  const error = state.error;

  if (error && !state.isDemoData) {
    return `
      <section class="overview-section" aria-labelledby="overview-heading">
        <h2 id="overview-heading" class="sr-only">System Overview</h2>
        <div class="card alert-card error-alert">
          <div class="alert-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div class="alert-body">
            <h3>Backend API Offline or Unreachable</h3>
            <p>${escapeHTML(error)}</p>
            <p class="text-muted">
              Veritas Gate is operating with fail-closed discipline. No fake data is substituted.
              You can start the backend service at <code>http://localhost:8000/api/v1</code>, or explore the dashboard with our test harness fixtures by enabling <strong>Demo Mode</strong>.
            </p>
            <div class="alert-actions">
              <button class="btn btn-sm btn-primary" onclick="document.getElementById('toggle-demo-btn').click()">
                Enable Demo Mode (Labeled Fixtures)
              </button>
              <button class="btn btn-sm btn-outline" onclick="document.getElementById('refresh-btn').click()">
                Retry Connection
              </button>
            </div>
          </div>
        </div>
      </section>
    `;
  }

  if (!metrics) {
    return `
      <section class="overview-section">
        <div class="loading-state">
          <div class="spinner"></div>
          <p>Loading governance analytics...</p>
        </div>
      </section>
    `;
  }

  const treasuryBalance = formatTokenAmount(metrics.treasury?.totalBalance, 18, 'MOCK');
  const treasuryRequested = formatTokenAmount(metrics.treasury?.requestedTotal, 18, 'MOCK');
  const nativeBalance = formatTokenAmount(metrics.treasury?.nativeBalanceWei, 18, 'ETH');

  return `
    <section class="overview-section" aria-labelledby="overview-heading">
      <div class="section-header">
        <div>
          <h2 id="overview-heading" class="section-title">Governance Health &amp; Audit Overview</h2>
          <p class="section-desc">Real-time deterministic verification status, treasury allocations, and security events.</p>
        </div>
        ${state.isDemoData ? '<span class="badge badge-warning">DEMO DATA</span>' : '<span class="badge badge-success">LIVE DATA</span>'}
      </div>

      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-label">Total Proposals</div>
          <div class="metric-value">${metrics.totalProposals ?? 0}</div>
          <div class="metric-sub">Tracked across governance epochs</div>
        </div>

        <div class="metric-card verdict-verified-border">
          <div class="metric-label">Verified (Clean)</div>
          <div class="metric-value text-success">${metrics.verifiedCount ?? 0}</div>
          <div class="metric-sub">100% promises match execution</div>
        </div>

        <div class="metric-card verdict-mismatch-border">
          <div class="metric-label">Proven Mismatch</div>
          <div class="metric-value text-danger">${metrics.mismatchCount ?? 0}</div>
          <div class="metric-sub">Critical violations or extra drains</div>
        </div>

        <div class="metric-card verdict-needs-review-border">
          <div class="metric-label">Needs Manual Review</div>
          <div class="metric-value text-warning">${metrics.needsReviewCount ?? 0}</div>
          <div class="metric-sub">Risky flags, truncated trace, reverts</div>
        </div>
      </div>

      <div class="overview-split">
        <div class="card treasury-impact-card">
          <div class="card-header">
            <h3 class="card-title">Treasury Balance &amp; Impact</h3>
            <span class="badge badge-info">Denomination: 18 decimals</span>
          </div>
          <div class="treasury-stats">
            <div class="t-stat">
              <span class="t-stat-label">Treasury MOCK Balance</span>
              <span class="t-stat-value">${treasuryBalance.formatted}</span>
              <span class="t-stat-raw">Raw: ${escapeHTML(treasuryBalance.exact)} wei</span>
            </div>
            <div class="t-stat">
              <span class="t-stat-label">Native Balance</span>
              <span class="t-stat-value">${nativeBalance.formatted}</span>
              <span class="t-stat-raw">Raw: ${escapeHTML(nativeBalance.exact)} wei</span>
            </div>
            <div class="t-stat">
              <span class="t-stat-label">Total Requested in Proposals</span>
              <span class="t-stat-value text-warning">${treasuryRequested.formatted}</span>
              <span class="t-stat-raw">Raw: ${escapeHTML(treasuryRequested.exact)} wei</span>
            </div>
          </div>
          <div class="card-footer-note">
            Treasury storage is strictly guarded against Slot 0 delegatecall collisions.
          </div>
        </div>

        <div class="card audit-feed-card">
          <div class="card-header">
            <h3 class="card-title">Latest Audit Events</h3>
            <span class="badge badge-neutral">${metrics.latestAuditEvents?.length || 0} events</span>
          </div>
          <div class="audit-feed-list">
            ${(metrics.latestAuditEvents || []).map(evt => `
              <div class="audit-feed-item">
                <div class="audit-badge-col">
                  <span class="badge badge-sm ${evt.verdict === 'VERIFIED' ? 'badge-success' : evt.verdict === 'MISMATCH' ? 'badge-danger' : 'badge-warning'}">
                    ${escapeHTML(evt.verdict || evt.type)}
                  </span>
                </div>
                <div class="audit-details-col">
                  <div class="audit-summary">${escapeHTML(evt.summary)}</div>
                  <div class="audit-meta">
                    <span>Target: <strong>${escapeHTML(evt.proposalId)}</strong></span>
                    <span>Actor: <code>${escapeHTML(evt.actor)}</code></span>
                    <span>${new Date(evt.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    </section>
  `;
}
