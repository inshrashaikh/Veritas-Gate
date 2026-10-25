/**
 * components/evaluationChain.js
 * ==============================
 * Four-Stage Evaluation Chain:
 * 1. Claim Confidence
 * 2. COI Risk
 * 3. Voting Status
 * 4. Execution Discrepancy
 * 
 * Rules:
 * - Shows source evidence and methodological limitations for EVERY indicator.
 * - STRICT: Never fabricates numerical probabilities or implies calibrated mathematical heuristics.
 */

import { escapeHTML } from '../security.js';

export function renderEvaluationChain(proposal) {
  if (!proposal || !proposal.evalChain) {
    return '';
  }

  const chain = proposal.evalChain;

  const stages = [
    {
      num: 1,
      id: 'claimConfidence',
      name: 'Claim Confidence',
      icon: '🔍',
      data: chain.claimConfidence
    },
    {
      num: 2,
      id: 'coiRisk',
      name: 'COI Risk (Conflict of Interest)',
      icon: '🤝',
      data: chain.coiRisk
    },
    {
      num: 3,
      id: 'votingStatus',
      name: 'Voting Readiness',
      icon: '🗳️',
      data: chain.votingStatus
    },
    {
      num: 4,
      id: 'executionDiscrepancy',
      name: 'Execution Discrepancy',
      icon: '⚖️',
      data: chain.executionDiscrepancy
    }
  ];

  return `
    <div class="card eval-chain-card">
      <div class="card-header">
        <div>
          <h3 class="card-title">Four-Stage Governance Evaluation Chain</h3>
          <p class="card-desc">
            Evidence-grounded qualitative indicators. Each stage declares explicit empirical sources and known methodological limitations.
          </p>
        </div>
        <span class="badge badge-outline">Non-Probabilistic Qualitative Analysis</span>
      </div>

      <div class="eval-chain-grid">
        ${stages.map(s => {
          const item = s.data || { status: 'PENDING', level: 'neutral', evidence: 'Awaiting evidence input', limitations: 'Pending audit' };
          const levelClass = item.level === 'good' ? 'badge-success' : item.level === 'danger' ? 'badge-danger' : 'badge-warning';

          return `
            <div class="eval-stage-card eval-stage-${item.level || 'neutral'}">
              <div class="eval-stage-header">
                <div class="eval-stage-num">${s.num}</div>
                <div class="eval-stage-title-wrap">
                  <span class="eval-stage-icon">${s.icon}</span>
                  <h4 class="eval-stage-name">${escapeHTML(s.name)}</h4>
                </div>
              </div>

              <div class="eval-stage-status">
                <span class="badge ${levelClass}">${escapeHTML(item.status)}</span>
              </div>

              <div class="eval-box eval-evidence-box">
                <div class="eval-box-label">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  Source &amp; Empirical Evidence
                </div>
                <p class="eval-box-text">${escapeHTML(item.evidence)}</p>
              </div>

              <div class="eval-box eval-limitations-box">
                <div class="eval-box-label text-muted">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  Methodological Limitations
                </div>
                <p class="eval-box-text text-muted">${escapeHTML(item.limitations)}</p>
              </div>
            </div>
          `;
        }).join('')}
      </div>

      <div class="eval-chain-footer-note text-muted">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
        <strong>Interface Discipline:</strong> Veritas Gate strictly refuses to fabricate numerical Bayesian percentages or calibrated risk scores. Every signal is anchored to observed EVM execution traces.
      </div>
    </div>
  `;
}
