/**
 * components/effectsDiff.js
 * =========================
 * Promises vs Actual Effects comparison table.
 * 
 * Rules:
 * - Side-by-side comparison of claimed effects vs observed execution traces.
 * - STRICT: Clearly distinguishes missing evidence from zero values.
 * - Shows tokens, recipients, amounts, ownership (Slot 0), allowances, and storage changes.
 */

import { escapeHTML, formatTokenAmount, truncateAddress } from '../security.js';

export function renderEffectsDiff(proposal) {
  if (!proposal) return '';

  const claims = proposal.claims || [];
  const observed = proposal.observedEffects || { transfers: [], nativeTransfers: [], stateDiffs: [], ownership: null };

  const observedTransfers = observed.transfers || [];
  const observedStateDiffs = observed.stateDiffs || [];
  const ownership = observed.ownership;

  return `
    <div class="card effects-diff-card">
      <div class="card-header">
        <div>
          <h3 class="card-title">Promises vs. Observed EVM Execution Effects</h3>
          <p class="card-desc">Deterministic comparison between author promises and actual bytecode trace results.</p>
        </div>
        <div class="card-header-tags">
          <span class="badge badge-sm badge-neutral">Claims: ${claims.length}</span>
          <span class="badge badge-sm badge-neutral">Observed Transfers: ${observedTransfers.length}</span>
        </div>
      </div>

      <!-- Token Transfers Comparison -->
      <div class="diff-section">
        <h4 class="diff-section-title">
          <span class="diff-icon">🪙</span> ERC-20 Token Transfers
        </h4>
        <div class="table-responsive">
          <table class="data-table diff-table">
            <thead>
              <tr>
                <th>Effect Type</th>
                <th>Token</th>
                <th>Recipient</th>
                <th>Claimed Amount</th>
                <th>Observed Amount</th>
                <th>Status / Discrepancy</th>
              </tr>
            </thead>
            <tbody>
              ${claims.filter(c => c.type === 'TOKEN_TRANSFER').map(c => {
                const claimedFmt = formatTokenAmount(c.amount, 18, 'MOCK');
                // Find matching observed transfer
                const match = observedTransfers.find(o => 
                  o.token?.toLowerCase() === c.token?.toLowerCase() &&
                  o.to?.toLowerCase() === c.recipient?.toLowerCase()
                );

                let observedFmt;
                let statusBadge;

                if (!match) {
                  observedFmt = { formatted: '0 MOCK (Not Transferred)', exact: '0', isZero: true };
                  statusBadge = '<span class="badge badge-danger">MISSING EFFECT</span>';
                } else if (String(match.amount) === String(c.amount)) {
                  observedFmt = formatTokenAmount(match.amount, 18, 'MOCK');
                  statusBadge = '<span class="badge badge-success">EXACT MATCH</span>';
                } else {
                  observedFmt = formatTokenAmount(match.amount, 18, 'MOCK');
                  statusBadge = '<span class="badge badge-danger">AMOUNT MISMATCH</span>';
                }

                return `
                  <tr>
                    <td><code>TOKEN_TRANSFER</code></td>
                    <td><code title="${escapeHTML(c.token)}">${truncateAddress(c.token)}</code></td>
                    <td><code title="${escapeHTML(c.recipient)}">${truncateAddress(c.recipient)}</code></td>
                    <td>
                      <div class="amount-bold">${claimedFmt.formatted}</div>
                      <div class="text-muted text-xs">Raw: ${escapeHTML(claimedFmt.exact)}</div>
                    </td>
                    <td>
                      <div class="amount-bold">${observedFmt.formatted}</div>
                      <div class="text-muted text-xs">Raw: ${escapeHTML(observedFmt.exact)}</div>
                    </td>
                    <td>${statusBadge}</td>
                  </tr>
                `;
              }).join('')}

              <!-- Detect Unclaimed Extra Transfers -->
              ${observedTransfers.filter(o => o.isUnclaimedMaterial).map(unclaimed => {
                const unfmt = formatTokenAmount(unclaimed.amount, 18, 'MOCK');
                return `
                  <tr class="row-danger-highlight">
                    <td><span class="badge badge-danger">UNCLAIMED TRANSFER</span></td>
                    <td><code title="${escapeHTML(unclaimed.token)}">${truncateAddress(unclaimed.token)}</code></td>
                    <td><code class="text-danger" title="${escapeHTML(unclaimed.to)}">${truncateAddress(unclaimed.to)} (Attacker)</code></td>
                    <td>
                      <span class="badge badge-neutral">NEVER CLAIMED</span>
                    </td>
                    <td>
                      <div class="amount-bold text-danger">+${unfmt.formatted}</div>
                      <div class="text-muted text-xs">Raw: ${escapeHTML(unfmt.exact)}</div>
                    </td>
                    <td>
                      <span class="badge badge-danger">DRAIN DETECTED</span>
                    </td>
                  </tr>
                `;
              }).join('')}

              ${claims.filter(c => c.type === 'TOKEN_TRANSFER').length === 0 && observedTransfers.length === 0 ? `
                <tr>
                  <td colspan="6" class="text-center text-muted">No token transfer claims declared or observed.</td>
                </tr>
              ` : ''}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Ownership & Storage Slot 0 Comparison -->
      <div class="diff-section">
        <h4 class="diff-section-title">
          <span class="diff-icon">🛡️</span> Contract Ownership &amp; Storage Slot 0
        </h4>
        <div class="ownership-diff-box">
          ${ownership ? `
            <div class="ownership-grid">
              <div class="ownership-col">
                <span class="sub-label">Target Contract</span>
                <code>${truncateAddress(ownership.contract)}</code>
              </div>
              <div class="ownership-col">
                <span class="sub-label">Pre-Execution Owner (Slot 0)</span>
                <code>${truncateAddress(ownership.before)}</code>
              </div>
              <div class="ownership-col">
                <span class="sub-label">Post-Execution Owner (Slot 0)</span>
                ${ownership.isMissing ? 
                  '<span class="badge badge-warning">EVIDENCE MISSING (TRUNCATED)</span>' : 
                  ownership.hasMutated ? 
                    `<code class="text-danger font-bold">${truncateAddress(ownership.after)} (HIJACKED)</code>` : 
                    `<code class="text-success">${truncateAddress(ownership.after)} (UNCHANGED)</code>`
                }
              </div>
              <div class="ownership-col">
                <span class="sub-label">Verdict Implication</span>
                ${ownership.isMissing ? 
                  '<span class="badge badge-warning">FAIL-CLOSED (NEEDS REVIEW)</span>' : 
                  ownership.hasMutated ? 
                    '<span class="badge badge-danger">PROVEN STORAGE COLLISION</span>' : 
                    '<span class="badge badge-success">STORAGE PRESERVED</span>'
                }
              </div>
            </div>
          ` : `
            <div class="text-muted p-2">
              <span class="badge badge-neutral">Zero Storage Changes</span> No contract storage modifications were observed in EVM diff.
            </div>
          `}
        </div>
      </div>

      <!-- State Diffs Table (All Mutated Slots) -->
      ${observedStateDiffs.length > 0 ? `
        <div class="diff-section">
          <h4 class="diff-section-title">
            <span class="diff-icon">📝</span> Complete EVM Storage State Diffs (${observedStateDiffs.length})
          </h4>
          <div class="table-responsive">
            <table class="data-table-sm diff-table">
              <thead>
                <tr>
                  <th>Address</th>
                  <th>Slot Key</th>
                  <th>Variable Name</th>
                  <th>Before (Hex)</th>
                  <th>After (Hex)</th>
                  <th>Mutation Status</th>
                </tr>
              </thead>
              <tbody>
                ${observedStateDiffs.map(d => `
                  <tr>
                    <td><code>${truncateAddress(d.address)}</code></td>
                    <td><code>${escapeHTML(d.slot)}</code></td>
                    <td>${escapeHTML(d.slotName || 'unnamed')}</td>
                    <td><code class="code-hex">${escapeHTML(d.before)}</code></td>
                    <td><code class="code-hex ${d.hasMutated ? 'text-danger' : ''}">${escapeHTML(d.after)}</code></td>
                    <td>
                      ${d.hasMutated ? 
                        '<span class="badge badge-sm badge-danger">MUTATED</span>' : 
                        '<span class="badge badge-sm badge-neutral">UNTOUCHED</span>'}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      ` : ''}
    </div>
  `;
}
