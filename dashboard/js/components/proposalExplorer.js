/**
 * components/proposalExplorer.js
 * ===============================
 * Searchable, filterable, and sortable proposal explorer table.
 */

import { escapeHTML, truncateAddress } from '../security.js';

export function renderProposalExplorer(state) {
  const proposals = state.getFilteredProposals();
  const filters = state.filters;
  const isDemo = state.isDemoData;

  return `
    <section class="explorer-section" aria-labelledby="explorer-heading">
      <div class="section-header">
        <div>
          <h2 id="explorer-heading" class="section-title">Proposal Explorer</h2>
          <p class="section-desc">Search, filter, and inspect governance proposals, execution verdicts, and evidence.</p>
        </div>
        ${isDemo ? '<span class="badge badge-warning">DEMO DATA</span>' : ''}
      </div>

      <div class="card filter-bar-card">
        <div class="filter-grid">
          <div class="filter-field search-field">
            <label for="proposal-search" class="filter-label">Search Proposals</label>
            <input type="search" id="proposal-search" class="input" 
                   placeholder="Search by ID, title, proposer address..." 
                   value="${escapeHTML(filters.searchQuery)}">
          </div>

          <div class="filter-field">
            <label for="verdict-filter" class="filter-label">Verdict Filter</label>
            <select id="verdict-filter" class="select">
              <option value="ALL" ${filters.verdict === 'ALL' ? 'selected' : ''}>All Verdicts</option>
              <option value="VERIFIED" ${filters.verdict === 'VERIFIED' ? 'selected' : ''}>VERIFIED (Clean)</option>
              <option value="MISMATCH" ${filters.verdict === 'MISMATCH' ? 'selected' : ''}>MISMATCH (Violations)</option>
              <option value="NEEDS_REVIEW" ${filters.verdict === 'NEEDS_REVIEW' ? 'selected' : ''}>NEEDS_REVIEW (Risky/Incomplete)</option>
            </select>
          </div>

          <div class="filter-field">
            <label for="status-filter" class="filter-label">Governance Status</label>
            <select id="status-filter" class="select">
              <option value="ALL" ${filters.status === 'ALL' ? 'selected' : ''}>All Statuses</option>
              <option value="ACTIVE" ${filters.status === 'ACTIVE' ? 'selected' : ''}>Active</option>
              <option value="PASSED" ${filters.status === 'PASSED' ? 'selected' : ''}>Passed</option>
              <option value="CHALLENGED" ${filters.status === 'CHALLENGED' ? 'selected' : ''}>Challenged</option>
            </select>
          </div>

          <div class="filter-field">
            <label for="sort-filter" class="filter-label">Sort By</label>
            <select id="sort-filter" class="select">
              <option value="date_desc" ${filters.sortBy === 'date_desc' ? 'selected' : ''}>Newest First</option>
              <option value="date_asc" ${filters.sortBy === 'date_asc' ? 'selected' : ''}>Oldest First</option>
              <option value="verdict" ${filters.sortBy === 'verdict' ? 'selected' : ''}>Severity (Mismatch first)</option>
            </select>
          </div>
        </div>
      </div>

      ${proposals.length === 0 ? `
        <div class="card empty-state-card">
          <div class="empty-icon">🔍</div>
          <h3>No Proposals Found</h3>
          <p class="text-muted">No governance proposals matched the selected search query and filter criteria.</p>
          <button id="reset-filters-btn" class="btn btn-sm btn-outline">Clear Filters</button>
        </div>
      ` : `
        <div class="card table-card">
          <div class="table-responsive">
            <table class="data-table" role="table">
              <thead>
                <tr>
                  <th scope="col">ID &amp; Version</th>
                  <th scope="col">Title</th>
                  <th scope="col">Proposer</th>
                  <th scope="col">Verdict</th>
                  <th scope="col">Reason Code</th>
                  <th scope="col">Trace</th>
                  <th scope="col">Status</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                ${proposals.map(p => {
                  const verdict = p.verdict?.status || 'UNKNOWN';
                  const badgeClass = verdict === 'VERIFIED' ? 'badge-success' : verdict === 'MISMATCH' ? 'badge-danger' : 'badge-warning';
                  const isSelected = state.selectedProposal?.id === p.id;
                  
                  return `
                    <tr class="table-row ${isSelected ? 'row-selected' : ''}" data-id="${escapeHTML(p.id)}">
                      <td>
                        <strong>${escapeHTML(p.id)}</strong>
                        <span class="badge badge-sm badge-neutral">${escapeHTML(p.version || 'v1.0')}</span>
                      </td>
                      <td class="table-cell-title">
                        <div class="proposal-table-title">${escapeHTML(p.title)}</div>
                        <div class="proposal-table-desc text-muted">${escapeHTML(p.description?.slice(0, 80))}...</div>
                      </td>
                      <td>
                        <code class="code-address" title="${escapeHTML(p.proposer)}">${truncateAddress(p.proposer)}</code>
                      </td>
                      <td>
                        <span class="badge ${badgeClass}">${escapeHTML(verdict)}</span>
                      </td>
                      <td>
                        <code class="code-sm">${escapeHTML(p.verdict?.reasonCode || 'N/A')}</code>
                      </td>
                      <td>
                        ${p.verdict?.traceComplete ? 
                          '<span class="trace-pill trace-complete" title="Full trace recorded">✓ Complete</span>' : 
                          '<span class="trace-pill trace-incomplete" title="Trace was truncated or partial">⚠ Incomplete</span>'}
                      </td>
                      <td>
                        <span class="badge badge-sm badge-outline">${escapeHTML(p.status || 'ACTIVE')}</span>
                      </td>
                      <td>
                        <button class="btn btn-sm btn-primary select-proposal-btn" data-id="${escapeHTML(p.id)}">
                          Inspect
                        </button>
                      </td>
                    </tr>
                  `;
                }).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `}
    </section>
  `;
}
