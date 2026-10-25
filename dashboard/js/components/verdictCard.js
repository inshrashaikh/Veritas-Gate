/**
 * components/verdictCard.js
 * =========================
 * Visual Verdict Card displaying status (VERIFIED, MISMATCH, NEEDS_REVIEW),
 * deterministic reason code, human-readable explanation, evidence references,
 * trace completeness, and risk findings.
 */

import { escapeHTML } from '../security.js';

export function renderVerdictCard(proposal) {
  if (!proposal || !proposal.verdict) {
    return `
      <div class="card empty-state-card">
        <p class="text-muted">No proposal selected for verdict inspection.</p>
      </div>
    `;
  }

  const v = proposal.verdict;
  const status = (v.status || 'UNKNOWN').toUpperCase();
  
  let headerClass = 'verdict-header-needs-review';
  let badgeClass = 'badge-warning';
  let iconSvg = `
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  `;

  if (status === 'VERIFIED') {
    headerClass = 'verdict-header-verified';
    badgeClass = 'badge-success';
    iconSvg = `
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M22 11.08V12a10 10 0 11-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
    `;
  } else if (status === 'MISMATCH') {
    headerClass = 'verdict-header-mismatch';
    badgeClass = 'badge-danger';
    iconSvg = `
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <line x1="15" y1="9" x2="9" y2="15"/>
        <line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
    `;
  }

  const evidenceRefs = v.evidenceReferences || [];
  const findings = v.findings || [];

  return `
    <div class="card verdict-card ${headerClass}">
      <div class="verdict-banner-row">
        <div class="verdict-icon-title">
          <div class="verdict-icon">${iconSvg}</div>
          <div>
            <div class="verdict-badge-row">
              <span class="badge ${badgeClass} badge-lg">${escapeHTML(status)}</span>
              <span class="trace-pill ${v.traceComplete ? 'trace-complete' : 'trace-incomplete'}">
                ${v.traceComplete ? '✓ Trace Complete (Full Opcode Coverage)' : '⚠ Incomplete Trace (Fail-Closed Safety)'}
              </span>
              <span class="badge badge-neutral">Mode: ${escapeHTML(v.simulationMode || 'EVM')}</span>
            </div>
            <h3 class="verdict-reason-title">
              Reason Code: <code>${escapeHTML(v.reasonCode || 'UNSPECIFIED')}</code>
            </h3>
          </div>
        </div>
      </div>

      <div class="verdict-explanation">
        <p>${escapeHTML(v.explanation || 'No human-readable explanation supplied.')}</p>
      </div>

      ${findings.length > 0 ? `
        <div class="verdict-section-box">
          <h4 class="box-title text-warning">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            </svg>
            Trace Risk Findings (${findings.length})
          </h4>
          <div class="findings-list">
            ${findings.map(f => `
              <div class="finding-item finding-${(f.severity || 'medium').toLowerCase()}">
                <div class="finding-header">
                  <span class="badge badge-sm badge-danger">${escapeHTML(f.severity || 'RISK')}</span>
                  <code class="finding-code">${escapeHTML(f.code || 'UNKNOWN_FINDING')}</code>
                </div>
                <div class="finding-desc">${escapeHTML(f.description || '')}</div>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${evidenceRefs.length > 0 ? `
        <div class="verdict-section-box">
          <h4 class="box-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            Deterministic Evidence References
          </h4>
          <div class="evidence-ref-table-wrap">
            <table class="data-table-sm">
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Identifier</th>
                  <th>Observed Details</th>
                </tr>
              </thead>
              <tbody>
                ${evidenceRefs.map(ref => `
                  <tr>
                    <td><span class="badge badge-sm badge-outline">${escapeHTML(ref.source)}</span></td>
                    <td><code>${escapeHTML(ref.identifier)}</code></td>
                    <td>
                      <pre class="code-pre">${escapeHTML(JSON.stringify(ref.details || {}, null, 2))}</pre>
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
