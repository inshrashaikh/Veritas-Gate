/**
 * components/coiPanel.js
 * ======================
 * Conflict of Interest (COI) & Wallet Adjacency Panel.
 * 
 * Rules:
 * - Visualizes known wallet connections and transfer paths using available data.
 * - Shows provenance, relationship depth, and uncertainty rating.
 * - STRICT: Never claims common ownership solely from a transfer.
 */

import { escapeHTML, truncateAddress } from '../security.js';

export function renderCoiPanel(proposal) {
  if (!proposal || !proposal.coiData) return '';

  const coi = proposal.coiData;
  const connections = coi.connections || [];

  return `
    <div class="card coi-panel-card">
      <div class="card-header">
        <div>
          <h3 class="card-title">Conflict of Interest (COI) &amp; Wallet Adjacency</h3>
          <p class="card-desc">Known on-chain fund flows and counterparty relationships associated with this proposal.</p>
        </div>
        <span class="badge badge-outline">Uncertainty: ${escapeHTML(coi.uncertainty || 'MODERATE')}</span>
      </div>

      <div class="coi-metrics-grid">
        <div class="coi-metric-box">
          <span class="sub-label">Proposer Wallet</span>
          <code>${truncateAddress(coi.proposer)}</code>
        </div>
        <div class="coi-metric-box">
          <span class="sub-label">Beneficiary Wallet</span>
          <code>${truncateAddress(coi.beneficiary)}</code>
        </div>
        <div class="coi-metric-box">
          <span class="sub-label">Graph Relationship Depth</span>
          <strong>${escapeHTML(coi.relationshipDepth || 'Unindexed')}</strong>
        </div>
        <div class="coi-metric-box">
          <span class="sub-label">Data Provenance Source</span>
          <span class="text-xs text-muted">${escapeHTML(coi.provenance || 'Public Explorer Index')}</span>
        </div>
      </div>

      <!-- Graph Visualization of Transfer Paths -->
      <div class="coi-graph-container">
        <h4 class="coi-graph-title">Transfer Adjacency Graph</h4>
        
        <div class="coi-visual-graph">
          <div class="coi-node node-proposer">
            <span class="node-icon">👤</span>
            <div class="node-label">Proposer</div>
            <code class="node-address">${truncateAddress(coi.proposer)}</code>
          </div>

          <div class="coi-edge">
            <span class="edge-line"></span>
            <span class="edge-label">Proposal Submission</span>
            <span class="edge-arrow">➔</span>
          </div>

          <div class="coi-node node-treasury">
            <span class="node-icon">🏛️</span>
            <div class="node-label">Treasury</div>
            <code class="node-address">${truncateAddress(proposal.targetTreasury || '0x1111...1111')}</code>
          </div>

          <div class="coi-edge">
            <span class="edge-line"></span>
            <span class="edge-label">Grant Transfer</span>
            <span class="edge-arrow">➔</span>
          </div>

          <div class="coi-node node-beneficiary">
            <span class="node-icon">🎯</span>
            <div class="node-label">Beneficiary</div>
            <code class="node-address">${truncateAddress(coi.beneficiary)}</code>
          </div>
        </div>

        ${connections.length > 0 ? `
          <div class="coi-suspicious-connections">
            <h5 class="text-danger font-bold text-xs uppercase mb-1">Observed Prior Transaction Flows:</h5>
            ${connections.map(c => `
              <div class="connection-item">
                <span class="badge badge-sm badge-danger">${escapeHTML(c.label || 'Fund Flow')}</span>
                <span>From <code>${truncateAddress(c.from)}</code> to <code>${truncateAddress(c.to)}</code></span>
                <strong>${escapeHTML(c.amount)}</strong>
                <span class="text-muted text-xs">Tx: <code>${escapeHTML(c.txHash)}</code> (${new Date(c.timestamp).toLocaleDateString()})</span>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>

      <div class="coi-warning-callout">
        <div class="warning-callout-icon">ℹ️</div>
        <div class="warning-callout-text text-xs text-muted">
          <strong>Mandatory Interpretive Standard:</strong>
          Historical transfer adjacency demonstrates that funds were transferred between addresses.
          <strong>Never claim common ownership solely from a transfer.</strong>
          Transfers may represent legitimate services, decentralized OTC swaps, or intermediate smart contracts.
        </div>
      </div>
    </div>
  `;
}
